import Link from "next/link";

/** Shell for signed-out pages: login, registration and password reset. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="bg-nhs-blue">
        <div className="mx-auto flex max-w-5xl items-center px-4 py-4">
          <Link
            href="/"
            className="text-xl font-bold text-white no-underline hover:underline"
          >
            NHS Digital Hospital Agent
          </Link>
        </div>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-xl flex-1 px-4 py-8">
        {children}
      </main>

      <footer className="mt-8 border-t-4 border-nhs-blue bg-nhs-pale-grey">
        <div className="mx-auto max-w-5xl px-4 py-6 text-sm">
          <p className="mb-2">
            This is a student demonstration project. It is not affiliated with, endorsed
            by, or connected to the NHS.
          </p>
          <p>
            For medical advice use{" "}
            <a href="https://111.nhs.uk" rel="noreferrer noopener" target="_blank">
              NHS 111
            </a>
            . In an emergency call 999.
          </p>
        </div>
      </footer>
    </>
  );
}
