"use client";

import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { Button } from "@/components/ui";

/**
 * Shown when a page throws.
 *
 * Without this, a production build falls back to a bare "Application error" screen: no
 * service name, no way back, and nothing about where to get real help. The brief asks for
 * safe failure states, and on a health service that means always pointing at NHS 111 and
 * 999 - never at a stack trace.
 *
 * The digest is Next's opaque reference for the underlying error: safe to show, and useful
 * for tracing a report. The error message itself is deliberately not shown, because it can
 * carry internal detail.
 */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <>
      <SiteHeader />
      <main id="main-content" className="mx-auto w-full max-w-xl flex-1 px-4 py-12">
        <h1 className="mb-4 text-4xl font-bold">Sorry, something went wrong</h1>
        <p className="mb-4">
          This page could not be shown. You can try again, or go back to the home page.
        </p>
        <p className="mb-6 font-bold">
          If you need medical help, use{" "}
          <a href="https://111.nhs.uk" rel="noreferrer noopener" target="_blank">
            NHS 111 online<span className="sr-only"> (opens in a new tab)</span>
          </a>{" "}
          or call 111. In an emergency call 999.
        </p>
        <div className="mb-6 flex flex-wrap items-center gap-4">
          <Button onClick={reset}>Try again</Button>
          <Link href="/">Go to the home page</Link>
        </div>
        {error.digest && (
          <p className="text-sm text-nhs-dark-grey">
            Reference: <code>{error.digest}</code>
          </p>
        )}
      </main>
    </>
  );
}
