import { z } from "zod";

/**
 * Client-side validation.
 *
 * This exists to give fast, accessible feedback - not to enforce anything. Every rule
 * here is enforced again server-side, because a client check is a convenience an attacker
 * simply skips (brief §9). The two must agree, so the constraints mirror
 * `backend/app/schemas/auth.py`.
 */

// Matches the backend's 12-character minimum. Length over composition rules, per NCSC:
// forced symbols push people toward predictable substitutions without adding entropy.
const password = z
  .string()
  .min(12, "Your password must be at least 12 characters long")
  .max(128, "Your password must be 128 characters or fewer");

const email = z
  .string()
  .min(1, "Enter your email address")
  .email("Enter an email address in the correct format, like name@example.com");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password"),
});

export const registerSchema = z.object({
  email,
  password,
  givenName: z.string().min(1, "Enter your first name").max(100),
  familyName: z.string().min(1, "Enter your last name").max(100),
  dateOfBirth: z
    .string()
    .min(1, "Enter your date of birth")
    .refine((value) => !Number.isNaN(Date.parse(value)), "Enter a real date of birth")
    .refine((value) => new Date(value) <= new Date(), "Date of birth cannot be in the future")
    .refine(
      (value) => new Date(value).getFullYear() >= 1900,
      "Enter a date of birth after 1900",
    ),
  // Optional at registration. The backend allows a patient to register before their NHS
  // number is confirmed rather than forcing them to invent one.
  nhsNumber: z
    .string()
    .optional()
    .refine(
      (value) => !value || /^[0-9]{10}$/.test(value.replace(/[^0-9]/g, "")),
      "An NHS number is 10 digits, like 943 476 5919",
    ),
});

export const forgotPasswordSchema = z.object({ email });

export const resetPasswordSchema = z
  .object({
    token: z.string().min(1, "This reset link is missing its code"),
    newPassword: password,
    confirmPassword: z.string(),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "Your passwords do not match",
    path: ["confirmPassword"],
  });

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

/** Flatten a Zod error into the field/message pairs the ErrorSummary expects. */
export function toFieldErrors(error: z.ZodError): Array<{ field: string; message: string }> {
  return error.issues.map((issue) => ({
    field: String(issue.path[0] ?? "form"),
    message: issue.message,
  }));
}
