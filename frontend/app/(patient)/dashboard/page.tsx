"use client";

import { Alert, Card } from "@/components/ui";
import { useSession } from "@/features/auth/SessionProvider";

export default function DashboardPage() {
  const { user } = useSession();

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
              <dd>{user?.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-bold">Account type</dt>
              <dd>Patient</dd>
            </div>
          </dl>
        </Card>

        <Card title="Appointments">
          {/* Honest empty state. Booking lands in Sprint 2; showing a fake list here
              would misrepresent what the system can currently do. */}
          <Alert tone="info" title="Not available yet">
            Appointment booking is being built. It will appear here once ready.
          </Alert>
        </Card>
      </div>
    </>
  );
}
