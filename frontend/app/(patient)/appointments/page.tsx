"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Badge, Button, ButtonLink, Card, Dialog } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { AppointmentItem, AppointmentListResponse } from "@/types/api";

const when = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

function StatusBadge({ status }: { status: string }) {
  // Icon and word as well as colour, so status is never carried by colour alone.
  if (status === "BOOKED") {
    return (
      <Badge tone="success" icon="✓">
        Booked
      </Badge>
    );
  }
  if (status === "CANCELLED") {
    return (
      <Badge tone="neutral" icon="○">
        Cancelled
      </Badge>
    );
  }
  if (status === "DID_NOT_ATTEND") {
    return (
      <Badge tone="attention" icon="!">
        Not attended
      </Badge>
    );
  }
  return (
    <Badge tone="info" icon="●">
      {status.replace(/_/g, " ").toLowerCase()}
    </Badge>
  );
}

function AppointmentsList() {
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [includePast, setIncludePast] = useState(false);
  const [cancelling, setCancelling] = useState<AppointmentItem | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const bookedReference = params.get("booked");

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
          <h1 className="mb-2 text-4xl font-bold">Your appointments</h1>
          <p className="text-nhs-dark-grey">Book, change or cancel an appointment.</p>
        </div>
        <ButtonLink href="/appointments/book" size="lg">
          Book an appointment
        </ButtonLink>
      </div>

      {bookedReference && (
        <Alert tone="success" title="Appointment booked">
          Your reference is <strong>{bookedReference}</strong>. We have sent a confirmation
          to your email address.
        </Alert>
      )}

      {actionError && (
        <Alert tone="error" title="Something went wrong" focusOnMount>
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
          Include past and cancelled appointments
        </label>
      </div>

      {appointments.isPending && (
        <p role="status" aria-live="polite">
          Loading your appointments…
        </p>
      )}

      {appointments.error && (
        <Alert tone="error" title="Could not load your appointments" focusOnMount>
          {appointments.error.message}
        </Alert>
      )}

      {appointments.data?.items.length === 0 && (
        <Card title="No appointments">
          <p className="mb-4">
            {includePast
              ? "You have no appointments on record."
              : "You have no upcoming appointments."}
          </p>
          <Link href="/appointments/book" className="font-bold">
            Book an appointment
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
                <dt className="text-sm font-bold text-nhs-dark-grey">Reference</dt>
                <dd className="font-mono">{appointment.reference}</dd>
              </div>
              {appointment.reasonText && (
                <div>
                  <dt className="text-sm font-bold text-nhs-dark-grey">You told us</dt>
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
                  Change this appointment
                </Link>
                <button
                  type="button"
                  onClick={() => setCancelling(appointment)}
                  className="font-bold text-nhs-red underline"
                >
                  Cancel this appointment
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <Dialog
        open={cancelling !== null}
        onClose={() => setCancelling(null)}
        title="Cancel this appointment?"
        tone="destructive"
        actions={
          <>
            {/* The safe action is first in the DOM, so it takes initial focus and a stray
                Enter keeps the appointment rather than destroying it. */}
            <Button variant="secondary" onClick={() => setCancelling(null)}>
              Keep this appointment
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
            <p>
              Cancelling frees this time for someone else. You will need to book again if
              you still need to be seen.
            </p>
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
