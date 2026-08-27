"""Rate limiting.

An in-process sliding-window counter. Brief §17 requires rate limiting; this covers the
single-instance development and staging deployment this project targets.

**Known limitation, stated rather than hidden:** the counters live in process memory, so
with more than one API replica each replica enforces its own limit and the effective
limit multiplies by the replica count. Moving to Redis is the fix, and is the reason
`RateLimiter` is an interface with the storage behind it - see `RedisRateLimiter` as the
documented next step in docs/architecture/02-system-architecture.md.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol


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

_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter
