import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { WORK_REFRESH_INTERVAL_MS } from "@/config";
import { saveFeedback } from "@/lib/save-feedback";
import {
  ApiError,
  hasSessionHint,
  request,
  SESSION_HINT_KEY,
  setCsrfToken,
  setSessionHint,
  setUnauthorisedHandler,
} from "@/lib/api";
import type { SessionState, TokenResponse, User } from "@/types/api";

interface RegistrationInput {
  full_name: string;
  email: string;
  password: string;
  job_title: string | null;
  invitation_code?: string;
}

interface AuthState {
  user: User | null;
  status: "loading" | "authenticated" | "anonymous";
  signIn: (email: string, password: string) => Promise<void>;
  register: (input: RegistrationInput) => Promise<void>;
  signOut: () => Promise<void>;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

// Set when the reader signs out, so whoever signs in next starts from home, not the last page.
let endedByReader = false;

/** True after a deliberate sign-out in this tab, until someone signs in again. */
export function sessionEndedByReader(): boolean {
  return endedByReader;
}

// An active tab renews its session this close to expiry. The server still ends every session a fixed
// time after the password was last entered, so renewal cannot extend a session indefinitely.
const RENEW_WHEN_SECONDS_LEFT = 10 * 60;

/** Milliseconds since the epoch, or null when the server sent no readable time. */
function parseExpiry(value: string | null | undefined): number | null {
  const time = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(time) ? null : time;
}

function expiryAfter(seconds: number): number {
  return Date.now() + seconds * 1000;
}

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const expiresAt = useRef<number | null>(null);

  const remember = useCallback((csrfToken: string | null | undefined, expiry: number | null) => {
    setCsrfToken(csrfToken ?? null);
    expiresAt.current = expiry;
  }, []);

  // Local only: after a 401 or another tab's sign-out the server session is already gone.
  const clearSession = useCallback(() => {
    saveFeedback.clear();
    setSessionHint(false);
    remember(null, null);
    queryClient.clear();
    setUser(null);
    setStatus("anonymous");
  }, [queryClient, remember]);

  const startSession = useCallback((result: TokenResponse) => {
    queryClient.clear();
    remember(result.csrf_token, expiryAfter(result.expires_in_seconds));
    setSessionHint(true);
    setUser(result.user);
    setStatus("authenticated");
  }, [queryClient, remember]);

  useEffect(() => {
    setUnauthorisedHandler(clearSession);
    return () => setUnauthorisedHandler(null);
  }, [clearSession]);

  // Restore the session on load so a refresh does not force a new sign-in.
  useEffect(() => {
    let cancelled = false;
    if (!hasSessionHint()) {
      setStatus("anonymous");
      return undefined;
    }
    async function restore(): Promise<void> {
      try {
        const profile = await request<User>("/auth/me");
        // This only recovers the CSRF token and expiry, so its failure must not end a live session.
        const session = await request<SessionState>("/auth/session").catch(() => null);
        if (cancelled || !hasSessionHint()) return;
        if (session) remember(session.csrf_token, parseExpiry(session.expires_at));
        setUser(profile);
        setStatus("authenticated");
      } catch {
        if (!cancelled) clearSession();
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, [clearSession, remember]);

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    let cancelled = false;
    let refreshing = false;
    async function refreshAccess(): Promise<void> {
      if (refreshing) return;
      if (!hasSessionHint()) { clearSession(); return; }
      refreshing = true;
      try {
        const profile = await request<User>("/auth/me");
        // Tabs share one cookie, so another tab may have renewed it or signed in again since.
        const session = await request<SessionState>("/auth/session").catch(() => null);
        if (cancelled) return;
        if (session) remember(session.csrf_token, parseExpiry(session.expires_at));
        const expiry = expiresAt.current;
        if (expiry !== null && expiry - Date.now() < RENEW_WHEN_SECONDS_LEFT * 1000) {
          const renewed = await request<TokenResponse>("/auth/refresh", { method: "POST" });
          if (cancelled) return;
          remember(renewed.csrf_token, expiryAfter(renewed.expires_in_seconds));
        }
        if (profile.id !== user?.id || profile.role !== user?.role || JSON.stringify(profile.permissions) !== JSON.stringify(user?.permissions)) {
          saveFeedback.clear();
          queryClient.clear();
        }
        setUser(profile);
      } catch (error) {
        if (!cancelled && error instanceof ApiError && [401, 403].includes(error.status)) clearSession();
      } finally {
        refreshing = false;
      }
    }
    const onFocus = (): void => { void refreshAccess(); };
    const onVisible = (): void => { if (document.visibilityState === "visible") void refreshAccess(); };
    const onStorage = (event: StorageEvent): void => { if (event.key === SESSION_HINT_KEY || event.key === null) void refreshAccess(); };
    const interval = window.setInterval(onVisible, WORK_REFRESH_INTERVAL_MS);
    window.addEventListener("focus", onFocus);
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [clearSession, queryClient, remember, status, user]);

  const signIn = useCallback(async (email: string, password: string) => {
    startSession(await request<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
    }));
    endedByReader = false;
  }, [startSession]);

  // The role is assigned by the backend. Nothing here can request an elevated one.
  const register = useCallback(async (input: RegistrationInput) => {
    startSession(await request<TokenResponse>("/auth/register", {
      method: "POST",
      body: input,
    }));
    endedByReader = false;
  }, [startSession]);

  const signOut = useCallback(async () => {
    endedByReader = true;
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } catch {
      // The session still ends in this tab when the service cannot confirm it.
    }
    clearSession();
  }, [clearSession]);

  const can = useCallback(
    (permission: string) => user?.permissions.includes(permission) ?? false,
    [user],
  );

  const value = useMemo<AuthState>(
    () => ({ user, status, signIn, register, signOut, can }),
    [user, status, signIn, register, signOut, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export { ApiError };
