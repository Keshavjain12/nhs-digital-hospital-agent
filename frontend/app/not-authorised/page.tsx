"use client";

import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { Alert } from "@/components/ui";
import { useSession } from "@/features/auth/SessionProvider";
import { ROLE_HOME } from "@/lib/routes";
import type { UserRole } from "@/types/api";

export default function NotAuthorisedPage() {
  const { user, loading } = useSession();
  const home = user ? (ROLE_HOME[user.role as UserRole] ?? "/") : "/login";

  return (
    <>
      <SiteHeader />
      <main id="main-content" className="mx-auto w-full max-w-xl flex-1 px-4 py-12">
        <h1 className="mb-6 text-4xl font-bold">You cannot view this page</h1>

        <Alert tone="error" title="Permission denied">
          {user ? (
            <>
              You are signed in as <strong>{user.displayName}</strong>, and this account does
              not have access to this part of the service.
            </>
          ) : (
            <>Your account does not have access to this part of the service.</>
          )}{" "}
          If you think this is wrong, contact your system administrator.
        </Alert>

        {/* A dead end helps nobody. Someone who is correctly signed in and hit a stale link
            needs a way back to work, not just the marketing page. */}
        {!loading && (
          <p>
            <Link href={home} className="font-bold">
              {user ? "Go to your home page" : "Sign in"}
            </Link>
          </p>
        )}
      </main>
    </>
  );
}
