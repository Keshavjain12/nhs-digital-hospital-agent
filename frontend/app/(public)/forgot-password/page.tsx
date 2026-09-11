"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ErrorSummary, TextInput } from "@/components/ui";
import { forgotPasswordSchema, toFieldErrors } from "@/features/auth/validation";
import { api, NetworkError } from "@/lib/api";
import type { MessageResponse } from "@/types/api";

/**
 * Password reset request.
 *
 * The flow is real up to the point of delivery: a token is issued and stored hashed. This
 * build has no email or SMS delivery, though, so the link never arrives - and the page used
 * to say "Check your email... if nothing arrives, check your spam folder or try again",
 * which sent people round in a loop waiting for a message that could not come. It now says
 * so before they start, and again afterwards.
 */
export default function ForgotPasswordPage() {
  const [fieldErrors, setFieldErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [requested, setRequested] = useState(false);
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
      setRequested(true);
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

  if (requested) {
    return (
      <>
        <h1 className="mb-6 text-4xl font-bold">Reset link requested</h1>
        <Alert tone="info" title="If that address has an account, a reset link has been issued">
          This demonstration does not send email, so the link will not arrive. To use a
          demonstration account, sign in with the password shown on the sign-in page.
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
      <p className="mb-4 text-nhs-dark-grey">
        Enter your email address to request a link to set a new password.
      </p>

      <Alert tone="info" title="This demonstration does not send email">
        A reset link is issued, but it is not delivered anywhere, so it will not reach you.
        Demonstration accounts use the password shown on the{" "}
        <Link href="/login">sign-in page</Link>.
      </Alert>

      <form onSubmit={handleSubmit} noValidate>
        <ErrorSummary errors={fieldErrors} />
        {formError && (
          <Alert tone="error" title="Could not request a reset link" focusOnMount>
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

        <Button type="submit" size="lg" loading={submitting} loadingText="Requesting">
          Request a reset link
        </Button>
      </form>

      <hr className="my-8 border-nhs-pale-grey" />
      <p>
        <Link href="/login">Back to sign in</Link>
      </p>
    </>
  );
}
