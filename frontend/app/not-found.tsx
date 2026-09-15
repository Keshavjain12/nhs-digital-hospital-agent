import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main id="main-content" className="mx-auto w-full max-w-xl flex-1 px-4 py-12">
        <h1 className="mb-4 text-4xl font-bold">Page not found</h1>
        <p className="mb-6">
          If you typed the address, check it is correct. If you pasted it, check you copied
          the whole thing.
        </p>
        <p>
          <Link href="/">Go to the home page</Link>
        </p>
      </main>
    </>
  );
}
