"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import type { FormEvent } from "react";

import { Alert, Badge, Button, Card, TriagePanel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { BreakglassResponse, PatientDetailResponse } from "@/types/api";
import { formatDate, languageName, UK_TIME_ZONE } from "@/lib/format";

export default function PatientRecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  const { data, isPending, error } = useQuery({
    queryKey: ["patient", id],
    queryFn: () => api.get<PatientDetailResponse>(`/patients/${id}`),
  });

  const breakglass = useMutation({
    mutationFn: (justification: string) =>
      api.post<BreakglassResponse>(`/patients/${id}/breakglass`, { reason: justification }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["patient", id] }),
    onError: (caught) =>
      setReasonError(
        caught instanceof ApiError ? caught.message : "Could not grant emergency access.",
      ),
  });

  function requestBreakglass(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setReasonError(null);

    if (reason.trim().length < 20) {
      setReasonError(
        "Give a reason of at least 20 characters explaining why you need this record.",
      );
      return;
    }
    breakglass.mutate(reason);
  }

  // 403 here means "no care relationship", which is a recoverable state offering
  // emergency access - not a dead end. Any other failure is a genuine error.
  const isBlocked = error instanceof ApiError && error.status === 403;

  if (isPending) {
    return (
      <p role="status" aria-live="polite">
        Loading patient record…
      </p>
    );
  }

  if (error && !isBlocked) {
    return (
      <>
        <Alert tone="error" title="Could not open this record" focusOnMount>
          {error.message}
        </Alert>
        <Link href="/staff/queue">Back to patients</Link>
      </>
    );
  }

  if (isBlocked) {
    return (
      <>
        <h1 className="mb-6 text-4xl font-bold">Record not available to you</h1>

        <Alert tone="warning" title="You are not in this patient's care team">
          {error.message} You can still open the record in an emergency, but doing so is
          recorded against your account and reviewed.
        </Alert>

        <Card title="Request emergency access" headingLevel={2}>
          <form onSubmit={requestBreakglass} noValidate>
            <label htmlFor="breakglass-reason" className="mb-1 block font-bold">
              Why do you need this record?
              <span className="ml-1 font-normal text-nhs-dark-grey">(required)</span>
            </label>
            <p id="breakglass-hint" className="mb-2 text-nhs-dark-grey">
              Be specific. This is stored permanently and reviewed by your organisation.
              &quot;Urgent&quot; on its own is not a reason.
            </p>
            {reasonError && (
              <p className="mb-2 font-bold text-nhs-red">
                <span className="sr-only">Error: </span>
                {reasonError}
              </p>
            )}
            <textarea
              id="breakglass-reason"
              name="reason"
              rows={4}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              aria-describedby="breakglass-hint"
              aria-invalid={reasonError ? true : undefined}
              className="mb-4 block w-full border-2 border-nhs-black p-3"
            />
            <div className="flex flex-wrap gap-4">
              <Button type="submit" variant="warning" loading={breakglass.isPending}>
                Open record with emergency access
              </Button>
              <Link href="/staff/queue" className="self-center">
                Cancel
              </Link>
            </div>
          </form>
        </Card>
      </>
    );
  }

  if (!data) return null;

  const { patient, access } = data;

  return (
    <>
      <p className="mb-4">
        <Link href="/staff/queue">Back to patients</Link>
      </p>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">
            {patient.givenName} {patient.familyName}
          </h1>
          <p className="text-nhs-dark-grey">
            Born {formatDate(patient.dateOfBirth)} · Age{" "}
            {patient.age}
            {patient.nhsNumber && (
              <>
                {" "}
                · NHS number{" "}
                <span className="font-mono">
                  {patient.nhsNumber.slice(0, 3)} {patient.nhsNumber.slice(3, 6)}{" "}
                  {patient.nhsNumber.slice(6)}
                </span>
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {access.basis === "CARE_ASSIGNMENT" && (
            <Badge tone="success" icon="✓">
              Your patient
            </Badge>
          )}
          {access.basis === "BREAKGLASS" && (
            <Badge tone="attention" icon="⚠">
              Emergency access
            </Badge>
          )}
          {patient.dataOrigin === "SYNTHETIC" && (
            <Badge tone="info" icon="i">
              Synthetic record
            </Badge>
          )}
        </div>
      </div>

      {access.basis === "BREAKGLASS" && (
        <Alert tone="warning" title="You are viewing this record under emergency access">
          This access has been logged against your account and will be reviewed.
          {access.expiresAt && (
            <>
              {" "}
              It expires at{" "}
              {new Date(access.expiresAt).toLocaleTimeString("en-GB", {
                timeZone: UK_TIME_ZONE,
                hour: "2-digit",
                minute: "2-digit",
              })}
              .
            </>
          )}
        </Alert>
      )}

      {patient.interpreterNeeded && (
        <Alert tone="info" title="Interpreter required">
          This patient has recorded a need for an interpreter. Preferred language:{" "}
          <strong>{languageName(patient.preferredLanguage)}</strong>. Arrange interpretation before the
          consultation.
        </Alert>
      )}

      {data.latestTriage && (
        <div className="mb-6">
          <TriagePanel triage={data.latestTriage} />
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Demographics">
          <dl className="space-y-3">
            <div>
              <dt className="font-bold">Date of birth</dt>
              <dd>{formatDate(patient.dateOfBirth)}</dd>
            </div>
            <div>
              <dt className="font-bold">Sex at birth</dt>
              <dd>{patient.sexAtBirth ?? "Not recorded"}</dd>
            </div>
            <div>
              <dt className="font-bold">Preferred language</dt>
              <dd>{languageName(patient.preferredLanguage)}</dd>
            </div>
          </dl>
        </Card>

        <Card title="Contact">
          <dl className="space-y-3">
            <div>
              <dt className="font-bold">Telephone</dt>
              <dd>{patient.phoneE164 ?? "Not recorded"}</dd>
            </div>
            <div>
              <dt className="font-bold">Email</dt>
              <dd className="break-words">{patient.email ?? "Not recorded"}</dd>
            </div>
            <div>
              <dt className="font-bold">Address</dt>
              <dd>
                {patient.addressLine1 ? (
                  <>
                    {patient.addressLine1}
                    <br />
                    {patient.city} {patient.postcode}
                  </>
                ) : (
                  "Not recorded"
                )}
              </dd>
            </div>
          </dl>
        </Card>

        <Card title="Encounters">
          {/* Honest empty state. No encounter data exists for this service, and inventing
              a clinical history on a hospital screen would be far worse than a gap. */}
          <Alert tone="info" title="Not part of this build">
            Encounter history is not recorded by this service, so there is nothing to show.
          </Alert>
        </Card>

        <Card title="Clinical summary">
          <Alert tone="info" title="Not part of this build">
            AI-drafted summaries have not been built. The note summariser belongs to the
            Gen AI workstream; if it is added, every draft must be clearly labelled and
            approved by a clinician before it forms part of the record.
          </Alert>
        </Card>
      </div>
    </>
  );
}
