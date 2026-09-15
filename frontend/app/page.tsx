import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { Card } from "@/components/ui";

/**
 * The public front door.
 *
 * Says what the service does for each of the three groups it serves, how to try it, and -
 * as plainly as everything else - what it is not. It sits outside the (public) route group
 * because it needs the full page width, so it takes the shared header directly. The footer
 * comes from the root layout, like every other page.
 */

const GROUPS = [
  {
    title: "Patients",
    points: [
      "Describe your symptoms to an automated check that suggests how soon you should be seen.",
      "Book, change or cancel hospital appointments. A time is held for you while you confirm.",
      "Use the patient screens in English or Welsh (a draft translation).",
    ],
  },
  {
    title: "Clinical staff",
    points: [
      "A working list of patients showing the check's suggested urgency, marked as not yet reviewed until a clinician has looked.",
      "Records open only to the patient's care team. Emergency access is possible, and is permanently recorded.",
      "Accept or change every automated suggestion. The original is kept alongside the clinician's decision.",
    ],
  },
  {
    title: "Operations",
    points: [
      "Activity across the service, and an audit trail of who opened what.",
      "How often clinicians agree with the automated check, with under- and over-triage shown separately.",
      "No access to clinical records: operational authority is not clinical authority.",
    ],
  },
] as const;

export default function HomePage() {
  return (
    <>
      <SiteHeader />

      <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        <h1 className="mb-4 text-4xl font-bold">Your hospital care, in one place</h1>
        <p className="mb-8 max-w-2xl text-lg">
          Describe your symptoms, book and manage appointments, and see the information
          your care team holds about you.
        </p>

        <div className="mb-12 grid gap-6 md:grid-cols-2">
          <Card title="Already have an account?">
            <p className="mb-4">
              Patients, clinical staff and operations staff all sign in here.
            </p>
            <Link href="/login" className="font-bold">
              Sign in to your account
            </Link>
          </Card>

          <Card title="New here?">
            <p className="mb-4">Create a patient account to get started.</p>
            <Link href="/register" className="font-bold">
              Create an account
            </Link>
          </Card>
        </div>

        <section aria-labelledby="what-it-does" className="mb-12">
          <h2 id="what-it-does" className="mb-6 text-2xl font-bold">
            What it does
          </h2>
          <div className="grid gap-8 md:grid-cols-3">
            {GROUPS.map((group) => (
              <section key={group.title} className="border-t-4 border-nhs-blue pt-4">
                <h3 className="mb-3 text-xl font-bold">{group.title}</h3>
                <ul className="list-disc space-y-2 pl-5">
                  {group.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </section>

        <section aria-labelledby="trying-it" className="mb-12">
          <h2 id="trying-it" className="mb-4 text-2xl font-bold">
            Trying the demonstration
          </h2>
          <p className="mb-2 max-w-3xl">
            There is a demonstration account for each role - patient, nurse, doctor and
            administrator - so you can see each part of the service as its users would.
            They are listed on the <Link href="/login">sign-in page</Link>.
          </p>
          <p className="max-w-3xl">
            Every person and record in the service is synthetic. None of it describes a real
            patient.
          </p>
        </section>

        <section
          aria-labelledby="what-it-is-not"
          className="border-l-4 border-nhs-warm-yellow bg-[#fff9e6] p-6"
        >
          <h2 id="what-it-is-not" className="mb-3 text-2xl font-bold">
            What this is not
          </h2>
          <ul className="mb-4 list-disc space-y-2 pl-5">
            <li>
              It is not an NHS service, and is not approved, assessed or endorsed by the NHS.
            </li>
            <li>
              It is not clinically validated. The symptom check is an automated set of rules,
              not a clinician, and it does not diagnose.
            </li>
            <li>It must not be used for real patients or real health decisions.</li>
          </ul>
          <p className="font-bold">
            If you are unwell, use{" "}
            <a href="https://111.nhs.uk" rel="noreferrer noopener" target="_blank">
              NHS 111 online<span className="sr-only"> (opens in a new tab)</span>
            </a>{" "}
            or call 111. In an emergency call 999.
          </p>
        </section>
      </main>
    </>
  );
}
