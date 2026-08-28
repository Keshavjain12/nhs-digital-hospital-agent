"use client";

import type { ReactNode } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { I18nProvider } from "@/lib/i18n";

/**
 * Supplies the locale to everything below it.
 *
 * Reads the signed-in patient's stored language preference so the choice follows them
 * between devices, rather than living only in one browser. An explicit switch still wins
 * for the current browser - see I18nProvider.
 */
export function LocalisedShell({ children }: { children: ReactNode }) {
  const { user } = useSession();

  return (
    <I18nProvider preferredLocale={user?.preferredLanguage ?? null}>{children}</I18nProvider>
  );
}
