"use client";

import { SafetyText } from "@/components/ui/SafetyText";
import { useT } from "@/lib/i18n";

/**
 * The footer, rendered once by the root layout so that no page can be left without it.
 *
 * It used to live in the public route group's layout, which meant the landing page, the
 * not-found page and every signed-in screen had none - so the most public page in a
 * service that deliberately looks NHS-branded was missing the line saying it is not
 * connected to the NHS.
 *
 * The 999 line reuses the banner's safety-critical string, so a draft translation shows
 * the English alongside it here too.
 */
export function SiteFooter() {
  const t = useT();

  return (
    <footer className="mt-8 border-t-4 border-nhs-blue bg-nhs-pale-grey">
      <div className="mx-auto max-w-5xl px-4 py-6 text-sm">
        <p className="mb-2">{t("footer.notAffiliated")}</p>
        <p>
          {t("footer.medicalAdvice")}{" "}
          <a href="https://111.nhs.uk" rel="noreferrer noopener" target="_blank">
            NHS 111
            <span className="sr-only"> {t("footer.opensInNewTab")}</span>
          </a>
          . <SafetyText id="banner.demo.emergency" className="font-bold" />
        </p>
      </div>
    </footer>
  );
}
