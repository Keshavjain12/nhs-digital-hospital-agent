"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Alert, Badge, ButtonLink, Card } from "@/components/ui";
import { useSession } from "@/features/auth/SessionProvider";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { AppointmentListResponse } from "@/types/api";
import { UK_TIME_ZONE } from "@/lib/format";

const when = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

export default function DashboardPage() {
  const { user } = useSession();
  const t = useT();

  const appointments = useQuery({
    queryKey: ["appointments", false],
    queryFn: () => api.get<AppointmentListResponse>("/appointments?includePast=false"),
  });

  const next = appointments.data?.items.find((item) => item.status === "BOOKED");

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">{t("dashboard.title")}</h1>
      <p className="mb-8 text-nhs-dark-grey">
        {t("dashboard.welcome", { name: user?.displayName ?? "" })}
      </p>

      <div className="mb-6 border-4 border-nhs-blue p-5">
        <p className="mb-1 text-sm font-bold uppercase tracking-wide text-nhs-dark-grey">
          {t("dashboard.prompt.eyebrow")}
        </p>
        <h2 className="mb-2 text-2xl font-bold">{t("dashboard.prompt.title")}</h2>
        <p className="mb-4 max-w-xl text-nhs-dark-grey">
          {t("dashboard.prompt.body")}
        </p>
        <ButtonLink href="/symptom-check">{t("dashboard.prompt.action")}</ButtonLink>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card title={t("dashboard.details.title")}>
          <dl className="space-y-2">
            <div>
              <dt className="font-bold">{t("dashboard.details.name")}</dt>
              <dd>{user?.displayName ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-bold">{t("dashboard.details.email")}</dt>
              <dd className="break-words">{user?.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-bold">{t("dashboard.details.accountType")}</dt>
              <dd>{t("dashboard.details.patient")}</dd>
            </div>
          </dl>
        </Card>

        <Card title={t("dashboard.appointments.title")}>
          {appointments.isPending && (
            <p role="status" aria-live="polite">
              {t("common.loading")}
            </p>
          )}

          {appointments.error && (
            <Alert tone="error" title={t("common.somethingWentWrong")}>
              {appointments.error.message}
            </Alert>
          )}

          {appointments.data && !next && (
            <>
              <p className="mb-4">{t("dashboard.appointments.none")}</p>
              <ButtonLink href="/appointments/book">{t("dashboard.appointments.book")}</ButtonLink>
            </>
          )}

          {next && (
            <>
              <div className="mb-4 border-l-8 border-nhs-blue bg-[#f7f9fa] p-4">
                <p className="mb-1 text-sm font-bold uppercase tracking-wide text-nhs-dark-grey">
                  {t("dashboard.appointments.next")}
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
                {t("dashboard.appointments.seeAll")}
              </Link>
            </>
          )}
        </Card>
      </div>
    </>
  );
}
