"use client";

import { useI18n, type MessageKey } from "@/lib/i18n";

/**
 * Renders a string that carries health advice.
 *
 * In an AUTHORITATIVE locale this is just the text. In a DRAFT locale it renders the
 * translation *and* the English beneath it, marked with `lang="en-GB"` so a screen reader
 * switches voice rather than reading English with Welsh pronunciation.
 *
 * The reasoning: a mistranslated emergency instruction is a patient safety risk, not a
 * cosmetic defect. Showing only unreviewed wording in someone's own language is worse than
 * showing none, because the reader has no way to know it is unreliable. Showing both lets
 * them read whichever they trust.
 *
 * Falling back to English alone was the other option and is worse: it silently denies the
 * translation to the people who most need it.
 */
export function SafetyText({
  id,
  values,
  className,
}: {
  id: MessageKey;
  values?: Record<string, string | number>;
  className?: string;
}) {
  const { t, english, isDraft, isSafetyCritical, locale } = useI18n();
  const translated = t(id, values);
  const authoritative = english(id, values);

  const needsBoth = isDraft && isSafetyCritical(id) && translated !== authoritative;

  if (!needsBoth) return <span className={className}>{translated}</span>;

  return (
    <span className={className}>
      <span lang={locale}>{translated}</span>{" "}
      <span lang="en-GB" className="text-nhs-dark-grey">
        ({authoritative})
      </span>
    </span>
  );
}
