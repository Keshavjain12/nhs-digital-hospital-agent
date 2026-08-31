"use client";

import Link from "next/link";

import { Button, LanguageSwitcher, TranslationNotice } from "@/components/ui";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { useSession } from "@/features/auth/SessionProvider";
import { useT } from "@/lib/i18n";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useSession();
  const t = useT();

  return (
    <RequireAuth roles={["PATIENT"]}>
      <header className="bg-nhs-blue">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <Link href="/dashboard" className="text-xl font-bold text-white no-underline hover:underline">
            {t("common.serviceName")}
          </Link>
          <div className="flex flex-wrap items-center gap-4">
            {user && (
              <span className="text-white">
                {t("common.signedInAs", { name: user.displayName })}
              </span>
            )}
            <LanguageSwitcher />
            <Button variant="secondary" onClick={() => void signOut()}>
              {t("common.signOut")}
            </Button>
          </div>
        </div>
        <nav aria-label="Your account" className="border-t border-white/20">
          <div className="mx-auto flex max-w-5xl flex-wrap gap-x-6 px-4">
            <Link href="/dashboard" className="py-3 font-bold text-white no-underline hover:underline">
              {t("nav.overview")}
            </Link>
            <Link
              href="/symptom-check"
              className="py-3 font-bold text-white no-underline hover:underline"
            >
              {t("nav.symptomCheck")}
            </Link>
            <Link
              href="/appointments"
              className="py-3 font-bold text-white no-underline hover:underline"
            >
              {t("nav.appointments")}
            </Link>
          </div>
        </nav>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <TranslationNotice />
        {children}
      </main>
    </RequireAuth>
  );
}
