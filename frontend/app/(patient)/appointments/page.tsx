"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Badge, Button, ButtonLink, Card, Dialog } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import type { AppointmentItem, AppointmentListResponse } from "@/types/api";
import { UK_TIME_ZONE } from "@/lib/format";

const when = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

function StatusBadge({ status }: { status: string }) {
  const t = useT();

  // Icon and word as well as colour, so status is never carried by colour alone.
  const known: Record<string, { tone: "success" | "neutral" | "attention"; icon: string }> = {
    BOOKED: { tone: "success", icon: "✓" },
    CANCELLED: { tone: "neutral", icon: "○" },
    DID_NOT_ATTEND: { tone: "attention", icon: "!" },
  };

  const match = known[status];
  if (match) {
    return (
      <Badge tone={match.tone} icon={match.icon}>
        {t(`appointments.status.${status}` as MessageKey)}
      </Badge>
    );
  }

  // An in-progress status the catalogue does not name yet. Shown readably rather than
  // as a raw enum, and never as a blank.
  return (
    <Badge tone="info" icon="●">
      {status.replace(/_/g, " ").toLowerCase()}
    </Badge>
  );
}

function AppointmentsList() {
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const t = useT();
  const [includePast, setIncludePast] = useState(false);
  const [cancelling, setCancelling] = useState<AppointmentItem | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const bookedReference = params.get("booked");
  const rescheduledReference = params.get("rescheduled");

  const appointments = useQuery({
    queryKey: ["appointments", includePast],
    queryFn: () =>
      api.get<AppointmentListResponse>(`/appointments?includePast=${includePast}`),
  });

  const cancel = useMutation({
    mutationFn: (appointment: AppointmentItem) =>
      api.post(`/appointments/${appointment.id}/cancel`, { reason: null }),
    onSuccess: async () => {
      setCancelling(null);
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["appointments"] });
    },
    onError: (error) =>
      setActionError(
        error instanceof ApiError ? error.message : "We could not cancel that appointment.",
      ),
  });

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="mb-2 text-4xl font-bold">{t("appointments.title")}</h1>
          <p className="text-nhs-dark-grey">{t("appointments.intro")}</p>
        </div>
        <ButtonLink href="/appointments/book" size="lg">
          {t("appointments.book")}
        </ButtonLink>
      </div>

      {bookedReference && (
        <Alert tone="success" title={t("appointments.booked.title")}>
          {t("appointments.booked.body", { reference: bookedReference })}
        </Alert>
      )}

      {/* A reschedule issues a new reference and cancels the old time. Saying so plainly
          stops the patient wondering whether they now hold two appointments. */}
      {rescheduledReference && (
        <Alert tone="success" title={t("appointments.rescheduled.title")}>
          {t("appointments.rescheduled.body", { reference: rescheduledReference })}
        </Alert>
      )}

      {actionError && (
        <Alert tone="error" title={t("common.somethingWentWrong")} focusOnMount>
          {actionError}
        </Alert>
      )}

      <div className="mb-6">
        <label className="inline-flex items-center gap-3 text-base">
          <input
            type="checkbox"
            checked={includePast}
            onChange={(event) => setIncludePast(event.target.checked)}
            className="size-6 border-2 border-nhs-black"
          />
          {t("appointments.includePast")}
        </label>
      </div>

      {appointments.isPending && (
        <p role="status" aria-live="polite">
          {t("common.loading")}
        </p>
      )}

      {appointments.error && (
        <Alert tone="error" title={t("common.somethingWentWrong")} focusOnMount>
          {appointments.error.message}
        </Alert>
      )}

      {appointments.data?.items.length === 0 && (
        <Card title={t("appointments.none.title")}>
          <p className="mb-4">
            {includePast ? t("appointments.none.any") : t("appointments.none.upcoming")}
          </p>
          <Link href="/appointments/book" className="font-bold">
            {t("appointments.book")}
          </Link>
        </Card>
      )}

      <ul className="flex flex-col gap-4">
        {appointments.data?.items.map((appointment) => (
          <li
            key={appointment.id}
            className="border border-nhs-mid-grey bg-white p-5"
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xl font-bold">{when.format(new Date(appointment.startsAt))}</p>
                <p className="text-nhs-dark-grey">
                  {appointment.departmentName} · {appointment.siteName}
                </p>
              </div>
              <StatusBadge status={appointment.status} />
            </div>

            <dl className="mb-4 grid gap-2 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-bold text-nhs-dark-grey">{t("appointments.reference")}</dt>
                <dd className="font-mono">{appointment.reference}</dd>
              </div>
              {appointment.reasonText && (
                <div>
                  <dt className="text-sm font-bold text-nhs-dark-grey">{t("appointments.youToldUs")}</dt>
                  <dd>{appointment.reasonText}</dd>
                </div>
              )}
            </dl>

            {appointment.isCancellable && (
              <div className="flex flex-wrap gap-3">
                <Link
                  href={`/appointments/book?reschedule=${appointment.id}`}
                  className="font-bold"
                >
                  {t("appointments.change")}
                </Link>
                <button
                  type="button"
                  onClick={() => setCancelling(appointment)}
                  className="font-bold text-nhs-red underline"
                >
                  {t("appointments.cancel")}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <Dialog
        open={cancelling !== null}
        onClose={() => setCancelling(null)}
        title={t("appointments.cancelDialog.title")}
        tone="destructive"
        actions={
          <>
            {/* The safe action is first in the DOM, so it takes initial focus and a stray
                Enter keeps the appointment rather than destroying it. */}
            <Button variant="secondary" onClick={() => setCancelling(null)}>
              {t("appointments.cancelDialog.keep")}
            </Button>
            <Button
              variant="warning"
              loading={cancel.isPending}
              loadingText="Cancelling your appointment"
              onClick={() => cancelling && cancel.mutate(cancelling)}
            >
              Yes, cancel it
            </Button>
          </>
        }
      >
        {cancelling && (
          <>
            <p className="mb-3 font-bold">
              {when.format(new Date(cancelling.startsAt))} · {cancelling.departmentName}
            </p>
            <p>{t("appointments.cancelDialog.body")}</p>
          </>
        )}
      </Dialog>
    </>
  );
}

export default function AppointmentsPage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <AppointmentsList />
    </Suspense>
  );
}
