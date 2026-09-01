"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, setAccessToken } from "@/lib/api";
import type { LoginResponse, UserSummary } from "@/types/api";

interface SessionState {
  user: UserSummary | null;
  /** True until the initial session restore finishes. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<UserSummary>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * Restore the session on load.
   *
   * The access token lives only in memory, so a refresh loses it. The httpOnly refresh
   * cookie survives, and this exchange turns it back into a usable session - which is
   * what makes memory-only storage practical rather than merely secure.
   */
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        // Through the shared, deduplicated path rather than posting to /auth/refresh
        // directly. This effect runs on every page load, and two of them overlapping -
        // a navigation starting before the previous one's rotated cookie came back -
        // replays a spent token. The server reads that as reuse and ends every session
        // the user has, on every device. Going through api.restoreSession() means only
        // one exchange is ever in flight.
        const restored = await api.restoreSession();
        if (!restored) throw new Error("no session");

        const me = await api.get<UserSummary>("/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        // No valid session. Not an error: this is the ordinary state for a signed-out
        // visitor, and surfacing it would put a spurious message on the login page.
        if (!cancelled) {
          setAccessToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await api.post<LoginResponse>(
      "/auth/login",
      { email, password },
      { retryOnUnauthorised: false },
    );
    setAccessToken(result.accessToken);
    setUser(result.user);
    return result.user;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      // Local state is cleared even if the call fails. Leaving a user looking signed in
      // after they asked to sign out is worse than a server-side token lingering until
      // it expires.
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn, signOut }),
    [user, loading, signIn, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
