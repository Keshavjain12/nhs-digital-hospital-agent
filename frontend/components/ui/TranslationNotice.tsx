"use client";

import { Alert } from "@/components/ui/Alert";
import { useI18n } from "@/lib/i18n";

/**
 * Shown on every page while a DRAFT locale is active.
 *
 * Deliberately written in English as well as the active language: someone who has switched
 * to a draft translation needs to understand the warning about that translation, and
 * warning them only in the language whose reliability is in question would be circular.
 */
export function TranslationNotice() {
  const { isDraft, t, english } = useI18n();
  if (!isDraft) return null;

  return (
    <Alert tone="warning" title={english("banner.draftTranslation.title")}>
      <p>{t("banner.draftTranslation.body")}</p>
      <p lang="en-GB" className="mt-2 text-sm text-nhs-dark-grey">
        {english("banner.draftTranslation.body")}
      </p>
    </Alert>
  );
}
