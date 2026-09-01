# Cross-browser testing

**Status:** run against Chromium, Firefox and WebKit. 30/30 on every engine, 2 September
2026. The defect previously recorded here as a WebKit fault was a misdiagnosis; §3 records
what it actually was and how it was found.

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
| Chromium | 30/30 pass |
| Firefox | 30/30 pass |
| WebKit | 30/30 pass |

No test is skipped or marked `fixme` on any engine.

Run one engine at a time:

```bash
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

The login limiter allows 15 attempts per 15 minutes and each project spends five. The
counter is now shared through Redis, so restarting the API no longer clears it —
`docker compose exec redis redis-cli FLUSHDB` does. The suite runs
serially (`workers: 1`) — see `playwright.config.ts` for why that is a correctness
requirement here and not a performance choice.

---

## 3. A defect I misdiagnosed, and what it actually was

**Closed 2 September 2026.** The behaviour was real. My explanation of it was wrong twice
before I found the cause, so the whole sequence is recorded rather than just the answer.

### What was observed

Sessions ended mid-run. A probe reading the `refresh_token` cookie after each page load
showed WebKit apparently rotating it twice and then repeating the same value, while Chromium
rotated on every load. The user was signed out on the third load — and because reuse
detection revokes every session for that user, on every device.

### Two wrong explanations

**"The cookie is cross-origin."** The API was addressed absolutely on another port, and
WebKit is stricter than Chromium about cookies written by cross-origin responses. Tested by
proxying the API under the app's own origin: WebKit still failed, one load earlier. Wrong.

**"It is a WebKit cookie-storage bug."** This survived longer because the evidence looked
browser-specific. It was not. Bisecting the changes since — removing the CSP middleware,
then `force-dynamic` — the behaviour did not come back, which meant nothing I had added was
responsible and the original diagnosis had to be re-examined.

### What it actually was

**The client racing itself.** The session provider exchanged the refresh cookie on every
page load by calling `POST /auth/refresh` directly, going around the deduplication that
already existed in `lib/api.ts` for the 401-retry path. Two of those overlapping — a
navigation starting before the previous one's rotated cookie came back — replays a token the
other has just spent. The server reads that as theft, correctly and by design, and ends
every session.

The proof it was never browser-specific: forcing a revocation from outside the browser and
then loading a page reproduces the identical signature **in Chromium**, which never showed
the "WebKit defect". The cookie appearing to stall was the *symptom* of a revoked session —
once refresh returns 401 there is no new cookie to store — not a storage failure. WebKit
simply ran last in the suite, after the most stale sessions had accumulated. Later the same
signature appeared in Firefox, which is what finally ruled the browser out.

### The fix

Two halves, because the client should not cause it and the server should not over-react:

- **`SessionProvider` now restores through `api.restoreSession()`**, the same deduplicated
  path everything else uses, so only one exchange is ever in flight per tab.
- **A ten-second grace window on the server.** A rotated token replayed while its
  replacement is still live is recorded as `TOKEN_REFRESH_RACE` and refused, without
  revoking anything. Outside that window, or once the chain has moved on, the full
  revocation still fires — covered by a test that ages the rotation past the window first,
  so it exercises the theft branch rather than accidentally proving the new one.

What is given up is detection of a theft replayed within seconds of the rotation it raced.
In that window the attacker gets a 401 and no session either way; a token stolen and used
minutes later, which is the realistic case, still ends every session.

### Why the mistake is worth recording

Two page loads overlapping is not exotic, and the consequence — a patient signed out on
every device for doing nothing wrong — is one they could never explain or avoid. It was
visible for days as "flaky tests" and attributed to a browser, which is the comfortable
explanation because it makes it someone else's bug. The evidence that settled it was the
same signature appearing in the browser that was supposed to be fine.

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
