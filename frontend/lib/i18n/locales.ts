/**
 * Supported locales and their translation provenance.
 *
 * `status` is the important field and is not decoration.
 *
 *   AUTHORITATIVE - written by, or professionally translated and clinically checked for,
 *                   this service. Safe to show on its own.
 *   DRAFT         - not professionally translated and not clinically checked. Usable for
 *                   navigation and general copy, but never the sole rendering of anything
 *                   that affects a decision about care.
 *
 * The distinction exists because a mistranslated emergency instruction is a patient safety
 * risk, not a cosmetic defect. A service that quietly shows unreviewed clinical wording in
 * someone's own language is more dangerous than one that shows none, because the reader has
 * no way to know it is unreliable.
 *
 * Welsh is the demonstration locale because Welsh language provision is a statutory duty for
 * public bodies in Wales, which makes it the requirement most likely to be real rather than
 * aspirational. Adding another locale is one file plus one entry here.
 */

export const LOCALES = ["en-GB", "cy-GB"] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en-GB";

export interface LocaleMeta {
  code: Locale;
  /** The language's name in that language, which is how a speaker recognises it. */
  nativeName: string;
  englishName: string;
  status: "AUTHORITATIVE" | "DRAFT";
  direction: "ltr" | "rtl";
}

export const LOCALE_META: Record<Locale, LocaleMeta> = {
  "en-GB": {
    code: "en-GB",
    nativeName: "English",
    englishName: "English",
    status: "AUTHORITATIVE",
    direction: "ltr",
  },
  "cy-GB": {
    code: "cy-GB",
    nativeName: "Cymraeg",
    englishName: "Welsh",
    // Machine-drafted for this demonstration. Real use needs a professional translator and
    // a clinical check of every string that carries advice.
    status: "DRAFT",
    direction: "ltr",
  },
};

export function isLocale(value: string | null | undefined): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/**
 * Map a stored patient language preference onto a supported locale.
 *
 * Patient records carry codes this service does not translate into - `pl-PL`, `ar`, `tr`.
 * Those fall back to English rather than to a half-match: showing Welsh to a Polish speaker
 * because both are "not English" would be worse than showing English.
 */
export function resolveLocale(preferred: string | null | undefined): Locale {
  if (isLocale(preferred)) return preferred;
  return DEFAULT_LOCALE;
}
