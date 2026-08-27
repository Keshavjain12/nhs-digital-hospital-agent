# Sprint 1 wireframes

Deliverable for Full Stack Sprint 1 task 1 (*Create UX wireframes: patient portal, staff
dashboard, chatbot widget*).

**Canvas:** https://claude.ai/code/artifact/de52e4d6-fc11-4623-b101-28756bc4ea9d

## Files

`*.dc.html` are the artboard sources; `canvas.json` is the layout (pages, positions,
annotations). `nhs-hospital-agent-wireframes.html` is the assembled canvas that was
published - it is generated, so edit the sources and re-seed rather than editing it.

## What is drawn

| Page | Screens |
|---|---|
| Patient journey | Dashboard, symptom-check chat, triage result, slot picker, booking outcome |
| Clinical | Patient queue, emergency access, AI discharge-letter review |
| Operations & patterns | Admin dashboard, model monitoring and override, the six UI states |

Most of these are **not yet built**. The wireframes exist to guide Sprint 2-3, which is why
they lean on the screens still to come rather than re-drawing the ones already shipped.

## Fidelity

They use the real design tokens from `frontend/app/globals.css` and the component anatomy
from `frontend/components/ui/`, so they read as the same product and translate directly
into markup. They are not pixel specifications: spacing and copy are indicative.

## Content warning

Every clinical detail shown is invented for illustration - Margaret Whitfield's chest
infection, the "82% approved unchanged" figure, the occupancy bars. None of it is measured
and none describes a real person. Do not quote any figure from these wireframes as a
finding.
