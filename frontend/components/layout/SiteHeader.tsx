import Link from "next/link";

/**
 * Header for pages outside the three portals: the landing page, sign-in, and error pages.
 *
 * Shared because it was not. The landing page carried its own copy of this markup, drifted
 * from it, and ended up as the one public page with no footer.
 */
export function SiteHeader() {
  return (
    <header className="bg-nhs-blue">
      <div className="mx-auto flex max-w-5xl items-center px-4 py-4">
        <Link href="/" className="text-xl font-bold text-white no-underline hover:underline">
          NHS Digital Hospital Agent
        </Link>
      </div>
    </header>
  );
}
