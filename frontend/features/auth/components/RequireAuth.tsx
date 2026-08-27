"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { ROLE_HOME } from "@/lib/routes";
import type { UserRole } from "@/types/api";

/**
 * Client-side route protection.
 *
 * This is a *usability* control, not a security one. It stops a signed-out user landing
 * on a page that would only show them errors, and sends them somewhere useful. It is not
 * what protects the data: every endpoint behind these pages authorises independently on
 * the server (brief §9). Removing this component would be a worse experience, not a
 * breach.
 */
export function RequireAuth({
  children,
  roles,
}: {
  children: ReactNode;
  roles?: ReadonlyArray<UserRole>;
}) {
  const { user, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;

    if (!user) {
      const next = encodeURIComponent(window.location.pathname);
      router.replace(`/login?next=${next}`);
      return;
    }

    if (roles && !roles.includes(user.role as UserRole)) {
      // Signed in, but on the wrong portal. Send them to their own home rather than a
      // dead end: the usual cause is a stale link or a bookmark from another account,
      // and stranding a correctly signed-in user on an error page helps nobody.
      router.replace(ROLE_HOME[user.role as UserRole] ?? "/not-authorised");
    }
  }, [user, loading, roles, router]);

  if (loading) {
    return (
      <p role="status" aria-live="polite" className="p-4">
        Checking your sign-in details…
      </p>
    );
  }

  if (!user) return null;
  if (roles && !roles.includes(user.role as UserRole)) return null;

  return <>{children}</>;
}
