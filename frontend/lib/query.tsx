"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

/**
 * Query client for all server-state.
 *
 * Created inside a component rather than at module scope: a module-level client is shared
 * across requests on the server, which would leak one user's cached data into another's
 * response.
 */
export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error) => {
              // Never retry an authorisation failure: the answer will not change, and
              // each attempt writes another PERMISSION_DENIED entry to the audit trail.
              if (error instanceof ApiError && !error.isRetryable) return false;
              return failureCount < 2;
            },
            // Clinical data going stale in a background tab is a real risk; refetching on
            // focus means a clinician returning to the tab sees current information.
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
