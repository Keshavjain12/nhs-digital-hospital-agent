"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ErrorSummary, TextInput } from "@/components/ui";
import { forgotPasswordSchema, toFieldErrors } from "@/features/auth/validation";
import { api, NetworkError } from "@/lib/api";
import type { MessageResponse } from "@/types/api";

export default function ForgotPasswordPage() {
  const [fieldErrors, setFieldErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldErrors([]);
    setFormError(null);

    const form = new FormData(event.currentTarget);
    const parsed = forgotPasswordSchema.safeParse({ email: String(form.get("email") ?? "") });
    if (!parsed.success) {
      setFieldErrors(toFieldErrors(parsed.error));
      return;
    }

    setSubmitting(true);
    try {
      await api.post<MessageResponse>("/auth/password-reset", parsed.data, {
        retryOnUnauthorised: false,
      });
      // Shown whether or not the address exists. The backend deliberately returns an
      // identical response either way; branching here would undo that and turn the page
      // into an account-enumeration oracle - which for a hospital reveals that someone
      // is a patient here.
      setSent(true);
    } catch (error) {
      setFormError(
        error instanceof NetworkError
          ? error.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <>
        <h1 className="mb-6 text-4xl font-bold">Check your email</h1>
        <Alert tone="success" title="If that address has an account, we have sent a link to it">
          The link expires in 30 minutes. If nothing arrives, check your spam folder or
          try again.
        </Alert>
        <p>
          <Link href="/login">Back to sign in</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Reset your password</h1>
      <p className="mb-6 text-nhs-dark-grey">
        Enter your email address and we will send you a link to set a new password.
      </p>

      <form onSubmit={handleSubmit} noValidate>
        <ErrorSummary errors={fieldErrors} />
        {formError && (
          <Alert tone="error" title="Could not send the link" focusOnMount>
            {formError}
          </Alert>
        )}

        <TextInput
          label="Email address"
          name="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          spellCheck={false}
          required
          error={fieldErrors.find((e) => e.field === "email")?.message}
        />

        <Button type="submit" size="lg" loading={submitting} loadingText="Sending">
          Send reset link
        </Button>
      </form>

      <hr className="my-8 border-nhs-pale-grey" />
      <p>
        <Link href="/login">Back to sign in</Link>
      </p>
    </>
  );
}
