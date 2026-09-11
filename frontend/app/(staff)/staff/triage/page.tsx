"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert, BANDS, Button, Card, Dialog, TriagePanel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { TriageQueueItemSchema, TriageQueueResponse, TriageReviewResponse } from "@/types/api";
import { UK_TIME_ZONE } from "@/lib/format";

const when = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** Bands a clinician can choose when overriding, most urgent first. */
const CHOOSABLE = ["EMERGENCY", "URGENT", "SOON", "ROUTINE", "SELF_CARE"] as const;

export default function TriageReviewPage() {
  const queryClient = useQueryClient();
  const [onlyPending, setOnlyPending] = useState(true);
  const [reviewing, setReviewing] = useState<TriageQueueItemSchema | null>(null);
  const [disagreeing, setDisagreeing] = useState(false);
  const [band, setBand] = useState<string>("SOON");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const queue = useQuery({
    queryKey: ["triage-queue", onlyPending],
    queryFn: () => api.get<TriageQueueResponse>(`/triage?onlyPending=${onlyPending}`),
  });

  const review = useMutation({
    mutationFn: (input: { id: string; agrees: boolean }) =>
      api.post<TriageReviewResponse>(`/triage/${input.id}/review`, {
        agrees: input.agrees,
        clinicianSeverity: input.agrees ? null : band,
        note: note.trim() || null,
      }),
    onSuccess: async () => {
      closeDialog();
      await queryClient.invalidateQueries({ queryKey: ["triage-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (error) =>
      setFormError(
        error instanceof ApiError ? error.message : "We could not record that decision.",
      ),
  });

  function closeDialog() {
    setReviewing(null);
    setDisagreeing(false);
    setNote("");
    setBand("SOON");
    setFormError(null);
  }

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Triage review</h1>
      <p className="mb-6 max-w-3xl text-nhs-dark-grey">
        Automated urgency suggestions awaiting a clinical decision. Confirming or changing
        one is recorded against your name. The original automated result is always kept.
      </p>

      <Alert tone="info" title="These are suggestions, not decisions">
        Each band was produced by an automated symptom check. None of them has decided a
        patient&apos;s care, and none is a diagnosis.
      </Alert>

      <div className="mb-6">
        <label className="inline-flex items-center gap-3">
          <input
            type="checkbox"
            checked={onlyPending}
            onChange={(event) => setOnlyPending(event.target.checked)}
            className="size-6 border-2 border-nhs-black"
          />
          Show only results awaiting review
        </label>
      </div>

      {queue.isPending && (
        <p role="status" aria-live="polite">
          Loading triage results…
        </p>
      )}

      {queue.error && (
        <Alert tone="error" title="Could not load triage results" focusOnMount>
          {queue.error.message}
        </Alert>
      )}

      {queue.data?.items.length === 0 && (
        <Card title="Nothing to review">
          <p>
            {onlyPending
              ? "Every automated result has been reviewed."
              : "No symptom checks have been completed yet."}
          </p>
        </Card>
      )}

      <ul className="flex flex-col gap-6">
        {queue.data?.items.map((item) => (
          <li key={item.triage.id}>
            <TriagePanel triage={item.triage}>
              <div className="border-t border-nhs-pale-grey pt-3">
                <p className="mb-1">
                  <Link href={`/staff/patients/${item.patientId}`} className="font-bold">
                    {item.patientName}
                  </Link>{" "}
                  {item.patientNhsNumber && (
                    <span className="font-mono text-sm text-nhs-dark-grey">
                      {item.patientNhsNumber.slice(0, 3)} {item.patientNhsNumber.slice(3, 6)}{" "}
                      {item.patientNhsNumber.slice(6)}
                    </span>
                  )}
                </p>
                <p className="text-sm text-nhs-dark-grey">
                  Checked {when.format(new Date(item.triage.createdAt))}
                </p>

                {item.triage.reviewStatus === "PENDING_REVIEW" && (
                  <div className="mt-3 flex flex-wrap gap-3">
                    <Button
                      onClick={() => {
                        setReviewing(item);
                        setDisagreeing(false);
                      }}
                    >
                      Review this
                    </Button>
                  </div>
                )}
              </div>
            </TriagePanel>
          </li>
        ))}
      </ul>

      <Dialog
        open={reviewing !== null}
        onClose={closeDialog}
        title="Record your decision"
        actions={
          <>
            <Button variant="secondary" onClick={closeDialog}>
              Cancel
            </Button>
            {disagreeing ? (
              <Button
                variant="warning"
                loading={review.isPending}
                loadingText="Recording"
                onClick={() =>
                  reviewing && review.mutate({ id: reviewing.triage.id, agrees: false })
                }
              >
                Record my decision
              </Button>
            ) : (
              <Button
                loading={review.isPending}
                loadingText="Recording"
                onClick={() =>
                  reviewing && review.mutate({ id: reviewing.triage.id, agrees: true })
                }
              >
                Confirm this urgency
              </Button>
            )}
          </>
        }
      >
        {reviewing && (
          <>
            <p className="mb-3">
              <strong>{reviewing.patientName}</strong> · automated check suggested{" "}
              <strong>{BANDS[reviewing.triage.engineSeverity]?.short}</strong>.
            </p>

            {formError && (
              <Alert tone="error" title="Could not record that">
                {formError}
              </Alert>
            )}

            {!disagreeing ? (
              <p className="mb-4">
                Confirming records that you agree with this urgency.{" "}
                <button
                  type="button"
                  onClick={() => setDisagreeing(true)}
                  className="font-bold text-nhs-blue underline"
                >
                  I disagree with this urgency
                </button>
              </p>
            ) : (
              <>
                <div className="mb-4">
                  <label htmlFor="band" className="mb-1 block font-bold">
                    What urgency is correct?
                  </label>
                  <select
                    id="band"
                    value={band}
                    onChange={(event) => setBand(event.target.value)}
                    className="min-h-[44px] w-full border-2 border-nhs-black px-3 py-2"
                  >
                    {CHOOSABLE.map((option) => (
                      <option key={option} value={option}>
                        {BANDS[option]?.label ?? option}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-2">
                  <label htmlFor="note" className="mb-1 block font-bold">
                    Why? <span className="font-normal text-nhs-dark-grey">(required)</span>
                  </label>
                  <p id="note-hint" className="mb-2 text-sm text-nhs-dark-grey">
                    Stored permanently alongside the original automated result. This is what
                    an incident review would read.
                  </p>
                  <textarea
                    id="note"
                    rows={3}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    aria-describedby="note-hint"
                    className="w-full border-2 border-nhs-black p-3"
                  />
                </div>

                <p className="text-sm text-nhs-dark-grey">
                  The automated result stays on the record. Your decision is stored beside
                  it, not in place of it.
                </p>
              </>
            )}
          </>
        )}
      </Dialog>
    </>
  );
}
