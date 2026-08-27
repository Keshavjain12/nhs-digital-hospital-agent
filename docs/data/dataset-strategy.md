# Dataset Strategy and Gap Analysis

> **Status of brief §25 ("Dataset analysis first"): BLOCKED — see §1.**
> This document replaces the requested dataset audit with the honest equivalent:
> what exists, what does not, and what we will generate instead.

---

## 1. Audit finding: there is no dataset

An inspection of the workspace on 2026-08-27 found three files, all documents:

| File | Type | Contents |
|---|---|---|
| `KeshavRajJain_..._Project_Analysis_Report.docx` | Prose report | Narrative analysis of the plan. No data. |
| `NHS_Digital_Hospital_Agent_2Month_Task_Plan (1).pdf` | Prose plan | 112 tasks across 6 domains. No data. |
| `NHS_Hospital_Agent_Dataset_Guide_6286.pdf` | Prose guide | A tiered list of **where to obtain** data. No data. |

There are no `.csv`, `.json`, `.parquet`, `.xlsx`, `.db` or `.sql` files anywhere in the tree.

The requested audit table therefore cannot be filled in:

```
Dataset
├── File          -> none present
├── Size          -> n/a
├── Rows          -> n/a
├── Columns       -> n/a
├── Missing values-> n/a
├── Duplicates    -> n/a
└── Relationships -> n/a
```

Per brief §7 ("If a required field does not exist: DO NOT INVENT DATA AND PRESENT IT AS REAL"),
the correct response is to declare the gap and propose a labelled synthetic substitute.
That is what the rest of this document does.

---

## 2. What the Dataset Guide actually authorises

The guide defines four tiers. Only Tiers 1 and 2 are available to this project without
governance approval that does not exist (Dataset Guide, "Golden rule"; ASSUMPTIONS B5).

| Tier | Availability to us | Verdict |
|---|---|---|
| **Tier 1** — Synthea, NHS England synthetic sets, CPRD dummy | Open, no approval | **Use. This is our primary source.** |
| **Tier 2** — HES aggregate, NHS Open Data, OpenPrescribing, ONS, SNOMED CT via TRUD, NHS Data Dictionary | Open / free licence | **Use for reference, terminology and realistic KPI baselines.** |
| **Tier 3** — Real/pseudonymised NHS data via DARS | Weeks-to-months approval; requires a legal basis we do not have | **Out of scope. Do not pursue.** |
| **Tier 4** — MIMIC-IV, i2b2/n2c2, HuggingFace clinical sets | Credentialed access; US data | **Out of scope for Full Stack.** May be relevant to the AI/ML domain for NLP prototyping only. |

**SNOMED CT note.** The UK Edition is free *for NHS-affiliated use* via a TRUD licence. A student
project may not qualify. Mitigation: the schema stores SNOMED codes as plain strings and ships a
small hand-curated subset of well-known concept IDs for demo purposes only. We do **not** bundle or
redistribute the full terminology release.

---

## 3. Primary source recommendation: Synthea

**Recommendation (ASSUMPTIONS P8): use Synthea as the canonical clinical data source.**

Why Synthea over the other Tier 1 options:

- It emits **FHIR R4 bundles directly**, which serves requirement C6 without us hand-writing a mapper.
- It is fully open source with no registration, unlike the NHS England synthetic releases which
  require navigating a request process of uncertain duration.
- Its output volume is configurable, so we can generate 200 patients for local dev and 20,000 for
  load testing (Task Plan, Python S4) from the same tool.
- Population parameters are tunable, which lets us approximate a UK district general hospital
  catchment rather than the US default.

### What Synthea gives us

| FHIR resource | Maps to our table | Populated? |
|---|---|---|
| `Patient` | `patients` | Yes — demographics, birth date, address, language |
| `Encounter` | `encounters` | Yes — class, period, reason, provider |
| `Condition` | `conditions` | Yes — SNOMED-coded |
| `Observation` | `observations` | Yes — LOINC-coded vitals and labs |
| `MedicationRequest` | `medication_requests` | Yes — RxNorm-coded |
| `AllergyIntolerance` | `allergies` | Yes |
| `Practitioner` / `Organization` | `staff`, `departments` | Partial — names and roles only |

### What Synthea does NOT give us

This is the critical part. Synthea models a **patient's lifetime history**, not a **hospital's
operations**. It has no concept of a future appointment.

| Required by the brief | Present in Synthea? | Consequence |
|---|---|---|
| Appointment slots / clinic capacity | **No** | Booking engine has no source data → BLOCKER B2 |
| Clinician availability rosters | **No** | Scheduling engine has no source data → BLOCKER B2 |
| Appointment status (booked/cancelled/DNA) | **No** | No-show model has no target variable |
| Triage severity labels | **No** | Triage classifier has no ground truth → BLOCKER B3 |
| Live bed occupancy | **No** | Admin occupancy dashboard has no source → BLOCKER B4 |
| Waiting times (referral-to-treatment) | **No** | Admin wait-time dashboard has no source → BLOCKER B4 |
| Department queue state | **No** | Staff queue has no source data |
| NHS numbers | **No** (emits US SSN/MRN) | Requires a UK identity overlay |
| UK addresses / postcodes | **No** (US addresses) | Requires a UK identity overlay |

**Roughly half of what this project needs is operational data that no Tier 1 or Tier 2 source
provides.** That is the single most important finding of this analysis, and it is why the
generator in §4 is not optional convenience — it is a prerequisite for the core module.

---

## 4. Development-only synthetic operational generator

To fill the §3 gaps we will build `backend/scripts/generate_operational_data.py`.

**Everything it produces is explicitly labelled synthetic**, at three levels:

1. Every generated row carries `data_origin = 'SYNTHETIC'` (an enum column on affected tables).
2. Every API response derived from it includes `"dataOrigin": "SYNTHETIC"` in its envelope.
3. Every UI surface backed by it renders a `<SyntheticDataNotice />` component.

There is no code path by which synthetic data can be presented as real. That is a deliberate
structural guarantee, not a convention.

### 4.1 UK identity overlay

| Field | Generation rule | Note |
|---|---|---|
| `nhs_number` | Generated in the **9990000000–9999999999 test range**, checksum-valid under Modulus 11 | The 999-prefixed range is conventionally reserved for test/synthetic use. **Verify against the NHS Data Dictionary before relying on this claim** — recorded as a to-do, not a fact. |
| `postcode` | Sampled from a small fixed list of valid-format non-real postcodes | We do not geocode to real addresses |
| `phone_e164` | Ofcom **drama range** `+44 7700 900xxx` | Reserved for fiction; cannot dial a real person |
| `email` | `*@example.test` | RFC 2606 reserved TLD; cannot deliver mail |

The drama-range and `.test` choices matter: a bug in the notification service that actually sends
a reminder cannot reach a real human being. Safety by construction.

### 4.2 Operational entities generated

| Entity | Generation approach |
|---|---|
| `departments` | Fixed list: A&E, General Medicine, Cardiology, Orthopaedics, Paediatrics, Outpatients, Radiology |
| `staff` | ~40 clinicians distributed across departments, `staff_code` = `SYN-####` |
| `availability_rules` | Weekday recurring patterns per clinician, e.g. Mon/Wed 09:00–17:00, 15-min slots |
| `appointment_slots` | Materialised from availability rules for a rolling 12-week horizon |
| `appointments` | Historic slots back-filled at ~78% booked, of which ~11% marked `DID_NOT_ATTEND` |
| `beds` / `wards` | ~180 beds across 6 wards |
| `bed_occupancy_snapshots` | Hourly snapshots with a diurnal + weekday seasonality curve |

### 4.3 Calibrating the synthetic rates against Tier 2 open data

The 78% booked / 11% DNA figures above are **placeholders and must not be quoted as findings.**
Before Sprint 2 we calibrate them against real published aggregates from the NHS England Open Data
Portal (Tier 2) — outpatient DNA rates and RTT waiting-time distributions are published openly.

This gives us the honest best-of-both position:

> The *shape* of the data is calibrated to published NHS aggregate statistics.
> The *records* are entirely synthetic and describe no real person.

Calibration is a **Data Science domain** task (Task Plan S1: "Audit available datasets… for quality
and gaps"). Full Stack consumes whatever rates they land on via config, not hard-coded constants.

---

## 5. Field → Backend → API → Frontend mapping

Only mappings actually supported by a source are listed. Origin column:
**SYN-C** = Synthea clinical · **SYN-O** = our operational generator · **DERIVED** = computed · **USER** = entered in-app.

| Source field | Origin | Backend model | API | Frontend component |
|---|---|---|---|---|
| `Patient.name` | SYN-C | `patients.given_name/family_name` | `GET /patients/{id}` | `PatientHeader` |
| `Patient.birthDate` | SYN-C | `patients.date_of_birth` | `GET /patients/{id}` | `PatientHeader`, age derived |
| `Patient.communication.language` | SYN-C | `patients.preferred_language` | `GET /me` | i18n locale default, `InterpreterFlag` |
| *(synthesised)* NHS number | SYN-O | `patients.nhs_number` | `GET /patients/{id}` | `NhsNumberDisplay` (3-3-4 spacing) |
| `Encounter.period.start` | SYN-C | `encounters.period_start` | `GET /patients/{id}/encounters` | `EncounterTimeline` |
| `Encounter.class` | SYN-C | `encounters.class` | `GET /patients/{id}/encounters` | `EncounterTypeBadge` |
| `Condition.code` (SNOMED) | SYN-C | `conditions.snomed_code/display` | `GET /patients/{id}/conditions` | `ConditionList` |
| `Observation.valueQuantity` | SYN-C | `observations.value_quantity/unit` | `GET /patients/{id}/observations` | `ObservationTable`, `VitalsSparkline` |
| `MedicationRequest.medication` | SYN-C | `medication_requests.display` | `GET /patients/{id}/medications` | `MedicationList` |
| slot start/end | SYN-O | `appointment_slots.starts_at/ends_at` | `GET /slots` | `SlotPicker`, `AppointmentCalendar` |
| slot department | SYN-O | `appointment_slots.department_id` | `GET /slots?departmentId=` | `DepartmentFilter` |
| appointment status | SYN-O / USER | `appointments.status` | `GET /appointments` | `AppointmentStatusBadge` |
| appointment DNA flag | SYN-O | `appointments.status='DID_NOT_ATTEND'` | `GET /analytics/kpis` | `NoShowRateCard` |
| bed occupancy snapshot | SYN-O | `bed_occupancy_snapshots` | `GET /analytics/occupancy` | `OccupancyChart`, `BedOccupancyCard` |
| wait time | DERIVED | from `encounters` arrival→seen | `GET /analytics/waiting-times` | `WaitTimeChart` |
| symptom free text | USER | `chat_messages.content_redacted` | `POST /chat/sessions/{id}/messages` | `ChatThread` |
| triage severity | DERIVED | `triage_results.severity` | `POST /triage/assess` | `TriageResultCard`, `PriorityFlag` |
| readmission risk | DERIVED | `risk_scores` | `GET /patients/{id}/risk-scores` | `RiskIndicator` |

### Fields the UI needs that have no source at all

Per brief §7 these are declared, not invented:

| UI need | Status | Resolution |
|---|---|---|
| Patient photo | No source | Not implemented. Initials avatar only. |
| Clinician sub-specialty | No source | Free-text on `staff`, seeded from a fixed list, marked SYN-O |
| Referral letters | No source | Out of scope for MVP |
| Real-time A&E queue position | No source | Derived from `encounters` with `class='EMER'` and open status; labelled as derived, not measured |

---

## 6. Data protection posture for synthetic data

Even though no record describes a real person, we apply production discipline throughout, because
the whole point of the exercise is that the architecture would survive real data:

- Free-text clinical fields pass through PII redaction before being written to `chat_messages`
  (Task Plan, Gen AI S2: "conversation logging with PII redaction").
- `audit_logs.metadata` never contains clinical content — only resource type and identifier.
- Data retention config exists from day one, defaulting to a short dev-mode window.
- `patients.deleted_at` supports soft delete for right-to-erasure workflows.

---

## 7. Open actions

| # | Action | Owner | Sprint |
|---|---|---|---|
| D1 | Confirm Synthea is approved as the primary source | You | S1 |
| D2 | Verify the 999-range NHS number test convention against the NHS Data Dictionary | Full Stack | S1 |
| D3 | Calibrate DNA rate and wait-time distributions against NHS Open Data | Data Science | S1 |
| D4 | Confirm whether a TRUD SNOMED licence is obtainable for this project | You | S1 |
| D5 | Agree the second locale for i18n | You | S3 |
