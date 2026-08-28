"use client";

import Link from "next/link";

import { Button } from "@/components/ui";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { useSession } from "@/features/auth/SessionProvider";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useSession();

  return (
    <RequireAuth roles={["PATIENT"]}>
      <header className="bg-nhs-blue">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <Link href="/dashboard" className="text-xl font-bold text-white no-underline hover:underline">
            NHS Digital Hospital Agent
          </Link>
          <div className="flex items-center gap-4">
            {user && <span className="text-white">Signed in as {user.displayName}</span>}
            <Button variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
        <nav aria-label="Your account" className="border-t border-white/20">
          <div className="mx-auto flex max-w-5xl gap-6 px-4">
            <Link href="/dashboard" className="py-3 font-bold text-white no-underline hover:underline">
              Overview
            </Link>
            <Link
              href="/symptom-check"
              className="py-3 font-bold text-white no-underline hover:underline"
            >
              Symptom check
            </Link>
            <Link
              href="/appointments"
              className="py-3 font-bold text-white no-underline hover:underline"
            >
              Appointments
            </Link>
          </div>
        </nav>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        {children}
      </main>
    </RequireAuth>
  );
}
