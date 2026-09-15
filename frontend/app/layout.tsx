import type { Metadata, Viewport } from "next";

import { SiteFooter } from "@/components/layout/SiteFooter";
import { NonClinicalBanner, SkipLink } from "@/components/ui";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { LocalisedShell } from "@/features/i18n/LocalisedShell";
import { QueryProvider } from "@/lib/query";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NHS Digital Hospital Agent (demonstration)",
    template: "%s - NHS Digital Hospital Agent (demonstration)",
  },
  description:
    "A demonstration hospital platform. Not an NHS service and not for clinical use.",
  // Nothing here should ever be indexed: it looks like an NHS service and is not one.
  robots: { index: false, follow: false },
};

/**
 * Rendered per request rather than prerendered, so the CSP nonce can be real.
 *
 * A nonce is by definition per response, and a statically prerendered page is one response
 * reused for everyone - so Next cannot stamp a nonce into it, and every script it emits is
 * refused by a `strict-dynamic` policy. The first production build did exactly that: the
 * HTML arrived, every chunk was blocked, and the app sat on "Checking your sign-in
 * details…" forever, with no server-side error to show for it.
 *
 * The alternative was `script-src 'unsafe-inline'`, which is the thing a CSP mostly exists
 * to prevent. Static prerendering buys very little here anyway - every page is client
 * rendered and takes its data from the API at request time, so what is being cached is an
 * empty shell.
 */
export const dynamic = "force-dynamic";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // maximumScale is deliberately unset. Blocking zoom fails WCAG 1.4.4 and is actively
  // hostile to the low-vision users this service must serve.
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body className="flex min-h-screen flex-col bg-nhs-white">
        <QueryProvider>
          <SessionProvider>
            {/* The shell owns the locale, so the banner and skip link are translated too.
                It sits inside SessionProvider because the patient's stored language
                preference is part of their session. */}
            <LocalisedShell>
              <SkipLink />
              <NonClinicalBanner />
              {children}
              {/* Once, here, so no page can be left without it - see SiteFooter. */}
              <SiteFooter />
            </LocalisedShell>
          </SessionProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
