import type { Metadata } from "next";
import Link from "next/link";

import { Alert } from "@/components/ui";
import { RegisterForm } from "@/features/auth/components/RegisterForm";

export const metadata: Metadata = { title: "Create an account" };

export default function RegisterPage() {
  return (
    <>
      <h1 className="mb-2 text-4xl font-bold">Create an account</h1>
      <p className="mb-6 text-nhs-dark-grey">
        You need an account to book appointments and see your care information.
      </p>

      <Alert tone="warning" title="Do not enter real personal information">
        This is a demonstration system holding synthetic data only. Use made-up details.
      </Alert>

      <RegisterForm />

      <hr className="my-8 border-nhs-pale-grey" />
      <p>
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </>
  );
}
