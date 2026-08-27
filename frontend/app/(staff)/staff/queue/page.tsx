"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { Alert, Badge, Button, Table, TextInput, type Column } from "@/components/ui";
import { api } from "@/lib/api";
import type { PatientListItem, PatientListResponse } from "@/types/api";

export default function StaffQueuePage() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");

  const { data, isPending, error } = useQuery({
    queryKey: ["patients", search],
    queryFn: () => {
      const params = new URLSearchParams({ pageSize: "50" });
      if (search.trim()) params.set("q", search.trim());
      return api.get<PatientListResponse>(`/patients?${params}`);
    },
  });

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearch(query);
  }

  const columns: ReadonlyArray<Column<PatientListItem>> = [
    {
      key: "name",
      header: "Patient",
      cell: (row) => (
        <Link href={`/staff/patients/${row.id}`} className="font-bold">
          {row.familyName}, {row.givenName}
        </Link>
      ),
    },
    {
      key: "dob",
      header: "Date of birth",
      cell: (row) => (
        <>
          {new Date(row.dateOfBirth).toLocaleDateString("en-GB")}{" "}
          <span className="text-nhs-dark-grey">({row.age})</span>
        </>
      ),
    },
    {
      key: "nhs",
      header: "NHS number",
      // Grouped 3-3-4 as on NHS correspondence: a clinician reading a 10-digit run aloud
      // is far more likely to transpose digits.
      cell: (row) =>
        row.nhsNumber ? (
          <span className="font-mono">
            {row.nhsNumber.slice(0, 3)} {row.nhsNumber.slice(3, 6)} {row.nhsNumber.slice(6)}
          </span>
        ) : (
          <span className="text-nhs-dark-grey">Not recorded</span>
        ),
    },
    {
      key: "flags",
      header: "Notes",
      cell: (row) => (
        <div className="flex flex-wrap gap-2">
          {row.assignedToMe ? (
            <Badge tone="success" icon="✓">
              Your patient
            </Badge>
          ) : (
            <Badge tone="neutral" icon="○">
              Not your patient
            </Badge>
          )}
          {row.interpreterNeeded && (
            <Badge tone="info" icon="⚑">
              Interpreter: {row.preferredLanguage}
            </Badge>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Patients</h1>
      <p className="mb-6 text-nhs-dark-grey">
        Search by name or NHS number. Opening a record is recorded in the audit trail.
      </p>

      <form onSubmit={handleSearch} className="mb-6 flex flex-wrap items-end gap-4" role="search">
        <div className="min-w-64 flex-1">
          <TextInput
            label="Search patients"
            name="q"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            hint="Family name, first name, or NHS number"
            className="mb-0"
          />
        </div>
        <Button type="submit" className="mb-6">
          Search
        </Button>
      </form>

      {error && (
        <Alert tone="error" title="Could not load patients" focusOnMount>
          {error.message}
        </Alert>
      )}

      {isPending ? (
        <p role="status" aria-live="polite">
          Loading patients…
        </p>
      ) : (
        data && (
          <>
            <p className="mb-4" role="status" aria-live="polite">
              {data.meta.totalItems} {data.meta.totalItems === 1 ? "patient" : "patients"} found
            </p>
            <Table
              caption="Patients matching your search"
              columns={columns}
              rows={data.items}
              rowKey={(row) => row.id}
              emptyMessage="No patients match that search."
            />
          </>
        )
      )}
    </>
  );
}
