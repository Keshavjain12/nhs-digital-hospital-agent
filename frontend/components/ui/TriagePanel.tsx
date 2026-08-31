"use client";

import type { TriageSummary } from "@/types/api";
import { cn } from "@/lib/cn";

/**
 * Visual language for triage output.
 *
 * The brief (§20, §38) requires AI-generated content to be visually distinguishable from
 * confirmed clinical fact, and forbids implying the system has diagnosed anyone. Two rules
 * follow from that and are enforced here rather than left to each caller:
 *
 * 1. Provenance is always stated in words - who or what produced this band, and whether a
 *    clinician has seen it. Never conveyed by styling alone.
 * 2. A band is never shown without its provenance. That is why the badge and the label are
 *    one component: a caller cannot render the colour and forget the caveat.
 */

export const BANDS: Record<
  string,
  { label: string; short: string; chip: string; border: string; icon: string }
> = {
  EMERGENCY: {
    label: "Emergency - needs immediate care",
    short: "Emergency",
    chip: "bg-nhs-red text-white",
    border: "border-nhs-red",
    icon: "!",
  },
  URGENT: {
    label: "Within 24 hours",
    short: "Within 24h",
    chip: "bg-nhs-orange text-nhs-black",
    border: "border-nhs-orange",
    icon: "!",
  },
  SOON: {
    label: "Within a week",
    short: "Within a week",
    chip: "bg-nhs-blue text-white",
    border: "border-nhs-blue",
    icon: "i",
  },
  ROUTINE: {
    label: "Routine",
    short: "Routine",
    chip: "bg-nhs-mid-grey text-white",
    border: "border-nhs-mid-grey",
    icon: "i",
  },
  SELF_CARE: {
    label: "Self care",
    short: "Self care",
    chip: "bg-nhs-mid-grey text-white",
    border: "border-nhs-mid-grey",
    icon: "i",
  },
};

const PROVENANCE: Record<string, { text: string; tone: string }> = {
  PENDING_REVIEW: {
    text: "Automated suggestion - not yet reviewed by a clinician",
    tone: "text-nhs-dark-grey",
  },
  CLINICIAN_CONFIRMED: {
    text: "Confirmed by a clinician",
    tone: "text-nhs-green",
  },
  CLINICIAN_OVERRIDDEN: {
    text: "Changed by a clinician",
    tone: "text-nhs-purple",
  },
};

/** Compact band chip for a table cell. Always paired with its provenance line. */
export function TriageBadge({ triage }: { triage: TriageSummary }) {
  const band = BANDS[triage.effectiveSeverity] ?? BANDS.SOON;
  const provenance = PROVENANCE[triage.reviewStatus] ?? PROVENANCE.PENDING_REVIEW;

  return (
    <div className="flex flex-col gap-1">
      <span
        className={cn(
          "inline-flex w-fit items-center gap-1 px-2 py-0.5 text-sm font-bold",
          band.chip,
        )}
      >
        <span aria-hidden="true">{band.icon}</span>
        {band.short}
      </span>
      {/* Never colour alone, and never a band without its provenance. */}
      <span className={cn("text-xs", provenance.tone)}>{provenance.text}</span>
    </div>
  );
}

/** Full panel for a patient record or the review queue. */
export function TriagePanel({
  triage,
  children,
}: {
  triage: TriageSummary;
  children?: React.ReactNode;
}) {
  const engineBand = BANDS[triage.engineSeverity] ?? BANDS.SOON;
  const effectiveBand = BANDS[triage.effectiveSeverity] ?? BANDS.SOON;
  const provenance = PROVENANCE[triage.reviewStatus] ?? PROVENANCE.PENDING_REVIEW;
  const wasOverridden = triage.reviewStatus === "CLINICIAN_OVERRIDDEN";

  return (
    <section className={cn("border-4 bg-white p-5", effectiveBand.border)}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-nhs-dark-grey">
            Suggested urgency
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={cn(
                "inline-flex size-8 items-center justify-center rounded-full font-bold",
                effectiveBand.chip,
              )}
              aria-hidden="true"
            >
              {effectiveBand.icon}
            </span>
            <strong className="text-2xl">{effectiveBand.label}</strong>
          </div>
        </div>
        <span className={cn("text-sm font-bold", provenance.tone)}>{provenance.text}</span>
      </div>

      {wasOverridden && (
        // The engine's original band stays visible next to the clinician's. Showing only
        // the final answer would erase the fact that a judgement was made.
        <div className="mb-4 border-l-8 border-nhs-purple bg-[#f7f9fa] p-3">
          <p className="mb-1 text-sm">
            The automated check suggested <strong>{engineBand.short}</strong>. A clinician
            changed this to <strong>{effectiveBand.short}</strong>.
          </p>
          {triage.clinicianNote && (
            <p className="text-sm text-nhs-dark-grey">
              Reason given: {triage.clinicianNote}
            </p>
          )}
        </div>
      )}

      <p className="mb-4">{triage.recommendedAction}</p>

      {triage.redFlags && triage.redFlags.length > 0 && (
        <div className="mb-4">
          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-nhs-dark-grey">
            Matched safety rules
          </p>
          <ul className="flex flex-wrap gap-2">
            {triage.redFlags.map((flag) => (
              <li
                key={flag}
                className="border-2 border-nhs-red px-2 py-0.5 font-mono text-sm text-nhs-red"
              >
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      {children}

      <div className="mt-4 border-t border-nhs-pale-grey pt-3 text-sm text-nhs-dark-grey">
        <p>
          Produced by{" "}
          <span className="font-mono">
            {triage.engine} {triage.engineVersion}
          </span>
          {triage.confidence === null
            ? " · no confidence score is reported for a rule-based check"
            : ` · confidence ${Math.round(triage.confidence * 100)}%`}
        </p>
        <p className="mt-1">
          <strong>This is a suggestion, not a diagnosis.</strong> It does not decide the
          patient&apos;s care.
        </p>
      </div>
    </section>
  );
}
