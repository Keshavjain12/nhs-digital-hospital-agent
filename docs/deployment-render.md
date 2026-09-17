# Deploying to Render

**Status:** configuration prepared and checked locally, 17 September 2026. Not yet deployed.

`render.yaml` in the repository root is a Render Blueprint. It creates four resources on
Render's free tier, in the Frankfurt region (the closest Render offers to the UK):

| Resource | Type | Purpose |
| --- | --- | --- |
| `nhs-hospital-agent-db` | PostgreSQL 16 | The application database |
| `nhs-hospital-agent-redis` | Key Value | Rate-limit counters shared by the API |
| `nhs-hospital-agent-api-kj12` | Web service (Docker) | The FastAPI backend |
| `nhs-hospital-agent-kj12` | Web service (Docker) | The Next.js app - the address you share |

> A demonstration on synthetic data. Deploying it does not make it an NHS service, and it
> must not be used for real patients. See `ASSUMPTIONS.md`.

---

## 1. Deploy

1. **Create a Render account** at <https://render.com> and sign in. No card is needed for the
   free tier.
2. In the Render dashboard choose **New → Blueprint**.
3. **Connect the repository** `Keshavjain12/nhs-digital-hospital-agent`. Connecting your
   GitHub account is the easiest route; the repository is public. Choose the `main` branch.
4. Render reads `render.yaml` and lists the four resources above. When it asks for
   **`DEMO_PASSWORD`**, enter the password the sign-in page shows for the demonstration
   accounts: `demo-hospital-2026`. The two must match, or the listed accounts will not sign in.
5. Click **Apply** (or **Deploy Blueprint**). The first build takes roughly **10-15 minutes**;
   installing the API's Python dependencies is the slow part.
6. **Check the API's address.** Open the `nhs-hospital-agent-api-kj12` service. Its address
   should be exactly `https://nhs-hospital-agent-api-kj12.onrender.com`.
   - **If it is different** (someone else already had that name), copy the real address, open
     the `nhs-hospital-agent-kj12` service → **Environment**, set `API_ORIGIN` to it, then
     choose **Manual Deploy → Clear build cache & deploy**. The clean build matters: the app
     reads `API_ORIGIN` when it is built, not when it runs.
7. **Open the app** at the `nhs-hospital-agent-kj12` service's address. The first visit can
   take about a minute while the service wakes.

## 2. Check it works

| Check | How |
| --- | --- |
| The API is up | Open `https://<api address>/health` - expect a 200 with a short JSON body |
| The app loads | The landing page shows the demonstration banner and footer |
| Sign-in works | Sign in as `patient@example.test` with the demo password |
| Data is there | The dashboard shows an upcoming appointment |
| Clinical view | Sign in as `doctor@example.test` - the working list shows patients |
| Admin view | Sign in as `admin@example.test` - the audit trail lists your sign-ins |
| HTTPS headers | In the browser's developer tools, a page response carries `Content-Security-Policy` with a `nonce-` value |

If every sign-in fails with "We could not reach the service", `API_ORIGIN` is wrong or was not
applied at build time - repeat step 6.

## 3. How it differs from the compose deployment

| | `docker-compose.prod.yml` | Render free tier |
| --- | --- | --- |
| Migrations | Their own one-shot service | `scripts/render-start.sh`, before the API starts |
| Demo data | Seeded by hand | Seeded on every start (idempotent) when `DEMO_PASSWORD` is set |
| API reachability | Internal network only | Public HTTPS address - free services cannot receive private-network traffic |
| API workers | 4 | 1 - a free instance has 512 MB of memory |
| TLS | None | Provided by Render |

The app still proxies `/api/v1` on its own origin, so the browser never calls the API
directly and the session cookie stays first-party.

## 4. Free-tier limits that matter

- **The database is deleted.** Free PostgreSQL expires **30 days after creation**, then has a
  **14-day grace period** before Render deletes it with all its data. If the site needs to be up
  for marking after that, upgrade the database before it expires. The data is synthetic and
  re-seeded on start, so a new database loses nothing of value - but the deployment stops
  working until one is attached.
- **Services sleep.** Each web service sleeps after 15 minutes without traffic and takes about
  a minute to wake. The app and the API sleep independently. To soften this, the app pings the
  API's health check on page loads (at most every five minutes), and its API proxy waits up to
  two minutes instead of Next's default 30 seconds.
- **750 free instance hours a month** across your whole Render workspace. Sleeping services
  use none, so this is only reached if both services are kept awake around the clock.
- **Key Value does not persist.** A restart clears the rate-limit counters. Nothing else is
  stored there.
- **No shell, pre-deploy command or one-off job** on free services, which is why migration and
  seeding live in the start script.

## 5. Known issues on this deployment

- **The login rate limit can be bypassed** by spoofing `X-Forwarded-For` (open defect
  **D-FORWARDED-FOR** in `ASSUMPTIONS.md`). Per-account lockout still applies. It matters more
  once the service has a public address.
- **The demonstration accounts are public by design**, including the administrator. Anyone with
  the address can sign in as any role and see the synthetic data.
- **It looks NHS-branded.** Every page carries the demonstration banner and a footer saying it
  is not connected to the NHS, and search engines are told not to index it. Share the address
  with the people who need it rather than publishing it.
