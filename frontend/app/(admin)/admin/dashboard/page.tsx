"use client";

import { useQuery } from "@tanstack/react-query";

import { Alert, Badge, Card } from "@/components/ui";
import { api } from "@/lib/api";
import type { OverviewResponse } from "@/types/api";

export default function AdminDashboardPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => api.get<OverviewResponse>("/admin/overview"),
  });

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Operations dashboard</h1>
      <p className="mb-6 text-nhs-dark-grey">
        Aggregate activity for this environment.
      </p>

      <Alert tone="info" title="Administrator accounts cannot open patient records">
        This is deliberate, not a missing permission. Operational authority is not clinical
        authority: you can see that records were accessed without seeing whose.
      </Alert>

      {error && (
        <Alert tone="error" title="Could not load the dashboard" focusOnMount>
          {error.message}
        </Alert>
      )}

      {isPending && (
        <p role="status" aria-live="polite">
          Loading dashboard…
        </p>
      )}

      {data && (
        <>
          <h2 className="mb-4 text-2xl font-bold">Last 24 hours</h2>
          <ul className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.cards.map((card) => (
              <li key={card.key} className="border border-nhs-mid-grey bg-white p-4">
                <p className="mb-1 font-bold text-nhs-dark-grey">{card.label}</p>
                <p className="mb-1 text-4xl font-bold">{card.value}</p>
                <p className="text-sm text-nhs-dark-grey">{card.caption}</p>
                {card.tone === "attention" && (
                  <p className="mt-2">
                    <Badge tone="attention" icon="⚠">
                      Needs review
                    </Badge>
                  </p>
                )}
              </li>
            ))}
          </ul>

          <Card title="Departments">
            <ul className="grid gap-2 sm:grid-cols-2">
              {data.departments.map((department) => (
                <li key={department.id}>
                  <span className="font-bold">{department.name}</span>{" "}
                  <span className="text-nhs-dark-grey">({department.code})</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Bed occupancy and waiting times" className="mt-6">
            {/* No source data exists for these - see docs/data/dataset-strategy.md B4.
                Charting invented numbers on an operations screen would be worse than
                showing nothing. */}
            <Alert tone="info" title="No data to show">
              No occupancy or waiting-time data exists for this service, and no open UK
              source provides it at this level of detail. Nothing is charted rather than
              something invented.
            </Alert>
          </Card>
        </>
      )}
    </>
  );
}
