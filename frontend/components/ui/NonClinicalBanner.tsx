"use client";

import { SafetyText } from "@/components/ui/SafetyText";
import { useT } from "@/lib/i18n";

/**
 * Required on every page by ASSUMPTIONS.md.
 *
 * This system is not NHS-approved, not clinically validated and holds no real patient
 * data. Anyone landing on a screen that looks like an NHS service must be told so
 * immediately - a demo mistaken for a real service is a patient safety problem, not a
 * presentational one.
 *
 * The 999 line is safety-critical, so in a draft locale it carries the English alongside.
 */
export function NonClinicalBanner() {
  const t = useT();

  return (
    <div className="border-b-4 border-nhs-warm-yellow bg-[#fff9e6]">
      <div className="mx-auto max-w-5xl px-4 py-2 text-center text-sm text-nhs-black">
        <strong>{t("banner.demo.title")}</strong> {t("banner.demo.body")}{" "}
        <SafetyText id="banner.demo.emergency" className="whitespace-nowrap font-bold" />
      </div>
    </div>
  );
}
