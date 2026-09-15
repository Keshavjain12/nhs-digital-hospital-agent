"use client";

/**
 * Last-resort error screen, used only when the root layout itself fails.
 *
 * It replaces the whole document, so none of the usual providers exist - no translations,
 * no session, and none of the shared components that depend on them. Plain markup and
 * inline styles only, carrying the one thing that matters most on a health service: where
 * to get real help.
 */
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en-GB">
      <body style={{ fontFamily: "Arial, sans-serif", margin: 0, color: "#212b32" }}>
        <div
          style={{
            background: "#fff9e6",
            borderBottom: "4px solid #ffb81c",
            padding: "8px 16px",
            textAlign: "center",
            fontSize: 14,
          }}
        >
          <strong>Demonstration system.</strong> Not an NHS service. In an emergency call 999.
        </div>
        <main style={{ maxWidth: 640, margin: "0 auto", padding: "48px 16px" }}>
          <h1 style={{ fontSize: 36, marginTop: 0 }}>Sorry, the service is not working</h1>
          <p>Please try again in a few minutes.</p>
          <p>
            <strong>
              If you need medical help, use <a href="https://111.nhs.uk">NHS 111 online</a> or
              call 111. In an emergency call 999.
            </strong>
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              background: "#007f3b",
              color: "#ffffff",
              border: 0,
              padding: "12px 16px",
              fontSize: 16,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
