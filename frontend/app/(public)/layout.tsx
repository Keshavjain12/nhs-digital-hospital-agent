import { SiteHeader } from "@/components/layout/SiteHeader";

/**
 * Shell for signed-out pages: login, registration and password reset.
 *
 * The footer is not here. It lives in the root layout so that no page - public or signed
 * in - can be left without it, which is exactly what happened while it lived here.
 */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main id="main-content" className="mx-auto w-full max-w-xl flex-1 px-4 py-8">
        {children}
      </main>
    </>
  );
}
