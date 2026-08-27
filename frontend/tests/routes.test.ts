/**
 * Post-login routing tests.
 *
 * Regression: sign-in honoured a `next` parameter that was a valid same-site path but
 * belonged to an area the signed-in role could not enter. Visiting /staff/queue while
 * signed out leaves `?next=/staff/queue` in the address bar; signing in there as an admin
 * or a patient then landed straight on "Permission denied" - which reads as a broken
 * account rather than a stale URL.
 */

import { describe, expect, it } from "vitest";

import { canRoleVisit, ROLE_HOME, resolvePostLoginPath, rolesAllowedFor } from "@/lib/routes";
import type { UserRole } from "@/types/api";

const ROLES: readonly UserRole[] = ["PATIENT", "NURSE", "DOCTOR", "ADMIN"];

describe("resolvePostLoginPath", () => {
  it.each(ROLES)("sends %s to its own home when there is no next", (role) => {
    expect(resolvePostLoginPath(role, null)).toBe(ROLE_HOME[role]);
  });

  it.each(ROLES)("never sends %s somewhere it cannot go", (role) => {
    // The whole failure class, asserted directly: whatever comes back must be visitable.
    for (const next of ["/staff/queue", "/admin/dashboard", "/dashboard", "/admin/audit"]) {
      expect(canRoleVisit(role, resolvePostLoginPath(role, next))).toBe(true);
    }
  });

  it("ignores a stale next belonging to another role", () => {
    expect(resolvePostLoginPath("ADMIN", "/staff/queue")).toBe("/admin/dashboard");
    expect(resolvePostLoginPath("PATIENT", "/staff/queue")).toBe("/dashboard");
    expect(resolvePostLoginPath("DOCTOR", "/admin/audit")).toBe("/staff/queue");
  });

  it("honours a next the role can actually use", () => {
    expect(resolvePostLoginPath("DOCTOR", "/staff/patients/abc")).toBe("/staff/patients/abc");
    expect(resolvePostLoginPath("ADMIN", "/admin/audit")).toBe("/admin/audit");
  });

  it.each([
    ["https://evil.test/phish", "absolute URL"],
    ["//evil.test/phish", "protocol-relative URL"],
    ["http://localhost:3000/dashboard", "absolute URL to our own host"],
  ])("refuses %s (%s) so login cannot become an open redirect", (next) => {
    expect(resolvePostLoginPath("PATIENT", next)).toBe("/dashboard");
  });

  it("falls back for an empty next", () => {
    expect(resolvePostLoginPath("NURSE", "")).toBe("/staff/queue");
  });
});

describe("rolesAllowedFor", () => {
  it.each([
    ["/staff/queue", ["DOCTOR", "NURSE"]],
    ["/staff/patients/123", ["DOCTOR", "NURSE"]],
    ["/admin/dashboard", ["ADMIN"]],
    ["/dashboard", ["PATIENT"]],
  ])("maps %s to its permitted roles", (path, expected) => {
    expect(rolesAllowedFor(path)).toEqual(expected);
  });

  it.each(["/login", "/register", "/", "/forgot-password"])(
    "treats %s as public",
    (path) => {
      expect(rolesAllowedFor(path)).toBeNull();
    },
  );

  it("does not match a prefix that is only a partial word", () => {
    // "/administration" must not be caught by the "/admin" area.
    expect(rolesAllowedFor("/administration")).toBeNull();
  });
});

describe("canRoleVisit", () => {
  it("lets every role reach public pages", () => {
    for (const role of ROLES) {
      expect(canRoleVisit(role, "/login")).toBe(true);
    }
  });

  it("keeps each role out of the other portals", () => {
    expect(canRoleVisit("ADMIN", "/staff/queue")).toBe(false);
    expect(canRoleVisit("ADMIN", "/dashboard")).toBe(false);
    expect(canRoleVisit("PATIENT", "/admin/dashboard")).toBe(false);
    expect(canRoleVisit("DOCTOR", "/admin/dashboard")).toBe(false);
    expect(canRoleVisit("NURSE", "/dashboard")).toBe(false);
  });

  it("agrees with every role's own home page", () => {
    // A role whose home it cannot visit would loop between redirect and refusal.
    for (const role of ROLES) {
      expect(canRoleVisit(role, ROLE_HOME[role])).toBe(true);
    }
  });
});
