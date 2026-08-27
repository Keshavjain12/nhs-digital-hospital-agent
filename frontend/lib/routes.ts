import type { UserRole } from "@/types/api";

/**
 * Which roles may enter each area of the application.
 *
 * Single source of truth, shared by the post-login redirect and the route guard. When
 * they were decided separately, sign-in could send a user somewhere their own guard then
 * refused - which presents as "permission denied" immediately after a successful sign-in
 * and looks like a broken account.
 *
 * This is navigation, not security. Every endpoint behind these pages authorises
 * independently on the server.
 */
const AREAS: ReadonlyArray<{ prefix: string; roles: ReadonlyArray<UserRole> }> = [
  { prefix: "/staff", roles: ["DOCTOR", "NURSE"] },
  { prefix: "/admin", roles: ["ADMIN"] },
  { prefix: "/dashboard", roles: ["PATIENT"] },
];

/** Where each role lands when it has nowhere more specific to go. */
export const ROLE_HOME: Record<UserRole, string> = {
  PATIENT: "/dashboard",
  NURSE: "/staff/queue",
  DOCTOR: "/staff/queue",
  ADMIN: "/admin/dashboard",
};

export function rolesAllowedFor(path: string): ReadonlyArray<UserRole> | null {
  const area = AREAS.find(
    (candidate) => path === candidate.prefix || path.startsWith(`${candidate.prefix}/`),
  );
  return area ? area.roles : null;
}

export function canRoleVisit(role: UserRole, path: string): boolean {
  const allowed = rolesAllowedFor(path);
  // Unlisted paths are public (login, register, the home page).
  return allowed === null || allowed.includes(role);
}

/**
 * Resolve where to send a user after they sign in.
 *
 * A `next` value is honoured only when it is a same-site path *and* the signed-in role can
 * actually use it. Two separate failures are being guarded here:
 *
 *  - An absolute or protocol-relative URL would make this login page an open redirect,
 *    which is a standard phishing primitive.
 *  - A stale `next` left in the address bar from an earlier visit - the common case - would
 *    otherwise drop the user straight onto a page their role cannot open.
 */
export function resolvePostLoginPath(role: UserRole, next: string | null): string {
  const home = ROLE_HOME[role] ?? "/dashboard";

  if (!next) return home;
  if (!next.startsWith("/") || next.startsWith("//")) return home;
  if (!canRoleVisit(role, next)) return home;

  return next;
}
