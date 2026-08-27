# 04 — Frontend Specification

Covers brief §41 part G, plus §15, §16, §19, §20, §21, §30, §38.

---

## 1. Route map

Every route sits under a `[locale]` segment (see `02-system-architecture.md` §D for why).

### Public — `app/[locale]/(public)/`

| Route | Page | Notes |
|---|---|---|
| `/` | Landing | Explains what the service is and, prominently, what it is not |
| `/login` | Patient login | |
| `/register` | Patient registration | 3-step: account → identity → confirmation |
| `/forgot-password` | Request reset | Always shows the same confirmation, no account enumeration |
| `/reset-password/[token]` | Set new password | |
| `/staff/login` | Staff login | Separate entry; CIS2 button present but disabled with an explanatory tooltip |
| `/accessibility` | Accessibility statement | Legally expected for public sector services |
| `/privacy` | Privacy notice | Explains synthetic data and non-clinical status |

### Patient — `app/[locale]/(patient)/`

| Route | Page | Key states |
|---|---|---|
| `/dashboard` | Next appointment, quick actions, notifications | empty (no appointments), loading, error |
| `/chat` | Chatbot | active, thinking, escalated, error, offline |
| `/symptom-check` | Structured symptom intake | multi-step, validation, red-flag interrupt |
| `/triage/[id]` | Triage result | emergency, urgent, routine, under review |
| `/appointments` | List: upcoming / past tabs | empty, loading, error |
| `/appointments/book` | Booking wizard | 4 steps + conflict recovery |
| `/appointments/[id]` | Detail | cancelled, completed, DNA variants |
| `/appointments/[id]/reschedule` | Reschedule | reuses the slot picker |
| `/profile` | Personal details, contact, language, accessibility needs | saving, saved, error |
| `/notifications` | Reminder history | empty |

### Staff — `app/[locale]/(staff)/`

| Route | Page | Key states |
|---|---|---|
| `/staff/queue` | Patient queue with priority column | empty, loading, filtered-empty |
| `/staff/patients` | Search | requires ≥3 chars, no-results |
| `/staff/patients/[id]` | Record shell with tabs | not-found, no-access + break-glass offer |
| `…/[id]/overview` | Demographics, alerts, allergies, risk indicators | |
| `…/[id]/encounters` | Encounter timeline | empty |
| `…/[id]/observations` | Observation table + trend charts | empty |
| `…/[id]/conditions` `…/medications` | Lists | empty |
| `…/[id]/documents` | AI documents for this patient | empty |
| `/staff/documents` | Review worklist across patients | empty |
| `/staff/documents/[id]/review` | **The human-in-the-loop screen** | draft, editing, unsaved-changes, approved |
| `/staff/triage/[id]/review` | Confirm or override a triage result | |

### Admin — `app/[locale]/(admin)/`

| Route | Page |
|---|---|
| `/admin/dashboard` | KPI cards + occupancy and wait-time charts |
| `/admin/departments` | Per-department performance table |
| `/admin/capacity` | Slot and clinic capacity management |
| `/admin/alerts` | Operational alerts |
| `/admin/models` | Model registry table |
| `/admin/models/[id]` | Metrics, drift history, model card link |
| `/admin/overrides` | Override log |
| `/admin/audit` | Audit search |

---

## 2. Design system — `components/ui/`

19 primitives, per brief §41 part G. Every one is keyboard-operable and screen-reader-labelled
before it is considered done.

| Component | Accessibility requirement it must satisfy |
|---|---|
| `Button` | Real `<button>`; visible focus ring; `aria-busy` while pending; never a `<div onClick>` |
| `Input` | Always a bound `<label>`; `aria-describedby` for hint and error; `aria-invalid` |
| `Select` | Native `<select>` by default — a custom listbox is only worth its accessibility cost when genuinely needed |
| `Textarea` | Label + character counter announced via `aria-live="polite"` |
| `Checkbox` / `RadioGroup` | `<fieldset>` + `<legend>`; grouped, not orphaned |
| `Card` | Heading level passed as a prop so the document outline stays correct in every context |
| `Table` | `<caption>`, `<th scope>`; collapses to a definition-list card layout below 768px |
| `Modal` | Focus trap, restore focus on close, Esc to dismiss, `aria-modal`, labelled by its heading |
| `Alert` | `role="alert"` for errors, `role="status"` for info; icon + text, never colour alone |
| `Badge` | Always carries text; colour is reinforcement only |
| `Tabs` | Full arrow-key roving tabindex per the WAI-ARIA pattern |
| `Nav` / `Sidebar` / `Header` | Landmark roles; skip-to-content link; `aria-current="page"` |
| `Breadcrumbs` | `<nav aria-label="Breadcrumb">` + ordered list |
| `Pagination` | Announces "Page 2 of 5" to assistive tech, not just arrows |
| `Spinner` | `aria-live` region announces what is loading, not just that something is |
| `EmptyState` | Heading, explanation, and a next action — never a bare "No data" |
| `ErrorState` | Plain-language message + retry, never a raw exception |
| `ConfirmDialog` | Destructive action named explicitly in the button ("Cancel appointment", not "OK") |
| `SkipLink` | First focusable element on every page |

### Clinical-safety primitives

Three components exist purely to keep brief §38 enforceable rather than aspirational:

```tsx
<ProvenanceBadge kind="ai-draft" />           // "AI-generated draft" + robot icon + amber
<ProvenanceBadge kind="clinician-approved" /> // "Approved by Dr S. Patel" + check + green
<ProvenanceBadge kind="patient-reported" />   // "Reported by patient" + person icon
<ProvenanceBadge kind="system-generated" />   // "Automatically calculated"
```

Any component rendering model output **must** accept and render a `ProvenanceBadge`. This is
enforced by a lint rule: importing from `features/ai/` without rendering a provenance badge in the
same file is an error. The rule is crude, and it catches the failure that matters.

```tsx
<PriorityFlag severity="EMERGENCY" />
// renders: ▲ icon + "Emergency" text + red background
// never: a red dot on its own
```

```tsx
<SyntheticDataNotice />
// "This screen shows synthetic demonstration data. It does not describe real patients."
// Rendered automatically whenever an API response carries meta.dataOrigin === "SYNTHETIC"
```

### Visual language

Following the NHS Digital Service Manual (C4), without using NHS branding:

| Token | Value | Use |
|---|---|---|
| `--color-primary` | `#005EB8` | Primary actions, links |
| `--color-primary-dark` | `#003087` | Hover, headers |
| `--color-emergency` | `#D5281B` | Emergency priority — always with an icon and label |
| `--color-urgent` | `#ED8B00` | Urgent priority |
| `--color-success` | `#007F3B` | Approved, confirmed |
| `--color-ai-draft` | `#7C2855` | AI-generated content chrome — deliberately not a status colour |
| Body text | 16px minimum, 1.5 line height | Brief §20 forbids tiny text |
| Focus ring | `#FFEB3B` on `#212B32`, 3px | High-visibility, per the Service Manual pattern |

`--color-ai-draft` is a distinct hue precisely so that "this is AI-generated" never reads as
"this is a warning" or "this is approved". Provenance and status are orthogonal, and sharing a
palette between them would conflate them.

**We do not use the NHS logo or NHS branding.** The identity is protected and this is not an NHS
service. The design system takes accessibility and layout guidance from the Service Manual only.

---

## 3. Mandatory UI states

Per brief §30, every page implements six states. This is a checklist item in code review, not a
suggestion.

| State | Pattern |
|---|---|
| Loading | Skeleton matching final layout — not a centred spinner that causes layout shift |
| Success | The content |
| Empty | `EmptyState` with a next action |
| Error | `ErrorState` with plain-language text + retry |
| Unauthorized | Redirect to login with `?next=`, preserving intent |
| Not found | 404 page with navigation back into the app |

Route-level `loading.tsx` and `error.tsx` files exist in every route group so a missing state is a
compile-time absence, not a runtime blank screen.

---

## 4. Key screens in detail

### 4.1 Booking wizard — `/appointments/book`

```
Step 1  Reason for visit          [department select · free-text reason]
   │                              if a triage result is attached, department is pre-filled
   │                              and a PriorityFlag is shown with a "change" link
   ▼
Step 2  Choose a date             [date range · availability calendar]
   │                              days with no availability are disabled AND labelled
   ▼
Step 3  Choose a time             [slot list, grouped by morning/afternoon]
   │                              selecting a slot calls POST /slots/{id}/hold
   │                              a countdown appears: "Slot held for 4:32"
   ▼
Step 4  Confirm                   [summary · confirm button]
   │                              POST /appointments with holdToken
   ▼
Confirmation                      reference APT-2026-000123, add-to-calendar, reminder notice
```

**Conflict recovery.** If step 4 returns `409 APPOINTMENT_CONFLICT`, the user is not dumped back to
step 1. They return to step 3 with the slot list refreshed, an `Alert` explaining that the slot was
taken, and their reason text preserved. Losing a user's input because of a race they did not cause
is the kind of small cruelty that makes people abandon a booking and phone the hospital instead.

If the hold countdown expires, an `Alert` appears with a "Get more time" button that re-holds the
slot if it is still free.

### 4.2 Staff queue — `/staff/queue`

Columns: Priority · Patient · NHS number · Reason · Waiting · Department · Risk · Actions

- Sorted by priority, then waiting time. Sort is explained in visible text above the table, because
  an unexplained ordering in a clinical queue is a safety issue.
- Priority renders as `<PriorityFlag>`: icon + word + colour.
- Risk renders as `<RiskIndicator>` with a `ProvenanceBadge` and a tooltip explaining what the
  score means and what it does not.
- Filters: department, priority, status, waiting-time threshold. Filter state lives in the URL so a
  clinician can share or bookmark a view.
- Below 1024px the table becomes stacked cards, priority-first. Not a horizontally scrolling table
  — a clinician on a ward tablet should not have to scroll sideways to see urgency.

### 4.3 AI document review — `/staff/documents/[id]/review`

The most safety-critical screen in the product.

```
┌────────────────────────────────────────────────────────────────────┐
│ Discharge letter — Alex Morgan (NHS 999 000 0018)                  │
│ [AI-generated draft]  Model: discharge-drafter-0.3.1  27 Aug 14:02 │
├────────────────────────────────────────────────────────────────────┤
│ ⓘ  This is an AI-generated draft. It is not part of the clinical   │
│    record. It becomes part of the record only when a clinician     │
│    approves it. Please read it in full before approving.           │
├──────────────────────────┬─────────────────────────────────────────┤
│  ORIGINAL AI DRAFT       │  YOUR VERSION                           │
│  (read-only, immutable)  │  (editable)                             │
│                          │                                         │
│  Mr Morgan was admitted  │  Mr Morgan was admitted on 24 August    │
│  on 24 August with…      │  with chest discomfort…                 │
│                          │                                         │
│  [changed text shown highlighted in the right pane]                │
├────────────────────────────────────────────────────────────────────┤
│ 3 changes made      [Reject] [Regenerate] [Save draft] [Approve ✓] │
└────────────────────────────────────────────────────────────────────┘
```

Design decisions and their reasons:

- **Side-by-side, original always visible.** The clinician can always see what the model actually
  produced. A single editable box hides the model's contribution the moment anyone types.
- **Approve is not the default focus** and is not pre-selected. Approval must be a deliberate act.
- **"3 changes made"** is shown because a draft approved with zero changes is the signature of
  automation bias, and making that visible is the cheapest available countermeasure.
- **Approve opens a `ConfirmDialog`** naming the patient and the document type. Approving the wrong
  patient's discharge letter is a realistic and serious error.
- After approval the page becomes read-only, showing `ProvenanceBadge kind="clinician-approved"`
  with the reviewer's name and timestamp.

### 4.4 Chatbot — `/chat`

Per brief §15.

```
┌──────────────────────────────────────────────────────────────┐
│ ⚠ If this is an emergency, call 999. This service cannot     │
│   help with emergencies.               [persistent, always]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────┐                  │
│  │ I have been having chest pain.         │  [patient]       │
│  └────────────────────────────────────────┘                  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ [AI assistant]                                          │ │
│  │ Chest pain can be serious and needs to be assessed by   │ │
│  │ a person, not by this service.                          │ │
│  │                                                          │ │
│  │ ▸ If the pain is severe, spreading to your arm or jaw,   │ │
│  │   or you feel breathless or sweaty — call 999 now.      │ │
│  │ ▸ Otherwise call NHS 111.                               │ │
│  │                                                          │ │
│  │ Sources: NHS chest pain guidance ↗                       │ │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ─── This conversation has been flagged for human review ─── │
│      A member of staff will look at it. Do not wait for a    │
│      reply if your symptoms are getting worse.               │
└──────────────────────────────────────────────────────────────┘
```

Rules the chat UI enforces:

- The 999 banner is always visible, never dismissible, never scrolled away.
- Every assistant message carries a `ProvenanceBadge kind="ai-draft"`.
- RAG answers show citations; an answer with no citation is visually marked as general information.
- On a red flag the input is **not** disabled — a patient must always be able to say more — but the
  escalation notice is inserted and pinned.
- Errors say "I could not answer that. Here is how to reach a person." A chatbot that fails
  silently in a health context is worse than one that is unavailable.
- Messages announce to screen readers via a polite `aria-live` region; the thread is a `<ol>`.

### 4.5 Admin dashboard — `/admin/dashboard`

KPI cards per brief §21: Total appointments · Waiting patients · Average wait · Bed occupancy ·
No-show rate · Patients flagged high readmission risk.

Charts: occupancy over time (line), wait time by department (bar), appointment status breakdown
(stacked bar — not a pie; comparing pie segments is harder and this is operational data people act
on), forecast vs actual (line with a visually distinct forecast segment).

Accessibility rules for every chart:

1. Wrapped in `<figure>` with a `<figcaption>` stating the takeaway in words.
2. `<title>` and `<desc>` inside the SVG.
3. A visually-hidden `<table>` carrying the same data, so the chart is fully available to a screen
   reader without any charting-library ARIA support.
4. Series distinguished by pattern or direct label as well as colour.
5. `<SyntheticDataNotice />` above the chart grid.

---

## 5. Copy rules (brief §38)

Forbidden in any user-facing string:

| Never | Instead |
|---|---|
| "The AI has diagnosed you with…" | "Based on what you have told us, this is how quickly we think you should be seen." |
| "You definitely have X" | "Your symptoms may be related to X. A clinician will assess this." |
| "You do not need to see a doctor" | "This does not look urgent. If you are worried or things change, contact your GP or NHS 111." |
| "The AI has approved…" | "Dr Patel approved this on 27 August." |
| "Diagnosis: …" | "Reported symptoms: …" |
| "Your risk score is 0.82" | "Higher than average likelihood of readmission — for clinical review, not a prediction about this patient." |

A lint rule scans `messages/*.json` for the forbidden phrasings. Copy safety is testable; treating
it as a matter of care alone means it degrades under deadline pressure.

---

## 6. Internationalisation (Sprint 3, C11)

- `next-intl`, locale segment `[locale]`, `en-GB` default.
- **No hard-coded strings in any patient-facing component.** ESLint `no-literal-string` is enabled
  for `app/[locale]/(public|patient)/**` and `features/**` from Sprint 1, so the Sprint 3 task is
  translation rather than extraction. Extracting strings retroactively across a finished portal is
  a multi-day job; preventing them costs nothing.
- Dates, times and numbers via `Intl`, never manual formatting.
- `<html lang>` follows the active locale.
- Staff and admin portals are English-only for MVP; clinical terminology translation carries a
  safety burden that this project cannot discharge.
- Second locale to be confirmed (ASSUMPTIONS open action D5). The mechanism is proved with a
  complete second locale file, not a partial one.

---

## 7. Responsive strategy (brief §5, FS-2.4)

Breakpoints: `sm 640` · `md 768` · `lg 1024` · `xl 1280`.

Explicitly **not** "shrink the desktop layout":

| Surface | Desktop | Mobile |
|---|---|---|
| Staff queue | Sortable table | Priority-first stacked cards |
| Patient record | Sidebar + tabbed panel | Accordion sections, one open at a time |
| Booking | Calendar grid + slot column | One step per screen, sticky action bar |
| Admin KPIs | 3-column grid | 1 column, ordered by importance not source order |
| Charts | Full detail | Reduced series count + link to the underlying table |
| Chat | Side panel | Full screen, input pinned above the keyboard |
| Modals | Centred dialog | Bottom sheet |

Touch targets are 44×44px minimum on all interactive elements — a clinician using a ward tablet
with gloves on is a real user of this system.
