"use client";

import { LOCALES, LOCALE_META, useI18n, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/cn";

/**
 * Language choice.
 *
 * Each option is labelled in its own language - a Welsh speaker looks for "Cymraeg", not
 * for the English word "Welsh". A draft locale says so on the control itself, so the
 * limitation is visible before someone switches rather than after.
 */
export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <label htmlFor="locale" className="text-sm font-bold text-white">
        {t("common.language")}
      </label>
      <select
        id="locale"
        value={locale}
        onChange={(event) => setLocale(event.target.value as Locale)}
        aria-label={t("common.changeLanguage")}
        className="min-h-[44px] border-2 border-white bg-white px-2 py-1 text-base text-nhs-black"
      >
        {LOCALES.map((code) => (
          <option key={code} value={code} lang={code}>
            {LOCALE_META[code].nativeName}
            {LOCALE_META[code].status === "DRAFT" ? " (draft)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
