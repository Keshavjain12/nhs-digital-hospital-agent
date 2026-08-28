"""Measure API latency.

Brief §5: establish a baseline, then measure - do not optimise speculatively. This script
is the baseline. It reports p50/p95/max per endpoint so that a change can be justified by a
number rather than by intuition.

Reported percentiles are of *server-observed* latency over loopback, so they exclude network
and TLS. They are useful for comparing one build against another, not for predicting what a
patient on mobile data experiences.

    docker compose exec api python scripts/benchmark.py
    docker compose exec api python scripts/benchmark.py --runs 50
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx

BASE_URL = "http://localhost:8000/api/v1"
DEMO_PASSWORD_ENV = "DEMO_PASSWORD"  # noqa: S105 - an environment variable name, not a secret

#: Above this a screen feels sluggish rather than instant. Not a contractual target - a
#: line to notice when a measurement crosses it.
SLOW_MS = 300.0


@dataclass(frozen=True, slots=True)
class Result:
    name: str
    method: str
    path: str
    samples: list[float]
    status: int

    @property
    def p50(self) -> float:
        return statistics.median(self.samples)

    @property
    def p95(self) -> float:
        if len(self.samples) < 20:
            return max(self.samples)
        return statistics.quantiles(self.samples, n=20)[18]

    @property
    def worst(self) -> float:
        return max(self.samples)


async def sign_in(client: httpx.AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        f"{BASE_URL}/auth/login", json={"email": email, "password": password}
    )
    response.raise_for_status()
    return str(response.json()["accessToken"])


async def measure(
    client: httpx.AsyncClient, name: str, method: str, path: str, token: str, runs: int
) -> Result:
    headers = {"Authorization": f"Bearer {token}"}
    samples: list[float] = []
    status = 0

    # One untimed request first: the first call pays for connection setup and any lazily
    # built query plan, which would otherwise land entirely in the p95.
    await client.request(method, f"{BASE_URL}{path}", headers=headers)

    for _ in range(runs):
        started = time.perf_counter()
        response = await client.request(method, f"{BASE_URL}{path}", headers=headers)
        samples.append((time.perf_counter() - started) * 1000)
        status = response.status_code

    return Result(name=name, method=method, path=path, samples=samples, status=status)


async def run(runs: int) -> int:
    import os

    password = os.environ.get(DEMO_PASSWORD_ENV)
    if not password:
        print(f"{DEMO_PASSWORD_ENV} is not set; run the seeder first.")
        return 1

    async with httpx.AsyncClient(timeout=30) as client:
        patient = await sign_in(client, "patient@example.test", password)
        doctor = await sign_in(client, "doctor@example.test", password)
        admin = await sign_in(client, "admin@example.test", password)

        checks = [
            ("patient: available slots", "GET", "/slots?limit=50", patient),
            ("patient: slots, one department", "GET", "/slots?limit=50", patient),
            ("patient: my appointments", "GET", "/appointments", patient),
            ("clinician: patient list", "GET", "/patients?pageSize=20", doctor),
            ("clinician: patient search", "GET", "/patients?q=tester1&pageSize=20", doctor),
            ("clinician: triage queue", "GET", "/triage?limit=50", doctor),
            ("admin: overview", "GET", "/admin/overview", admin),
            ("admin: audit trail", "GET", "/admin/audit?pageSize=25", admin),
            ("admin: model monitoring", "GET", "/admin/models", admin),
        ]

        results = [
            await measure(client, name, method, path, token, runs)
            for name, method, path, token in checks
        ]

    print(f"\n{runs} runs each, milliseconds\n")
    print(f"  {'endpoint':<34}{'status':>7}{'p50':>9}{'p95':>9}{'max':>9}")
    print(f"  {'-' * 34}{'-' * 7:>7}{'-' * 9:>9}{'-' * 9:>9}{'-' * 9:>9}")

    slow: list[Result] = []
    for result in results:
        flag = ""
        if result.p95 > SLOW_MS:
            flag = "  <-- slow"
            slow.append(result)
        print(
            f"  {result.name:<34}{result.status:>7}"
            f"{result.p50:>9.1f}{result.p95:>9.1f}{result.worst:>9.1f}{flag}"
        )

    if slow:
        print(f"\n{len(slow)} endpoint(s) above {SLOW_MS:.0f}ms at p95:")
        for result in slow:
            print(f"  {result.method} {result.path}")
    else:
        print(f"\nNothing above {SLOW_MS:.0f}ms at p95.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure API latency.")
    parser.add_argument("--runs", type=int, default=30)
    args = parser.parse_args()
    return asyncio.run(run(args.runs))


if __name__ == "__main__":
    raise SystemExit(main())
