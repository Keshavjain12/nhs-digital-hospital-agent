import type { Metadata, Viewport } from "next";

import { NonClinicalBanner, SkipLink } from "@/components/ui";
import { SessionProvider } from "@/features/auth/SessionProvider";

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
        <SkipLink />
        <NonClinicalBanner />
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
