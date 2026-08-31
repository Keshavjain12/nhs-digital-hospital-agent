"use client";

import Link from "next/link";

import { Button } from "@/components/ui";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { useSession } from "@/features/auth/SessionProvider";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useSession();

  return (
    <RequireAuth roles={["ADMIN"]}>
      <header className="bg-nhs-purple">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <Link
            href="/admin/dashboard"
            className="text-xl font-bold text-white no-underline hover:underline"
          >
            Operations
          </Link>
          <div className="flex flex-wrap items-center gap-4">
            {user && <span className="text-white">{user.displayName} · Administrator</span>}
            <Button variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
        <nav aria-label="Operations" className="border-t border-white/20">
          <div className="mx-auto flex max-w-6xl gap-6 px-4">
            <Link href="/admin/dashboard" className="py-3 font-bold text-white no-underline hover:underline">
              Dashboard
            </Link>
            <Link href="/admin/models" className="py-3 font-bold text-white no-underline hover:underline">
              Models
            </Link>
            <Link href="/admin/audit" className="py-3 font-bold text-white no-underline hover:underline">
              Audit trail
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
