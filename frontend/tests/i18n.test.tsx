/**
 * Internationalisation tests.
 *
 * The interesting property is not that strings translate - it is what happens to the
 * strings that carry health advice when the translation has not been checked. Those must
 * never be shown alone in a draft locale, and a missing key must never surface as a raw
 * identifier to a patient.
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { SafetyText } from "@/components/ui";
import { I18nProvider, useI18n, useT } from "@/lib/i18n";
import { LOCALES, LOCALE_META } from "@/lib/i18n/locales";
import { messages as cy } from "@/lib/i18n/messages/cy-GB";
import { messages as en, SAFETY_CRITICAL_KEYS } from "@/lib/i18n/messages/en-GB";
import type { MessageKey } from "@/lib/i18n/messages/en-GB";

function setStoredLocale(locale: string | null) {
  if (locale === null) window.localStorage.removeItem("preferred-locale");
  else window.localStorage.setItem("preferred-locale", locale);
}

beforeEach(() => {
  setStoredLocale(null);
});

function Show({ id }: { id: MessageKey }) {
  const t = useT();
  return <p>{t(id)}</p>;
}

function LocaleName() {
  const { locale, isDraft } = useI18n();
  return (
    <p>
      {locale}
      {isDraft ? " draft" : " authoritative"}
    </p>
  );
}

// --- Catalogue integrity --------------------------------------------------------


describe("message catalogues", () => {
  it("has no empty English strings", () => {
    for (const [key, value] of Object.entries(en)) {
      expect(value.trim(), `${key} is empty`).not.toBe("");
    }
  });

  it("has no Welsh key that English does not define", () => {
    // A stale translation key is dead text nobody notices. Typing cy as a Partial of the
    // English catalogue makes this a compile error too; this catches it at runtime as well.
    for (const key of Object.keys(cy)) {
      expect(en, `cy-GB defines ${key}, which English does not`).toHaveProperty(key);
    }
  });

  it("translates every safety-critical key it claims to support", () => {
    // A safety key half-translated is the worst case: some of the advice in Welsh, some in
    // English, with no indication which is which.
    const translatedSafetyKeys = [...SAFETY_CRITICAL_KEYS].filter((key) => key in cy);
    expect(translatedSafetyKeys.length).toBeGreaterThan(0);

    for (const key of translatedSafetyKeys) {
      expect(cy[key]?.trim()).not.toBe("");
    }
  });

  it("keeps every placeholder that the English string uses", () => {
    // Dropping {name} from a translation renders a sentence with a hole in it.
    const placeholders = (value: string) => (value.match(/\{(\w+)\}/g) ?? []).sort();

    for (const [key, welsh] of Object.entries(cy)) {
      const english = en[key as MessageKey];
      expect(placeholders(welsh), `${key} placeholders differ`).toEqual(placeholders(english));
    }
  });

  it("declares provenance for every locale", () => {
    for (const locale of LOCALES) {
      expect(LOCALE_META[locale].status).toMatch(/^(AUTHORITATIVE|DRAFT)$/);
      expect(LOCALE_META[locale].nativeName).toBeTruthy();
    }
  });

  it("marks the Welsh catalogue as a draft", () => {
    // It is machine-drafted. Marking it authoritative would suppress every safeguard that
    // depends on this flag.
    expect(LOCALE_META["cy-GB"].status).toBe("DRAFT");
  });
});

// --- Translation ------------------------------------------------------------------

describe("translation", () => {
  it("renders English by default", () => {
    render(
      <I18nProvider>
        <Show id="dashboard.title" />
      </I18nProvider>,
    );

    expect(screen.getByText("Your account")).toBeInTheDocument();
  });

  it("uses the patient's stored language preference", () => {
    render(
      <I18nProvider preferredLocale="cy-GB">
        <Show id="dashboard.title" />
      </I18nProvider>,
    );

    expect(screen.getByText("Eich cyfrif")).toBeInTheDocument();
  });

  it("lets an explicit choice in this browser win over the profile", () => {
    // Someone who has just switched language should not be overridden by a profile setting
    // they may be about to change.
    setStoredLocale("en-GB");

    render(
      <I18nProvider preferredLocale="cy-GB">
        <Show id="dashboard.title" />
      </I18nProvider>,
    );

    expect(screen.getByText("Your account")).toBeInTheDocument();
  });

  it("falls back to English for an unsupported patient language", () => {
    // Patient records carry pl-PL, ar and tr, which this service does not translate.
    // Showing Welsh to a Polish speaker because both are "not English" would be worse.
    render(
      <I18nProvider preferredLocale="pl-PL">
        <Show id="dashboard.title" />
      </I18nProvider>,
    );

    expect(screen.getByText("Your account")).toBeInTheDocument();
  });

  it("falls back to English for a key the locale does not carry", () => {
    // A partial translation must degrade into a usable page, never a raw key.
    render(
      <I18nProvider preferredLocale="cy-GB">
        <Show id="common.serviceName" />
      </I18nProvider>,
    );

    expect(screen.getByText("NHS Digital Hospital Agent")).toBeInTheDocument();
  });

  it("substitutes placeholders", () => {
    function Welcome() {
      const t = useT();
      return <p>{t("dashboard.welcome", { name: "Priya" })}</p>;
    }

    render(
      <I18nProvider>
        <Welcome />
      </I18nProvider>,
    );

    expect(screen.getByText("Welcome back, Priya.")).toBeInTheDocument();
  });

  it("reports whether the active locale is a draft", () => {
    render(
      <I18nProvider preferredLocale="cy-GB">
        <LocaleName />
      </I18nProvider>,
    );

    expect(screen.getByText("cy-GB draft")).toBeInTheDocument();
  });
});

// --- The safety mechanism -----------------------------------------------------------

describe("SafetyText", () => {
  it("shows the translation alone in an authoritative locale", () => {
    render(
      <I18nProvider preferredLocale="en-GB">
        <SafetyText id="symptomCheck.emergency.title" />
      </I18nProvider>,
    );

    expect(screen.getByText("Call 999 now")).toBeInTheDocument();
    expect(screen.queryByText(/\(/)).not.toBeInTheDocument();
  });

  it("shows the English alongside a draft translation", () => {
    // A mistranslated emergency instruction is a safety risk, not a cosmetic defect.
    // Showing both lets the reader use whichever they trust.
    render(
      <I18nProvider preferredLocale="cy-GB">
        <SafetyText id="symptomCheck.emergency.title" />
      </I18nProvider>,
    );

    expect(screen.getByText("Ffoniwch 999 nawr")).toBeInTheDocument();
    expect(screen.getByText("(Call 999 now)")).toBeInTheDocument();
  });

  it("marks the English with lang so a screen reader switches voice", () => {
    render(
      <I18nProvider preferredLocale="cy-GB">
        <SafetyText id="symptomCheck.emergency.body" />
      </I18nProvider>,
    );

    expect(screen.getByText(/^\(What you have described/)).toHaveAttribute("lang", "en-GB");
  });

  it("does not duplicate a non-safety string in a draft locale", () => {
    render(
      <I18nProvider preferredLocale="cy-GB">
        <SafetyText id="nav.appointments" />
      </I18nProvider>,
    );

    expect(screen.getByText("Apwyntiadau")).toBeInTheDocument();
    expect(screen.queryByText("(Appointments)")).not.toBeInTheDocument();
  });

  it("does not duplicate when a safety key is untranslated", () => {
    // The fallback already rendered English; showing it twice would be noise.
    render(
      <I18nProvider preferredLocale="cy-GB">
        <SafetyText id="symptomCheck.outcome.producedBy" values={{ engine: "rules 0.3.0" }} />
      </I18nProvider>,
    );

    expect(screen.queryByText(/^\(/)).not.toBeInTheDocument();
  });

  it("covers every string that tells someone what to do about their health", () => {
    // A key missing from this set renders unreviewed clinical advice with no English
    // alongside, which is the failure this whole mechanism exists to prevent.
    const mustBeCovered: MessageKey[] = [
      "symptomCheck.emergency.title",
      "symptomCheck.emergency.body",
      "symptomCheck.emergencyBanner.title",
      "symptomCheck.emergencyBanner.body",
      "symptomCheck.outcome.notADiagnosis",
      "symptomCheck.outcome.ifWorse",
      "symptomCheck.band.URGENT",
      "symptomCheck.band.SOON",
      "banner.demo.emergency",
    ];

    for (const key of mustBeCovered) {
      expect(SAFETY_CRITICAL_KEYS.has(key), `${key} must be safety-critical`).toBe(true);
    }
  });
});
