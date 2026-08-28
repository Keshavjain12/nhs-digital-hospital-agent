"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";

import { messages as cy } from "./messages/cy-GB";
import { messages as en, SAFETY_CRITICAL_KEYS } from "./messages/en-GB";
import type { MessageKey } from "./messages/en-GB";
import {
  DEFAULT_LOCALE,
  LOCALE_META,
  isLocale,
  resolveLocale,
  type Locale,
  type LocaleMeta,
} from "./locales";

const CATALOGUES: Record<Locale, Partial<Record<MessageKey, string>>> = {
  "en-GB": en,
  "cy-GB": cy,
};

const STORAGE_KEY = "preferred-locale";
const CHANGE_EVENT = "locale-change";

type Values = Record<string, string | number>;

function substitute(template: string, values?: Values): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}

/**
 * The browser's stored language choice, read through useSyncExternalStore.
 *
 * localStorage is external mutable state, which is exactly what this API exists for. The
 * alternative - reading it in an effect and calling setState - renders once with the wrong
 * language and then corrects itself, which flashes English at a Welsh speaker on every
 * page load.
 *
 * Subscribing to `storage` is a free bonus: changing language in one tab updates the others.
 */
function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function getStoredLocale(): Locale | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isLocale(stored) ? stored : null;
  } catch {
    // Private browsing or blocked site data. The profile preference still applies.
    return null;
  }
}

/** The server has no browser storage, so it always renders the profile preference. */
function getServerLocale(): Locale | null {
  return null;
}

interface I18nState {
  locale: Locale;
  meta: LocaleMeta;
  setLocale: (locale: Locale) => void;
  /** Translate. Falls back to English for any key this locale does not carry. */
  t: (key: MessageKey, values?: Values) => string;
  /** The authoritative English, whatever the active locale. Used by SafetyText. */
  english: (key: MessageKey, values?: Values) => string;
  /** True when the active locale's translations are unreviewed. */
  isDraft: boolean;
  isSafetyCritical: (key: MessageKey) => boolean;
}

const I18nContext = createContext<I18nState | null>(null);

export function I18nProvider({
  children,
  preferredLocale,
}: {
  children: ReactNode;
  /** The signed-in patient's stored preference, when there is one. */
  preferredLocale?: string | null;
}) {
  const chosen = useSyncExternalStore(subscribe, getStoredLocale, getServerLocale);

  // An explicit choice in this browser wins over the profile setting: someone who has just
  // switched language should not be overridden by a preference they may be about to change.
  const locale: Locale = chosen ?? resolveLocale(preferredLocale) ?? DEFAULT_LOCALE;

  // Keeps assistive technology and the browser's own language handling correct - it is what
  // makes a screen reader switch voice for translated content.
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = LOCALE_META[locale].direction;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not persisted, but the event below still applies it for this page view.
    }
    // `storage` does not fire in the tab that made the change, so notify explicitly.
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  const value = useMemo<I18nState>(() => {
    const catalogue = CATALOGUES[locale];

    return {
      locale,
      meta: LOCALE_META[locale],
      setLocale,
      t: (key, values) => substitute(catalogue[key] ?? en[key] ?? key, values),
      english: (key, values) => substitute(en[key] ?? key, values),
      isDraft: LOCALE_META[locale].status === "DRAFT",
      isSafetyCritical: (key) => SAFETY_CRITICAL_KEYS.has(key),
    };
  }, [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nState {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used within an I18nProvider");
  return context;
}

/** Convenience for the common case. */
export function useT(): I18nState["t"] {
  return useI18n().t;
}

export type { Locale, MessageKey };
export { LOCALE_META, LOCALES } from "./locales";
