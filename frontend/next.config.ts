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
   * Proxying keeps the session cookie first-party, removes the CORS preflight from every
   * request, and keeps the backend's address out of the browser entirely.
   *
   * API_ORIGIN is read when this config is evaluated at build time and written into the
   * routes manifest, which is why it is a Docker build argument - see Dockerfile.frontend.
   *
   * (This comment used to say the proxy was introduced to fix a WebKit cookie defect. That
   * was a misdiagnosis - see docs/testing/cross-browser.md §3 - and the proxy is kept on its
   * own merits.)
   */
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
  },

  experimental: {
    // How long the rewrite proxy waits for the API. Next's default is 30 seconds. On
    // Render's free tier a sleeping API takes about a minute to wake, so the first sign-in
    // after a quiet spell would otherwise fail with a timeout that looks like an outage.
    proxyTimeout: 120_000,
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
