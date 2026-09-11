import type { NextConfig } from "next";

/**
 * Where the backend actually lives. Server-side only - deliberately not NEXT_PUBLIC_, so
 * the browser never learns the backend's address and never addresses it directly.
 */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The repo documents its own conventions in CONTRIBUTING.md; a generated agent file
  // would be a second, drifting source of truth.
  agentRules: false,

  // Emits a self-contained server bundle with only the dependencies actually reached, so
  // the production image does not have to carry node_modules.
  output: "standalone",

  /**
   * Serve the API under this app's own origin.
   *
   * This is not a convenience. Addressing the backend absolutely made every call
   * cross-origin, and WebKit responded by silently declining to store the rotated refresh
   * cookie: the third page load replayed a spent token, the server correctly read that as
   * reuse, and every session for that user was revoked. A Safari user was signed out on
   * their third page load, on every device. See docs/testing/cross-browser.md §3.
   *
   * Proxying makes the session cookie first-party, removes the CORS preflight from every
   * request, and keeps the backend's address out of the browser entirely.
   */
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
  },

  // Security headers for the frontend. The API sets its own; these cover the HTML the
  // browser loads.
  //
  // The CSP is *not* here: it needs a per-request nonce, and headers() is static. It lives
  // in proxy.ts instead. These are the headers that do not vary per request.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "geolocation=(), microphone=(), camera=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
