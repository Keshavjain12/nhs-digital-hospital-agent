# Accessibility audit

**Status:** 63 automated checks passing across three browser engines, 31 August 2026 —
21 checks × Chromium, Firefox and WebKit. Screen-reader and cognitive checks **not done**.

WCAG 2.1 AA is the standard the NHS Service Standard and DTAC require. This records what was
tested, the one real defect it found, and — at least as importantly — the substantial part
of accessibility that automated tooling cannot reach and that has not been covered here.

> **Automated tooling finds roughly a third of accessibility barriers.** Everything in §2
> passing means the machine-detectable failures are absent. It does not mean the service is
> accessible, and this document does not claim conformance. See §5.

---

## 1. How it runs

```bash
# both servers must be up: docker compose up, and npm run dev
npm run test:a11y     # Chromium only, quick
npm run test:e2e      # all three engines
```

Two things about the harness are worth knowing before running it:

**The login rate limiter will stop you.** It allows 15 attempts per 15 minutes and each full
run spends three. Iterating on these tests exhausts it, and the symptom is a bare navigation
timeout that looks nothing like its cause — so `signIn` now detects it and says so. The
limiter is in-process; `docker compose restart api` clears it.

**Sessions are shared per role, deliberately.** The first version signed in for every test
and every authenticated test failed with a 429. Playwright's usual answer — save
`storageState` and reuse it across workers — does not work here either, for a more
interesting reason: the refresh token rotates on every use, and presenting a rotated one
revokes the whole chain. Parallel workers replaying one saved cookie is exactly the reuse
pattern the auth design treats as a stolen token. So each role signs in once and runs its
tests serially in that context.

---

## 2. What was tested and what it found

### 2.1 Automated rule checks (axe-core, WCAG 2.1 AA tags only)

Fourteen pages, every one clean:

| Area | Pages |
| --- | --- |
| Public | home, sign in, register, forgot password, not authorised |
| Patient | dashboard, appointments, booking, symptom check |
| Clinical | queue, triage review |
| Administrative | dashboard, audit trail, model monitoring |

Restricted to the `wcag2a`, `wcag2aa`, `wcag21a` and `wcag21aa` tags rather than everything
axe knows. Best-practice rules are worth following, but failing a build on them
misrepresents which findings are conformance failures and which are opinions.

The Next.js dev-tools overlay is excluded. It is injected into every dev-server page, ships
in no build a user loads, and auditing it reports failures in someone else's toolbar as
failures in this service. That exclusion is narrow and deliberate — not a way to make an
inconvenient finding disappear.

### 2.2 The defect this found

**Reflow, WCAG 1.4.10 — the patient dashboard scrolled sideways by 116 px at 320 px wide.**

320 px is the criterion's own threshold, equivalent to 400% zoom on a 1280 px screen and
roughly the narrowest phone still in use. Horizontal scrolling at that width means a reader
who has zoomed in loses the layout out from under them on every line.

The cause was a header row — the "signed in as", language switcher and sign-out cluster —
that could not wrap. Both the staff and admin layouts already had `flex-wrap` on the same
cluster; only the patient one was missing it. All three nav rows lacked it as well.

Fixed in `app/(patient)/layout.tsx`, `app/(staff)/layout.tsx` and `app/(admin)/layout.tsx`.
The check now passes at 320 px on all three engines, and there is a matching check that the
clinical queue — the widest table in the product — does not scroll the page body at 200%
zoom.

### 2.3 Checks that cannot be done in jsdom

These are the reason for adding a real browser rather than extending the Vitest suite.
jsdom has no layout engine and no rendering, so it can neither compute contrast against what
is actually painted nor tell whether a focus ring is visible.

| Check | Criterion | Result |
| --- | --- | --- |
| Every interactive element on sign-in shows a visible focus indicator | 2.4.7 | Pass |
| Skip link is present, and is the first tab stop | 2.4.1 | Pass (see §3 for WebKit) |
| Symptom check startable and answerable by keyboard alone | 2.1.1 | Pass |
| Cancel dialog traps focus, closes on Escape, returns focus to trigger | 2.1.2, 2.4.3 | Pass |
| Patient pages reflow at 320 px | 1.4.10 | Pass, after §2.2 |
| Clinical queue at 200% zoom | 1.4.10 | Pass |
| Exactly one `h1` and a non-empty title per page | 1.3.1, 2.4.2 | Pass |
| `html` element declares a language | 3.1.1 | Pass |

The focus-indicator check exists because the project sets `:focus-visible` deliberately
*outside* any cascade layer — unlayered CSS beats all layered CSS regardless of specificity.
That decision is easy to undo by accident in a later stylesheet change, and this is what
would catch it.

The dialog check verifies a native `<dialog>` opened with `showModal()`, which makes the
rest of the page inert. That is what makes the focus trap real rather than something
reimplemented in JavaScript that a screen reader may not respect.

---

## 3. A genuine cross-browser difference

**WebKit does not put links in the tab order by default.** Safari leaves anchors out of the
tab sequence unless the reader turns on Full Keyboard Access, so on WebKit the first tab
stop on a patient page is the language `select`, not the skip link.

This is Safari behaving as Safari, not a defect in this service, and the fix is not
available to the page: it is a browser setting. The skip link is still present and still
reachable — the assertion about its *position* is therefore scoped to Chromium and Firefox,
with this note explaining why rather than the check being quietly deleted.

It does mean a Safari user who has not enabled Full Keyboard Access cannot use the skip
link. That is worth knowing and is recorded in the cross-browser report.

---

## 4. Two harness bugs worth recording

Both were my errors, not the application's, and both would have produced a misleading result
if left alone:

- **A test that asserted against a page that does not exist.** The first keyboard test
  looked for a text input on the symptom check page and failed. There is no input there
  until you press Start — the tab order was in fact perfectly correct. Reported as a defect,
  it would have been a false finding.
- **A locator that silently matched nothing.** `input[type='text']` does not match the
  answer box, because the field carries no `type` attribute at all (text is the default).
  Now located by ARIA role, which is both correct and what assistive technology goes on.

---

## 5. Not covered — the part that matters most

Automated checks find the failures a machine can see. Everything below needs a person, and
none of it has been done:

- **Screen readers.** No testing with NVDA, JAWS or VoiceOver. Nothing here establishes that
  the emergency banner is *announced* rather than merely present in the accessibility tree,
  which is the single most safety-relevant question in the product.
- **Whether the emergency advice reads as urgent when heard.** Visual prominence and audible
  prominence are different things, and only the first has been checked.
- **Focus order being logical.** The tests confirm focus moves and is visible. Whether the
  order makes sense to someone who cannot see the layout is a judgement call.
- **Colour independence.** The clinical queue's priority flags have not been checked for
  conveying urgency by more than hue (WCAG 1.4.1). Automated contrast checking does not
  answer this.
- **Reading level and cognitive load.** NHS guidance is a reading age of around 11. Not
  assessed.
- **Users with access needs.** No one with a disability has used this service. That is what
  an accessibility audit means in an NHS procurement, and it has not happened here.
- **Welsh with a screen reader.** `SafetyText` shows English alongside draft translations
  and marks it with `lang="en-GB"` so the voice switches. Verified in markup; never heard.

Because of the above, this project makes **no claim of WCAG 2.1 AA conformance** and no
claim of DTAC compliance. See `ASSUMPTIONS.md`.
