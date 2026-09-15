import { NextResponse, type NextRequest } from "next/server";

/**
 * Content-Security-Policy, applied per request so it can carry a nonce.
 *
 * `next.config.ts` has carried a note since Sprint 1 saying a CSP was not added because
 * Next's dev overlay and its inline bootstrap need nonce plumbing, and "a CSP that has to
 * be disabled in development is one nobody trusts in production". This is that plumbing.
 *
 * A nonce cannot come from `headers()` in next.config.ts, which is static. It has to be
 * generated per response, which is what this proxy is for: the nonce goes into the CSP
 * header and into a request header that Next reads to stamp its own inline scripts.
 *
 * Development keeps a deliberately looser policy. The dev server needs `unsafe-eval` for
 * React Refresh and inline styles for the error overlay, and pretending otherwise would
 * mean either a broken dev experience or a policy quietly relaxed everywhere. The
 * difference is confined to this file and stated out loud.
 *
 * Named proxy.ts rather than middleware.ts because Next.js 16 deprecated the old file
 * convention and warned on every start. The behaviour is unchanged.
 */

const isProduction = process.env.NODE_ENV === "production";

function contentSecurityPolicy(nonce: string, overHttps: boolean): string {
  const scriptSrc = isProduction
    ? `'self' 'nonce-${nonce}' 'strict-dynamic'`
    : `'self' 'unsafe-eval' 'unsafe-inline'`;

  // Styles: Next injects inline <style> for critical CSS and Tailwind's runtime, and those
  // are not nonce-stamped, so 'unsafe-inline' is required for styles even in production.
  // Worth being honest that this is a real weakening - style injection can exfiltrate data
  // through selectors - rather than leaving it to look like an oversight.
  const styleSrc = "'self' 'unsafe-inline'";

  return [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    `style-src ${styleSrc}`,
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    // The API is same-origin (see the rewrite in next.config.ts), so 'self' is all that is
    // needed. If the API is ever moved back to its own origin this must be widened to
    // match.
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'none'",
    "object-src 'none'",
    // Only when the request already arrived over TLS.
    //
    // Keyed on NODE_ENV first, and that was wrong. The production image served over plain
    // HTTP told the browser to upgrade every subresource to https://, where nothing was
    // listening. Chromium and Firefox exempt localhost and carried on; WebKit does not, so
    // every script failed with an SSL error and Safari could not sign in at all - a bug
    // introduced by the security header itself.
    //
    // Upgrading subresources of a page that was itself fetched over HTTP is incoherent
    // anyway, so the condition belongs on the scheme, not the build mode.
    ...(overHttps ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");

  // x-forwarded-proto first: behind a TLS-terminating proxy the request reaches this
  // server over plain HTTP even though the browser used HTTPS, and only the header knows.
  const forwarded = request.headers.get("x-forwarded-proto");
  const overHttps = forwarded
    ? forwarded.split(",")[0].trim() === "https"
    : request.nextUrl.protocol === "https:";

  // Next reads x-nonce and applies it to the script tags it generates itself.
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);

  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", contentSecurityPolicy(nonce, overHttps));
  return response;
}

export const config = {
  matcher: [
    /*
     * Everything except static assets and the proxied API.
     *
     * The API sets its own security headers, and it sets a stricter CSP than this one
     * because it serves JSON rather than a page. Wrapping it here would replace a tight
     * policy with a looser one.
     */
    {
      source: "/((?!api/|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
