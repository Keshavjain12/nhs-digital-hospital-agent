"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { Alert, Button, ErrorSummary, TextInput } from "@/components/ui";
import { useSession } from "@/features/auth/SessionProvider";
import { loginSchema, toFieldErrors } from "@/features/auth/validation";
import { ApiError, NetworkError } from "@/lib/api";
import { resolvePostLoginPath } from "@/lib/routes";
import type { UserRole } from "@/types/api";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { signIn } = useSession();

  const [fieldErrors, setFieldErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors([]);

    const form = new FormData(event.currentTarget);
    const values = {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    };

    const parsed = loginSchema.safeParse(values);
    if (!parsed.success) {
      setFieldErrors(toFieldErrors(parsed.error));
      return;
    }

    setSubmitting(true);
    try {
      const user = await signIn(parsed.data.email, parsed.data.password);
      // Resolves `next` against both same-site rules and the role's own permissions, so a
      // stale value left in the address bar cannot drop the user on a page they are then
      // refused. See lib/routes.ts.
      router.replace(resolvePostLoginPath(user.role as UserRole, params.get("next")));
    } catch (error) {
      if (error instanceof ApiError) {
        // The message is the backend's own wording, which is deliberately identical for
        // an unknown account and a wrong password. Rewording it here could reintroduce
        // the enumeration difference the backend works to avoid.
        setFormError(error.message);
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
        <Alert tone="error" title="Could not sign in" focusOnMount>
          {formError}
        </Alert>
      )}

      <TextInput
        label="Email address"
        name="email"
        type="email"
        autoComplete="username"
        // Helps password managers and mobile keyboards; also reduces typos on a field
        // where a typo is indistinguishable from a wrong password.
        inputMode="email"
        spellCheck={false}
        required
        error={errorFor("email")}
      />

      <TextInput
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        error={errorFor("password")}
      />

      <Button type="submit" size="lg" loading={submitting} loadingText="Signing in">
        Sign in
      </Button>
    </form>
  );
}
