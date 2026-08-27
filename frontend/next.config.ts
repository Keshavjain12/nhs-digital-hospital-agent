import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The repo documents its own conventions in CONTRIBUTING.md; a generated agent file
  // would be a second, drifting source of truth.
  agentRules: false,

  // Security headers for the frontend. The API sets its own; these cover the HTML the
  // browser loads. A CSP is not added here yet: Next's dev overlay and its inline
  // bootstrap need nonce plumbing to work, and a CSP that has to be disabled in
  // development is one nobody trusts in production. Tracked for Sprint 4 hardening.
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
