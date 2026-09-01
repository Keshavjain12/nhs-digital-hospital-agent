"""Rate limiting.

Brief §17 requires rate limiting. Two implementations behind one interface:

* `InMemoryRateLimiter` - a sliding-window log in process memory. Correct for a single
  process, and used for development and the test suite.
* `RedisRateLimiter` - the same algorithm with the window in Redis, so every worker and
  every replica counts against one total.

The in-memory one was the only implementation until the production stack started running
uvicorn with four workers, at which point each worker kept its own counter and the
effective login limit became roughly four times the configured one - and reset on every
deploy. A limit whose real value is "the configured number times however many workers
happen to be running" is not a control, so production now requires REDIS_URL
(`app/core/config.py`).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from redis.exceptions import RedisError

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimit:
    """A limit of `max_events` within `window_seconds`."""

    max_events: int
    window_seconds: int

    @property
    def description(self) -> str:
        return f"{self.max_events} per {self.window_seconds}s"


@dataclass(frozen=True, slots=True)
class RateLimitVerdict:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    async def check(self, key: str, limit: RateLimit) -> RateLimitVerdict: ...
    async def reset(self, key: str) -> None: ...


@dataclass
class InMemoryRateLimiter:
    """Sliding-window log, keyed by an opaque string.

    A sliding window rather than a fixed one: a fixed window lets an attacker send the
    full allowance at the end of one window and again at the start of the next, which
    doubles the effective burst exactly when it matters least.
    """

    _events: dict[str, deque[float]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def check(self, key: str, limit: RateLimit) -> RateLimitVerdict:
        now = time.monotonic()
        cutoff = now - limit.window_seconds

        async with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit.max_events:
                retry_after = max(1, int(bucket[0] + limit.window_seconds - now) + 1)
                return RateLimitVerdict(allowed=False, retry_after_seconds=retry_after)

            bucket.append(now)
            if not bucket:
                self._events.pop(key, None)
            return RateLimitVerdict(allowed=True)

    async def reset(self, key: str) -> None:
        """Clear a key's history, e.g. after a successful login."""
        async with self._lock:
            self._events.pop(key, None)

    async def purge_expired(self, older_than_seconds: int = 3600) -> int:
        """Drop stale buckets so the dictionary cannot grow without bound.

        Without this, every distinct key ever seen - one per attacker IP - stays resident
        for the process lifetime, which is a slow memory leak with an obvious trigger.
        """
        cutoff = time.monotonic() - older_than_seconds
        async with self._lock:
            stale = [
                key for key, events in self._events.items() if not events or events[-1] <= cutoff
            ]
            for key in stale:
                del self._events[key]
            return len(stale)


#: One atomic sliding-window check.
#:
#: A Lua script rather than a pipeline, because the read and the write must not interleave
#: with another worker's: two requests both reading "14 of 15 used" and both adding one is
#: exactly the race this whole change exists to remove.
#:
#: KEYS[1] the window key.  ARGV: now (ms), window (ms), max events, a unique member id.
#: Returns {allowed, retry_after_seconds}.
_SLIDING_WINDOW = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
local used = redis.call('ZCARD', KEYS[1])

if used >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = 1
  if oldest[2] then
    retry = math.ceil((tonumber(oldest[2]) + window - now) / 1000)
    if retry < 1 then retry = 1 end
  end
  return {0, retry}
end

redis.call('ZADD', KEYS[1], now, ARGV[4])
-- Expire slightly beyond the window so an idle key cannot linger, and so a key nobody
-- touches again is reclaimed without a sweeper.
redis.call('PEXPIRE', KEYS[1], window + 1000)
return {1, 0}
"""


class RedisRateLimiter:
    """The sliding-window log, shared across every worker and replica.

    Falls back to a local counter when Redis is unreachable rather than failing either
    open or closed. Failing open removes the control at exactly the moment infrastructure
    is unhealthy; failing closed locks every user out of a health service because a cache
    is down. Degrading to per-process counting keeps *a* limit in force and says so loudly
    in the log.
    """

    def __init__(self, url: str, fallback: InMemoryRateLimiter | None = None) -> None:
        self._url = url
        self._client: Redis | None = None
        self._fallback = fallback or InMemoryRateLimiter()

    def _connect(self) -> Redis:
        if self._client is None:
            self._client = redis_from_url(self._url, decode_responses=True)
        return self._client

    async def check(self, key: str, limit: RateLimit) -> RateLimitVerdict:
        try:
            client = self._connect()
            now_ms = int(time.time() * 1000)
            # EVAL rather than a registered script: redis-py caches by SHA behind
            # register_script, but its async typing does not line up and the saving is a
            # few hundred bytes per call on a path that runs at human speed.
            allowed, retry_after = await client.eval(
                _SLIDING_WINDOW,
                1,
                f"rl:{key}",
                now_ms,
                limit.window_seconds * 1000,
                limit.max_events,
                f"{now_ms}-{uuid.uuid4().hex}",
            )
        except RedisError as error:
            logger.error(
                "rate_limiter_unavailable",
                extra={"error": type(error).__name__, "detail": "degraded to per-process counting"},
            )
            return await self._fallback.check(key, limit)

        return RateLimitVerdict(allowed=bool(allowed), retry_after_seconds=int(retry_after))

    async def reset(self, key: str) -> None:
        try:
            await self._connect().delete(f"rl:{key}")
        except RedisError:
            # A failed reset only means the user keeps a few counted attempts they should
            # not have. Not worth failing the request they just succeeded at.
            await self._fallback.reset(key)


# Limits from docs/api/api-contract-v1.md §1.
#
# LOGIN_LIMIT is deliberately higher than settings.max_failed_logins (5). The two controls
# defend different attacks and must not share a threshold:
#
#   account lockout  - one account, many guesses  (targeted brute force)
#   IP rate limit    - many accounts, few guesses (password spraying)
#
# When the IP limit is set at or below the lockout threshold, a single-account attack trips
# the IP limit first and the lockout never engages, leaving the account-level control dead
# while appearing to be configured.
LOGIN_LIMIT = RateLimit(max_events=15, window_seconds=900)
# Keyed on client IP, so this counts everyone behind one address. Three per hour
# false-positives on any shared connection - a household, a ward, a university - and the
# person refused has no way to tell it was not their own mistake. Ten still stops bulk
# account creation while leaving legitimate shared use unaffected.
REGISTRATION_LIMIT = RateLimit(max_events=10, window_seconds=3600)
PASSWORD_RESET_LIMIT = RateLimit(max_events=3, window_seconds=3600)
AUTHENTICATED_LIMIT = RateLimit(max_events=300, window_seconds=60)
ANONYMOUS_LIMIT = RateLimit(max_events=60, window_seconds=60)

_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """The process-wide limiter, chosen once from configuration.

    Redis when REDIS_URL is set, which production requires; the in-process counter
    otherwise. Built lazily so importing this module does not open a connection - the test
    suite and the migration runner both import it without wanting one.
    """
    global _limiter
    if _limiter is None:
        from app.core.config import get_settings

        url = get_settings().redis_url
        _limiter = RedisRateLimiter(url) if url else InMemoryRateLimiter()
    return _limiter


def reset_rate_limiter() -> None:
    """Drop the cached limiter. For tests that change configuration between cases."""
    global _limiter
    _limiter = None
