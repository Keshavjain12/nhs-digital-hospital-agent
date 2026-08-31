import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Alert } from "@/components/ui";
import { LoginForm } from "@/features/auth/components/LoginForm";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ registered?: string; expired?: string }>;
}) {
  const params = await searchParams;

  return (
    <>
      <h1 className="mb-6 text-4xl font-bold">Sign in</h1>

      {params.registered && (
        <Alert tone="success" title="Account created">
          You can now sign in with your email address and password.
        </Alert>
      )}
      {params.expired && (
        <Alert tone="info" title="You were signed out">
          Your session expired for security. Please sign in again.
        </Alert>
      )}

      {/* useSearchParams needs a Suspense boundary in the App Router. */}
      <Suspense fallback={<p>Loading…</p>}>
        <LoginForm />
      </Suspense>

      <details className="mb-6 border border-nhs-mid-grey p-4">
        <summary className="cursor-pointer font-bold">
          Demonstration accounts
        </summary>
        <p className="mt-3 mb-2">
          This is a demo system with synthetic data. Sign in with any of these:
        </p>
        <ul className="mb-2 list-disc pl-6">
          <li><code>patient@example.test</code> — patient portal</li>
          <li><code>doctor@example.test</code> — clinical view</li>
          <li><code>nurse@example.test</code> — clinical view</li>
          <li><code>admin@example.test</code> — operations view</li>
        </ul>
        <p>
          Password: <code>demo-hospital-2026</code>
        </p>
        <p className="mt-2 text-sm text-nhs-dark-grey">
          These accounts describe no real person, and the data behind them is synthetic.
          Each one opens the view for its own role.
        </p>
      </details>

      <hr className="my-8 border-nhs-pale-grey" />

      <p className="mb-2">
        <Link href="/forgot-password">I have forgotten my password</Link>
      </p>
      <p>
        Do not have an account? <Link href="/register">Create one now</Link>
      </p>
    </>
  );
}
