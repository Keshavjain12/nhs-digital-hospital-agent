# Deployment

**Status:** a production-*shaped* deployment, built and run, 31 August 2026.
**Not production-ready.** §6 lists what is missing, and it is not a short list.

This describes how the application is packaged and run as a deployment rather than as a
development stack: built images instead of mounted source, no reload, migrations applied
before the API starts, the database unreachable from outside, a real Content-Security-Policy
and no default secrets anywhere.

> This is a student demonstration on synthetic data. Running it does not make it an NHS
> service, DTAC-assessed, DSPT-certified, or fit for patient use. See `ASSUMPTIONS.md`.

---

## 1. Running it

```bash
# Secrets come from the environment. Every one is mandatory; there are no defaults.
export POSTGRES_USER=hospital
export POSTGRES_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
export POSTGRES_DB=hospital
export JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export WEB_HOST_PORT=3000
# REDIS_URL is set by the compose file. Production refuses to start without it - see §3.

docker compose -f docker-compose.prod.yml up -d --build
```

Then seed demonstration data — synthetic, and the only data this service has:

```bash
docker compose -f docker-compose.prod.yml exec \
  -e DEMO_PASSWORD='<at least 12 characters>' api python scripts/seed_demo.py
```

Only the web service is published. The API and the database are reachable only on the
internal network.

## 2. How it is put together

| Service | What it does |
| --- | --- |
| `db` | PostgreSQL 16. **No published port** — nothing outside needs it, and publishing it is how a development convenience becomes an exposed database. |
| `redis` | Rate-limit counters, shared across workers. No persistence and no volume: nothing here is worth keeping across a restart, and losing it resets a limit rather than losing data. |
| `migrate` | Runs `alembic upgrade head` once and exits. `api` waits for it to complete successfully. |
| `api` | FastAPI under uvicorn, 4 workers, no source mount, no reload. |
| `web` | The Next.js standalone server. The only service published to the host. |

**Migrations are their own service, not part of the API's start-up.** Two API replicas
racing `alembic upgrade head` is a real way to corrupt a schema, and folding migrations into
the application makes that race the default behaviour rather than an accident.

**The browser never talks to the API directly.** `web` proxies `/api/v1/*` to `api` on its
own origin, so the session cookie is first-party, no CORS preflight happens, and the
backend's address never reaches the browser. `CORS_ORIGINS` is therefore empty by default.

Both images run as a non-root user and carry a healthcheck. The frontend image is built in
three stages so the runtime layer carries neither the toolchain nor `node_modules` — Next's
`output: "standalone"` traces only the dependencies actually reached.

**`API_ORIGIN` is a build argument, not a runtime one.** Next evaluates rewrites at build
time and writes them into the routes manifest, so setting it only at runtime leaves the
proxy pointing at the default and every API call fails in a way that looks like the backend
being down.

## 3. Rate limiting is shared, and production insists on it

Counters live in Redis, using an atomic sliding window implemented in Lua — a script rather
than a pipeline, because a read and a write that interleave with another worker's is exactly
the race being removed.

The settings model **refuses to start in production without `REDIS_URL`**. That is a hard
failure rather than a warning because the failure it prevents is silent: with four workers
each keeping its own counter, the configured limit is not the limit in force, and nothing in
the logs says so. The validator earned its keep immediately — the `migrate` service declared
production without Redis and was stopped on the spot.

If Redis becomes unreachable at runtime the limiter degrades to per-process counting and
logs an error, rather than failing open (removing the control exactly when infrastructure is
unhealthy) or closed (locking every user out of a health service because a cache is down).

Measured against the running production stack with four workers: exactly 15 login attempts
allowed, then 429. Before this change it would have been roughly 60.

## 4. Content-Security-Policy

`frontend/middleware.ts`, applied per request because a nonce is by definition per response.

```
default-src 'self';
script-src 'self' 'nonce-<per response>' 'strict-dynamic';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;  font-src 'self' data:;
connect-src 'self';  frame-ancestors 'none';  form-action 'self';
base-uri 'none';  object-src 'none';
upgrade-insecure-requests   (only when the request arrived over TLS)
```

Three things about it are worth knowing, because each was learned by breaking something:

**Pages are rendered per request (`export const dynamic = "force-dynamic"`).** A statically
prerendered page is one response reused for everyone, so Next cannot stamp a per-request
nonce into it and a `strict-dynamic` policy refuses every script it emits. The first
production build did exactly that: the HTML arrived, every chunk was blocked, and the app
sat on "Checking your sign-in details…" forever with no server-side error to show for it.
The alternative was `script-src 'unsafe-inline'`, which is most of what a CSP exists to
prevent. Static prerendering bought very little here — every page is client-rendered and
takes its data from the API at request time, so what was being cached was an empty shell.

**`upgrade-insecure-requests` is conditional on the request scheme, not on `NODE_ENV`.**
Keyed on the build mode first, and that was wrong: the production image served over plain
HTTP told the browser to upgrade every subresource to `https://`, where nothing was
listening. Chromium and Firefox exempt localhost and carried on. WebKit does not, so every
script failed with an SSL error and Safari could not sign in at all — a bug introduced by
the security header itself. It now keys on `x-forwarded-proto` (so a TLS-terminating proxy
is understood) falling back to the request protocol.

**`style-src` still allows `'unsafe-inline'`.** Next injects inline `<style>` for critical
CSS and those are not nonce-stamped. This is a real weakening — style injection can
exfiltrate data through attribute selectors — and it is recorded here rather than left
looking like an oversight.

## 5. Verification performed

The production stack was built, started and tested, not just written:

| Check | Result |
| --- | --- |
| Full browser suite, Chromium | 30/30 |
| Full browser suite, Firefox | 30/30 |
| Full browser suite, WebKit | 24 (the rest from D-WEBKIT-SESSION) |
| CSP present with a per-response nonce | yes |
| `upgrade-insecure-requests` absent over HTTP, present behind a TLS proxy | yes |
| Database reachable from the host | no |
| Migrations applied before the API accepted traffic | yes |
| API reachable only through the web origin's proxy | yes |
| Login limit across 4 workers | 15 allowed, then 429 |
| Production start refused without `REDIS_URL` | yes |

## 6. Operating it

```bash
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec api alembic downgrade -1   # rollback one
docker compose -f docker-compose.prod.yml down          # keeps the volume
docker compose -f docker-compose.prod.yml down -v       # destroys the database
```

Logs are structured JSON with request ids, and the logging formatter redacts credentials and
tokens (`backend/app/core/logging.py`). Every error response carries `X-Request-ID`, so a
user's report can be tied to a log line without asking them for anything sensitive.

Clearing rate-limit counters, which restarting the API no longer does:

```bash
docker compose -f docker-compose.prod.yml exec redis redis-cli FLUSHDB
```

**The demo data ages.** Slots are generated relative to seed time, so a stack left running
for weeks will show an empty appointments screen. Re-running the seeder is idempotent and
tops up an upcoming appointment.

---

## 7. What is missing before this could be deployed for real

Not a summary — the actual list.

**Infrastructure**
- **No TLS.** No certificate, no HSTS, no redirect from HTTP. Everything above assumes a
  TLS-terminating proxy in front, which does not exist here.
- **No secrets management.** Secrets come from the shell environment. There is no vault, no
  rotation, and no separation between who can deploy and who can read a secret.
- **No backups.** The database is a Docker volume. Nothing is backed up, and no restore has
  ever been tested — an untested backup is not a backup.
- **Single host, no redundancy.** One instance of everything. Any failure is an outage.
- **No log aggregation, metrics or alerting.** Logs stay in the containers. Nobody is
  paged, and nothing is retained.
- **No CI/CD.** Images are built by hand on a developer machine. Nothing is signed, scanned
  or reproducible from a known commit.

**Security and governance**
- **No penetration test** and no independent security review.
- **No DSPT submission, no DTAC assessment, no DPIA.** None started.
- **No named Clinical Safety Officer**, so no DCB0129/0160 safety case can exist — blocker
  B5 in `ASSUMPTIONS.md`.
- **No email delivery.** Password reset and confirmation emails are not sent anywhere.

**Clinical and data**
- **All data is synthetic.** No real patient record has been near this, which is the only
  reason the gaps above are survivable.
- **The triage engine has never been clinically reviewed** — blocker B3.
- **Welsh translations are machine-drafted** and unreviewed. Safety-critical strings show
  English alongside; that is a mitigation, not a substitute for translation.
- **No accessibility testing with real users or screen readers.** See
  `docs/testing/accessibility-audit.md` §5.
