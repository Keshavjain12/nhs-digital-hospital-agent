/**
 * The single HTTP entry point to the backend.
 *
 * Every request goes through here so that error-envelope decoding, credential handling
 * and access-token refresh exist in exactly one place. Brief §5: no component may
 * hard-code a fetch or a response shape.
 */

import type { ApiErrorBody, ErrorCode } from "@/types/api";

/**
 * Empty by default, which means "this origin".
 *
 * Requests go to /api/v1 on the app's own origin and are proxied to the backend by the
 * rewrite in next.config.ts. That keeps the session cookie first-party, removes the CORS
 * preflight from every request, and keeps the backend's address out of the browser. Set
 * NEXT_PUBLIC_API_BASE_URL only to deliberately talk to a different origin.
 *
 * This was originally changed in the belief that a cross-origin cookie was why WebKit
 * stopped storing the rotated refresh token. That turned out to be a misdiagnosis - the
 * sign-outs were a refresh race, not a browser defect (docs/testing/cross-browser.md §3).
 * The change is kept on its own merits.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const API_V1 = `${API_BASE_URL}/api/v1`;

/**
 * A failed request, carrying the backend's error envelope.
 *
 * `code` is the stable contract the UI branches on. `message` is written by the backend
 * to be safe to show a user verbatim, so it is displayed rather than replaced with our
 * own wording - which would drift from the API's meaning over time.
 */
export class ApiError extends Error {
  readonly code: ErrorCode | string;
  readonly status: number;
  readonly requestId?: string;
  readonly fieldErrors: ReadonlyArray<{ field: string; issue: string }>;

  constructor(status: number, body: ApiErrorBody, requestId?: string) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.requestId = body.error.requestId ?? requestId;
    this.fieldErrors = body.error.details ?? [];
  }

  /** True when re-sending the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.status >= 500 || this.status === 429;
  }
}

/** Thrown when the network fails outright, distinct from the server returning an error. */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super("We could not reach the service. Check your connection and try again.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

let accessToken: string | null = null;

/**
 * The access token is held in module memory, never in localStorage or a readable cookie.
 *
 * localStorage is readable by any script that manages to run on the page, which turns a
 * single XSS into a stolen session. Memory-only means the token dies with the tab, and
 * the httpOnly refresh cookie restores the session on reload.
 */
export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Set false for auth endpoints, so a 401 there does not trigger a refresh loop. */
  retryOnUnauthorised?: boolean;
  signal?: AbortSignal;
}

async function parseError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("X-Request-ID") ?? undefined;
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (body?.error?.code) return new ApiError(response.status, body, requestId);
  } catch {
    // Body was not JSON - fall through to the generic envelope below.
  }
  return new ApiError(
    response.status,
    {
      error: {
        code: "INTERNAL_ERROR",
        message: "Something went wrong. Please try again.",
      },
    },
    requestId,
  );
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  try {
    return await fetch(`${API_V1}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      // Required for the httpOnly refresh cookie to travel.
      credentials: "include",
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new NetworkError(cause);
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/**
 * Exchange the refresh cookie for a new access token.
 *
 * Deduplicated: if three requests 401 at once, they share one refresh rather than firing
 * three. That matters beyond efficiency - the backend rotates refresh tokens and treats
 * reuse as theft, so concurrent refreshes would revoke the user's own session.
 *
 * Exported because the session provider restores the session on every page load and was
 * calling POST /auth/refresh directly, going around this guard entirely. Two of those
 * overlapping is precisely the race the comment above describes, and it was signing users
 * out mid-session. Anything that needs a refresh must come through here.
 */
export async function refreshAccessToken(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await rawRequest("/auth/refresh", {
        method: "POST",
        retryOnUnauthorised: false,
      });
      if (!response.ok) {
        setAccessToken(null);
        return false;
      }
      const data = (await response.json()) as { accessToken: string };
      setAccessToken(data.accessToken);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await rawRequest(path, options);

  if (response.status === 401 && (options.retryOnUnauthorised ?? true)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await rawRequest(path, options);
    }
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}

export const api = {
  /** Restore a session from the refresh cookie. Deduplicated - see refreshAccessToken. */
  restoreSession: () => refreshAccessToken(),
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown, options: Partial<RequestOptions> = {}) =>
    request<T>(path, { method: "POST", body, ...options }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
