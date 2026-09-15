"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Table, type Column } from "@/components/ui";
import { api } from "@/lib/api";
import type { AuditEntry, AuditListResponse } from "@/types/api";
import { UK_TIME_ZONE } from "@/lib/format";

const FILTERS = [
  { label: "All events", action: "", result: "" },
  { label: "Refused", action: "", result: "DENIED" },
  { label: "Record access", action: "PATIENT_RECORD_VIEW", result: "" },
  { label: "Emergency override", action: "BREAKGLASS_INVOKED", result: "" },
  { label: "Sign-ins", action: "USER_LOGIN", result: "" },
] as const;

export default function AuditPage() {
  const [active, setActive] = useState(0);

  const { data, isPending, error } = useQuery({
    queryKey: ["admin", "audit", active],
    queryFn: () => {
      const filter = FILTERS[active];
      const params = new URLSearchParams({ pageSize: "50" });
      if (filter.action) params.set("action", filter.action);
      if (filter.result) params.set("result", filter.result);
      return api.get<AuditListResponse>(`/admin/audit?${params}`);
    },
  });

  const columns: ReadonlyArray<Column<AuditEntry>> = [
    {
      key: "when",
      header: "When",
      cell: (row) => new Date(row.occurredAt).toLocaleString("en-GB", { timeZone: UK_TIME_ZONE }),
    },
    {
      key: "action",
      header: "Action",
      cell: (row) => <span className="font-mono text-sm">{row.action}</span>,
    },
    {
      key: "result",
      header: "Result",
      cell: (row) =>
        row.result === "SUCCESS" ? (
          <Badge tone="success" icon="✓">
            Allowed
          </Badge>
        ) : (
          <Badge tone="attention" icon="✕">
            {row.result === "DENIED" ? "Refused" : "Error"}
          </Badge>
        ),
    },
    { key: "actor", header: "Who", cell: (row) => row.actor },
    {
      key: "detail",
      header: "Detail",
      cell: (row) => (
        <span className="text-sm text-nhs-dark-grey">
          {Object.keys(row.metadata ?? {}).length > 0
            ? Object.entries(row.metadata)
                .map(([key, value]) => `${key}: ${String(value)}`)
                .join(", ")
            : "—"}
        </span>
      ),
    },
  ];

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Audit trail</h1>
      <p className="mb-6 text-nhs-dark-grey">
        Every access and refusal, append-only. Records cannot be edited or deleted, by
        anyone, including this account.
      </p>

      <Alert tone="info" title="Patient identities are not shown">
        Entries reference records by identifier only. You can see that a record was
        accessed, by whom, and on what basis - not whose record it was.
      </Alert>

      <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="Filter audit events">
        {FILTERS.map((filter, index) => (
          <Button
            key={filter.label}
            variant={index === active ? "primary" : "secondary"}
            onClick={() => setActive(index)}
            aria-pressed={index === active}
          >
            {filter.label}
          </Button>
        ))}
      </div>

      {error && (
        <Alert tone="error" title="Could not load the audit trail" focusOnMount>
          {error.message}
        </Alert>
      )}

      {isPending ? (
        <p role="status" aria-live="polite">
          Loading audit trail…
        </p>
      ) : (
        data && (
          <>
            <p className="mb-4" role="status" aria-live="polite">
              {data.meta.totalItems} events
            </p>
            <Table
              caption="Audit trail entries"
              columns={columns}
              rows={data.items}
              rowKey={(row) => String(row.id)}
              emptyMessage="No events match this filter."
            />
          </>
        )
      )}
    </>
  );
}
