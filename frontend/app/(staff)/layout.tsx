"use client";

import Link from "next/link";

import { Button } from "@/components/ui";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { useSession } from "@/features/auth/SessionProvider";

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useSession();

  return (
    <RequireAuth roles={["DOCTOR", "NURSE"]}>
      <header className="bg-nhs-dark-blue">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <Link
            href="/staff/queue"
            className="text-xl font-bold text-white no-underline hover:underline"
          >
            Clinical workspace
          </Link>
          <div className="flex flex-wrap items-center gap-4">
            {user && (
              <span className="text-white">
                {user.displayName} · {user.role === "DOCTOR" ? "Doctor" : "Nurse"}
              </span>
            )}
            <Button variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
        <nav aria-label="Clinical" className="border-t border-white/20">
          <div className="mx-auto flex max-w-6xl flex-wrap gap-x-6 px-4">
            <Link
              href="/staff/queue"
              className="inline-block py-3 font-bold text-white no-underline hover:underline"
            >
              Patients
            </Link>
            <Link
              href="/staff/triage"
              className="inline-block py-3 font-bold text-white no-underline hover:underline"
            >
              Triage review
            </Link>
          </div>
        </nav>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {children}
      </main>
    </RequireAuth>
  );
}
