import Link from "next/link";

import { Alert } from "@/components/ui";

export default function NotAuthorisedPage() {
  return (
    <main id="main-content" className="mx-auto w-full max-w-xl flex-1 px-4 py-12">
      <h1 className="mb-6 text-4xl font-bold">You cannot view this page</h1>
      <Alert tone="error" title="Permission denied">
        Your account does not have access to this part of the service. If you think this
        is wrong, contact your system administrator.
      </Alert>
      <p>
        <Link href="/">Go to the home page</Link>
      </p>
    </main>
  );
}
