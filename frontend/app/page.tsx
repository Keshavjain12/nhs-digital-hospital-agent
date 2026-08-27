import Link from "next/link";

import { Card } from "@/components/ui";

export default function HomePage() {
  return (
    <>
      <header className="bg-nhs-blue">
        <div className="mx-auto max-w-5xl px-4 py-4">
          <span className="text-xl font-bold text-white">NHS Digital Hospital Agent</span>
        </div>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        <h1 className="mb-4 text-4xl font-bold">Your hospital care, in one place</h1>
        <p className="mb-8 max-w-2xl text-lg">
          Describe your symptoms, book and manage appointments, and see the information
          your care team holds about you.
        </p>

        <div className="grid gap-6 md:grid-cols-2">
          <Card title="Patients">
            <p className="mb-4">
              Book, reschedule or cancel an appointment and check your details.
            </p>
            <Link href="/login" className="font-bold">
              Sign in to your account
            </Link>
          </Card>

          <Card title="New here?">
            <p className="mb-4">Create an account to get started.</p>
            <Link href="/register" className="font-bold">
              Create an account
            </Link>
          </Card>
        </div>
      </main>
    </>
  );
}
