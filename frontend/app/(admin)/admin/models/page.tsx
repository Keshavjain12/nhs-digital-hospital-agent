"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Card } from "@/components/ui";
import { cn } from "@/lib/cn";
import { api } from "@/lib/api";
import type { ModelCardSchema, ModelListResponse } from "@/types/api";

const when = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const WINDOWS = [7, 30, 90] as const;

function StatusBadge({ status }: { status: string }) {
  if (status === "LIVE") {
    return (
      <Badge tone="success" icon="✓">
        Live
      </Badge>
    );
  }
  if (status === "SHADOW") {
    return (
      <Badge tone="info" icon="●">
        Shadow
      </Badge>
    );
  }
  if (status === "ROLLED_BACK") {
    return (
      <Badge tone="attention" icon="✕">
        Rolled back
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" icon="○">
      Not built
    </Badge>
  );
}

function ModelPanel({ model }: { model: ModelCardSchema }) {
  const isLive = model.status === "LIVE";

  return (
    <Card
      title={model.name}
      headingLevel={2}
      className={cn(!isLive && "bg-[#f7f9fa]")}
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <StatusBadge status={model.status} />
        {model.version && (
          <span className="font-mono text-sm text-nhs-dark-grey">{model.version}</span>
        )}
        <span className="text-sm text-nhs-dark-grey">Owned by {model.owner}</span>
      </div>

      <p className="mb-5">{model.purpose}</p>

      {model.metrics.length > 0 ? (
        <>
          <ul className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {model.metrics.map((metric) => (
              <li
                key={metric.key}
                className={cn(
                  "border p-4",
                  metric.tone === "attention"
                    ? "border-2 border-nhs-red"
                    : "border-nhs-mid-grey",
                )}
              >
                <p className="mb-1 text-sm font-bold text-nhs-dark-grey">{metric.label}</p>
                <p className="mb-1 text-3xl font-bold">{metric.value}</p>
                <p className="text-sm text-nhs-dark-grey">{metric.caption}</p>
                {metric.tone === "attention" && (
                  <p className="mt-2">
                    <Badge tone="attention" icon="!">
                      Needs review
                    </Badge>
                  </p>
                )}
              </li>
            ))}
          </ul>

          {model.lastOutputAt && (
            <p className="mb-4 text-sm text-nhs-dark-grey">
              Last output {when.format(new Date(model.lastOutputAt))}
            </p>
          )}
        </>
      ) : (
        // No metrics at all, rather than zeroes. A 0% reading for a model nobody has built
        // reads as a healthy model.
        <Alert tone="info" title="Nothing to monitor">
          This model has not been built, so it has never produced an output. No figures are
          shown because there are none.
        </Alert>
      )}

      {model.caveats.length > 0 && (
        <div className="border-t border-nhs-pale-grey pt-4">
          <p className="mb-2 text-sm font-bold uppercase tracking-wide text-nhs-dark-grey">
            How to read this
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-nhs-dark-grey">
            {model.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export default function ModelMonitoringPage() {
  const [windowDays, setWindowDays] = useState<number>(30);

  const models = useQuery({
    queryKey: ["admin", "models", windowDays],
    queryFn: () => api.get<ModelListResponse>(`/admin/models?windowDays=${windowDays}`),
  });

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Models</h1>
      <p className="mb-6 max-w-3xl text-nhs-dark-grey">
        What is running, and how clinicians are responding to it.
      </p>

      <Alert tone="warning" title="Monitoring is not clinical governance">
        These figures show how a model behaves. They do not replace a clinical safety case,
        a named Clinical Safety Officer, or clinician review of every individual output.
      </Alert>

      <Alert tone="info" title="Aggregates only">
        You can see that clinicians are changing a model&apos;s output, and in which
        direction, without seeing which patients were involved. Administrator accounts are
        excluded from clinical records by design.
      </Alert>

      <div
        className="mb-6 flex flex-wrap items-center gap-3"
        role="group"
        aria-label="Reporting period"
      >
        <span className="font-bold">Period:</span>
        {WINDOWS.map((days) => (
          <button
            key={days}
            type="button"
            aria-pressed={windowDays === days}
            onClick={() => setWindowDays(days)}
            className={cn(
              "min-h-[44px] border-2 px-4 py-2 font-bold",
              windowDays === days
                ? "border-nhs-black bg-nhs-black text-white"
                : "border-nhs-mid-grey bg-white hover:bg-nhs-pale-grey",
            )}
          >
            Last {days} days
          </button>
        ))}
      </div>

      {models.isPending && (
        <p role="status" aria-live="polite">
          Loading model information…
        </p>
      )}

      {models.error && (
        <Alert tone="error" title="Could not load model information" focusOnMount>
          {models.error.message}
        </Alert>
      )}

      <div className="flex flex-col gap-6">
        {models.data?.items.map((model) => (
          <ModelPanel key={model.key} model={model} />
        ))}
      </div>
    </>
  );
}
