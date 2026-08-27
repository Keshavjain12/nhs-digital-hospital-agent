"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ErrorSummary, TextInput } from "@/components/ui";
import { registerSchema, toFieldErrors } from "@/features/auth/validation";
import { api, ApiError, NetworkError } from "@/lib/api";
import type { RegisterResponse } from "@/types/api";

export function RegisterForm() {
  const router = useRouter();

  const [fieldErrors, setFieldErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors([]);

    const form = new FormData(event.currentTarget);
    const rawNhs = String(form.get("nhsNumber") ?? "").trim();

    const values = {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
      givenName: String(form.get("givenName") ?? ""),
      familyName: String(form.get("familyName") ?? ""),
      dateOfBirth: String(form.get("dateOfBirth") ?? ""),
      nhsNumber: rawNhs || undefined,
    };

    const parsed = registerSchema.safeParse(values);
    if (!parsed.success) {
      setFieldErrors(toFieldErrors(parsed.error));
      return;
    }

    setSubmitting(true);
    try {
      await api.post<RegisterResponse>(
        "/auth/register",
        {
          ...parsed.data,
          // Spaces stripped before sending: the backend stores the digits, and the UI
          // reformats for display. Users copy NHS numbers in the printed 3-3-4 grouping.
          nhsNumber: parsed.data.nhsNumber?.replace(/[^0-9]/g, ""),
        },
        { retryOnUnauthorised: false },
      );
      router.replace("/login?registered=1");
    } catch (error) {
      if (error instanceof ApiError) {
        // Map any per-field detail the backend returned onto the matching input, so the
        // user sees the problem next to the field rather than only at the top.
        const mapped = error.fieldErrors.map((detail) => ({
          field: detail.field,
          message:
            detail.field === "nhsNumber"
              ? "Check your NHS number and try again"
              : "Check this answer and try again",
        }));
        if (mapped.length > 0) setFieldErrors(mapped);
        else setFormError(error.message);
      } else if (error instanceof NetworkError) {
        setFormError(error.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const errorFor = (field: string) =>
    fieldErrors.find((error) => error.field === field)?.message;

  return (
    <form onSubmit={handleSubmit} noValidate>
      <ErrorSummary errors={fieldErrors} />
      {formError && (
        <Alert tone="error" title="Could not create your account" focusOnMount>
          {formError}
        </Alert>
      )}

      <TextInput
        label="First name"
        name="givenName"
        autoComplete="given-name"
        required
        error={errorFor("givenName")}
      />

      <TextInput
        label="Last name"
        name="familyName"
        autoComplete="family-name"
        required
        error={errorFor("familyName")}
      />

      <TextInput
        label="Date of birth"
        name="dateOfBirth"
        type="date"
        autoComplete="bday"
        hint="For example, 12 04 1988"
        required
        error={errorFor("dateOfBirth")}
      />

      <TextInput
        label="Email address"
        name="email"
        type="email"
        autoComplete="username"
        inputMode="email"
        spellCheck={false}
        required
        error={errorFor("email")}
      />

      <TextInput
        label="Create a password"
        name="password"
        type="password"
        autoComplete="new-password"
        hint="Must be at least 12 characters. A memorable phrase of three or four words is both stronger and easier to remember than a short complex password."
        required
        error={errorFor("password")}
      />

      <TextInput
        label="NHS number"
        name="nhsNumber"
        inputMode="numeric"
        hint="It is on any letter the NHS has sent you, in the format 943 476 5919. You can add this later."
        error={errorFor("nhsNumber")}
      />

      <Button type="submit" size="lg" loading={submitting} loadingText="Creating your account">
        Create account
      </Button>
    </form>
  );
}
