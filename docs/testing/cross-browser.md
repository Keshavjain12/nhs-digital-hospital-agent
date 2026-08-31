# Cross-browser testing

**Status:** run against Chromium, Firefox and WebKit, 31 August 2026. **One open defect
found in WebKit**, unresolved — see §3.

Two suites run on all three engines: the WCAG audit
(`docs/testing/accessibility-audit.md`) and the journey checks in
`frontend/e2e/cross-browser.spec.ts`. The accessibility suite covers rule-level conformance
per page; this one covers what differs between *engines* rather than between pages.

WebKit is the engine behind Safari and the closest thing to it that runs on Windows. **It is
not Safari**, and a finding in WebKit needs confirming on real Safari before it is treated
as certain.

---

## 1. What is checked

| Check | Why it is engine-sensitive |
| --- | --- |
| Native `<dialog>` with `showModal()` | The cancel confirmation depends on it for a real focus trap and page inertness. An engine without it would render a non-modal dialog and say nothing. |
| `Intl` date formatting for en-GB | Appointment times are formatted client-side. An engine falling back to US ordering would show 3 April as 4 March — wrong, plausible, and about an appointment. |
| Patient dashboard renders its own content | A page whose requests all fail still looks fine in a screenshot, so the failure state is asserted absent explicitly. |
| Appointments list shows a booking reference | Real data reaching the page, not just a shell. |
| Booking page offers slots | |
| Layout at 360 px | The most common Android width. Distinct from the 320 px WCAG reflow check. |
| Clinical queue renders rows | |
| Triage view raises no uncaught error | An exception in one engine and not another is the classic cross-browser failure, and it does not necessarily change what the page looks like. |

## 2. Results

| Engine | Result |
| --- | --- |
| Chromium | 29/29 pass |
| Firefox | 29/29 pass |
| WebKit | 27 pass, 2 marked `fixme` for the defect in §3 |

Run one engine at a time:

```bash
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

The login limiter allows 15 attempts per 15 minutes and each project spends five, so
`docker compose restart api` between projects clears the in-process counter. The suite runs
serially (`workers: 1`) — see `playwright.config.ts` for why that is a correctness
requirement here and not a performance choice.

---

## 3. Open defect — WEBKIT-SESSION

**In WebKit, a signed-in user is signed out on the third full page load — and because reuse
detection revokes every session for that user, they are signed out on every device.**

### What was observed

A probe that signs in and then loads four pages, reading the `refresh_token` cookie after
each:

```
chromium   a5huz1qQRw | OW8d8dkBWh | rng38U588T | jq48kYZd4B    (four distinct values)
webkit     FaOo1GvWhp | 19M4_nsMLG | FkA0dE6M1i | FkA0dE6M1i    (stalls, then repeats)
```

Chromium rotates the cookie on every load. WebKit rotates twice and then stops storing the
new value, so the next load presents a token that has already been spent.

The server's response to that is correct and deliberate: a replayed refresh token is
indistinguishable from a stolen one, so `revoke_all_for_user` ends every session
(`backend/app/services/auth.py`). The security control is behaving exactly as designed. The
problem is that WebKit hands it a false positive.

Confirmed by a second probe: signed out on load 3 under WebKit, still signed in after load 4
under Chromium.

### The cause is not what I first assumed

My first hypothesis was that the cookie being cross-origin was to blame: the API was
addressed absolutely at `localhost:8000` while the app ran on `localhost:3001`, and WebKit
applies stricter rules than Chromium or Firefox to cookies written by a cross-origin XHR
response.

**That hypothesis was tested and is wrong.** The API is now proxied under the app's own
origin, so the cookie is first-party and no CORS is involved. WebKit still fails — in fact
it stalls one load earlier:

```
                    login       load 1      load 2      load 3      load 4
chromium (after)    fjZcSXjevv  zgHTmjAucv  RC66PqTE8L  SUypZNpDra  0YsxeM9sjv
webkit   (after)    6v_cpNlUOS  lZK8pJzoYm  lZK8pJzoYm  lZK8pJzoYm  lZK8pJzoYm
```

So: WebKit stores the cookie when it is first created, accepts one update, and then stops
accepting updates. Chromium accepts every one. The cause is something about how WebKit
handles a repeated `Set-Cookie` for an existing cookie on a fetch response, and I have not
identified it.

The same-origin proxy was kept regardless — it removes a CORS preflight from every request
and keeps the backend's address out of the browser, which are worth having on their own
merits. It is simply not the fix for this.

### What has and has not been done

- **Not fixed.** The one hypothesis I had was tested and disproved, above. I do not
  currently know the cause.
- **Not confirmed on real Safari.** WebKit on Windows is not Safari on macOS or iOS, and
  that remains the most likely way this turns out to be narrower than it looks.
- **Not explained by deployment topology.** The service is now same-origin and the defect
  persists — one load earlier, in fact — so it cannot be put down to running the API on a
  separate port in development.
- **Two tests carry `test.fixme` for WebKit**, referencing this section. They are visible as
  skipped with a reason rather than deleted or quietly passed.

### Why it matters

Safari is a large share of UK mobile browsing, and this is a patient-facing service. Being
signed out mid-task is bad; being signed out *on every device* because the service decided
you might be an attacker is worse, and it would be very hard for a patient to make sense of.
It should be resolved before any real use, and it is listed in `ASSUMPTIONS.md` as an open
issue.

---

## 4. A WebKit difference that is not a defect

**WebKit leaves links out of the tab order** unless the reader has turned on Safari's Full
Keyboard Access. On WebKit the first tab stop on a patient page is the language `select`,
not the skip link.

This is Safari behaving as Safari and there is nothing the page can do about it. The skip
link is present and reachable; only its *position in the tab sequence* differs, so that
assertion is scoped to Chromium and Firefox with the reason recorded rather than the check
being deleted.

It does mean a Safari user who has not enabled Full Keyboard Access cannot use the skip
link. Worth knowing, and not something this codebase can fix.

---

## 5. Not covered

- **Real Safari, real Edge.** Edge is Chromium-based and covered in substance by the
  Chromium runs, but has not been run directly. Safari has not been run at all.
- **Mobile browsers on real devices.** Viewport size was emulated at 360 px; touch input,
  on-screen keyboards and real iOS Safari were not tested.
- **Older browser versions.** Only current stable engines, as bundled with Playwright.
- **Screen readers**, which are browser-paired in practice (VoiceOver with Safari, NVDA with
  Firefox). See the accessibility report §5.
