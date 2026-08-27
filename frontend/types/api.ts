/**
 * Application-facing API types.
 *
 * The shapes are pulled from `types/generated/api.d.ts`, which is generated from the
 * backend's live OpenAPI document by `npm run generate:api`. Nothing here restates a
 * field name by hand: when the backend contract changes, regeneration makes the mismatch
 * a TypeScript error rather than a runtime surprise in a browser.
 *
 * This file only gives those generated shapes readable names and adds the few types the
 * generator cannot know about (the error-code union).
 */

import type { components } from "./generated/api";

type Schemas = components["schemas"];

export type LoginRequest = Schemas["LoginRequest"];
export type LoginResponse = Schemas["LoginResponse"];
export type RegisterRequest = Schemas["RegisterRequest"];
export type RegisterResponse = Schemas["RegisterResponse"];
export type RefreshResponse = Schemas["RefreshResponse"];
export type UserSummary = Schemas["UserSummary"];
export type MessageResponse = Schemas["MessageResponse"];
export type PasswordResetRequest = Schemas["PasswordResetRequest"];
export type PasswordResetConfirm = Schemas["PasswordResetConfirm"];
export type ApiErrorBody = Schemas["ErrorResponse"];

// --- Patients ---------------------------------------------------------------
export type PatientListItem = Schemas["PatientListItem"];
export type PatientListResponse = Schemas["PatientListResponse"];
export type PatientSummary = Schemas["PatientSummary"];
export type PatientDetailResponse = Schemas["PatientDetailResponse"];
export type BreakglassResponse = Schemas["BreakglassResponse"];

// --- Administration ---------------------------------------------------------
export type OverviewResponse = Schemas["OverviewResponse"];
export type KpiCard = Schemas["KpiCard"];
export type AuditEntry = Schemas["AuditEntry"];
export type AuditListResponse = Schemas["AuditListResponse"];

/**
 * Error codes the UI branches on.
 *
 * Mirrors the AppError subclasses in `backend/app/core/errors.py`. Kept as a union rather
 * than derived from the generated types because FastAPI does not express the code
 * vocabulary in its schema - only that `code` is a string.
 */
export type ErrorCode =
  | "VALIDATION_ERROR"
  | "AUTHENTICATION_REQUIRED"
  | "TOKEN_EXPIRED"
  | "PERMISSION_DENIED"
  | "RESOURCE_NOT_FOUND"
  | "APPOINTMENT_CONFLICT"
  | "SLOT_HOLD_EXPIRED"
  | "INVALID_STATE_TRANSITION"
  | "NHS_NUMBER_INVALID"
  | "RATE_LIMITED"
  | "UPSTREAM_UNAVAILABLE"
  | "INTERNAL_ERROR";

export type UserRole = "PATIENT" | "NURSE" | "DOCTOR" | "ADMIN";

/** Where a role lands after signing in. */
export const ROLE_HOME: Record<UserRole, string> = {
  PATIENT: "/dashboard",
  NURSE: "/staff/queue",
  DOCTOR: "/staff/queue",
  ADMIN: "/admin/dashboard",
};
