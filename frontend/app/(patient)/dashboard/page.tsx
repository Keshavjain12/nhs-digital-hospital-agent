"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Alert, Badge, ButtonLink, Card } from "@/components/ui";
import { useSession } from "@/features/auth/SessionProvider";
import { api } from "@/lib/api";
import type { AppointmentListResponse } from "@/types/api";

const when = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

export default function DashboardPage() {
  const { user } = useSession();

  const appointments = useQuery({
    queryKey: ["appointments", false],
    queryFn: () => api.get<AppointmentListResponse>("/appointments?includePast=false"),
  });

  const next = appointments.data?.items.find((item) => item.status === "BOOKED");

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Your account</h1>
      <p className="mb-8 text-nhs-dark-grey">
        Welcome back{user ? `, ${user.displayName}` : ""}.
      </p>

      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Your details">
          <dl className="space-y-2">
            <div>
              <dt className="font-bold">Name</dt>
              <dd>{user?.displayName ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-bold">Email address</dt>
              <dd className="break-words">{user?.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-bold">Account type</dt>
              <dd>Patient</dd>
            </div>
          </dl>
        </Card>

        <Card title="Appointments">
          {appointments.isPending && (
            <p role="status" aria-live="polite">
              Loading your appointments…
            </p>
          )}

          {appointments.error && (
            <Alert tone="error" title="Could not load your appointments">
              {appointments.error.message}
            </Alert>
          )}

          {appointments.data && !next && (
            <>
              <p className="mb-4">You have no upcoming appointments.</p>
              <ButtonLink href="/appointments/book">Book an appointment</ButtonLink>
            </>
          )}

          {next && (
            <>
              <div className="mb-4 border-l-8 border-nhs-blue bg-[#f7f9fa] p-4">
                <p className="mb-1 text-sm font-bold uppercase tracking-wide text-nhs-dark-grey">
                  Your next appointment
                </p>
                <p className="mb-1 text-lg font-bold">{when.format(new Date(next.startsAt))}</p>
                <p className="mb-2 text-nhs-dark-grey">
                  {next.departmentName} · {next.siteName}
                </p>
                <Badge tone="success" icon="✓">
                  Booked
                </Badge>
              </div>
              <Link href="/appointments" className="font-bold">
                See all your appointments
              </Link>
            </>
          )}
        </Card>
      </div>
    </>
  );
}
