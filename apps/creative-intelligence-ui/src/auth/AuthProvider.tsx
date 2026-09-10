import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, setGateHandler } from "@/api/client";
import { installationContainer } from "@/auth/container";
import type { AuthStatus, MeResponse } from "@/types/auth";
import { statusForMe } from "@/types/auth";

interface AuthContextValue {
  status: AuthStatus;
  me: MeResponse | null;
  refresh: () => Promise<void>;
  oauthStart: (provider: string) => Promise<void>;
  emailSignIn: (email: string, password: string) => Promise<void>;
  emailCodeSend: (email: string) => Promise<string>;
  emailCodeSignIn: (email: string, code: string) => Promise<void>;
  emailReset: (email: string) => Promise<string>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchMe(): Promise<MeResponse> {
  return api<MeResponse>("GET", "/api/auth/me");
}

/** Centralized authentication state (item 4). The ONLY source of truth is
 *  GET /api/auth/me; the backend stays authoritative and the app never
 *  renders protected content until gate === "app" with an active employee. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [authenticating, setAuthenticating] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setMe(await fetchMe());
    } catch {
      setMe({ authenticated: false, gate: "login", employee: null, is_admin: false, message: "", workos_configured: false });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setGateHandler(() => {
      void refresh();
    });
    return () => setGateHandler(null);
  }, [refresh]);

  // Adopt OAuth sessions (whose server-side redirect cannot carry the
  // container id) into this installation on boot. First write wins
  // server-side; a foreign container is refused with a login gate.
  useEffect(() => {
    if (me !== null && me.authenticated) {
      const id = installationContainer();
      if (id) {
        api<{ container_id: string }>("POST", "/api/auth/container", {
          container_id: id,
        }).catch(() => {
          void refresh();
        });
      }
    }
  }, [me, refresh]);

  const status: AuthStatus = useMemo(() => {
    if (me === null) return "INITIALISING";
    if (authenticating) return "AUTHENTICATING";
    return statusForMe(me);
  }, [me, authenticating]);

  const oauthStart = useCallback(async (provider: string) => {
    setAuthenticating(true);
    try {
      const res = await api<{ url: string }>("POST", "/api/auth/oauth/start", { provider });
      window.location.href = res.url;
    } finally {
      setAuthenticating(false);
    }
  }, []);

  const afterLogin = useCallback(
    async (res: MeResponse) => {
      setMe(res);
      await refresh();
    },
    [refresh],
  );

  const emailSignIn = useCallback(
    async (email: string, password: string) => {
      setAuthenticating(true);
      try {
        await afterLogin(
          await api<MeResponse>("POST", "/api/auth/email/signin", {
            email,
            password,
            container_id: installationContainer(),
          }),
        );
      } finally {
        setAuthenticating(false);
      }
    },
    [afterLogin],
  );

  const emailCodeSend = useCallback(async (email: string) => {
    await api("POST", "/api/auth/email/code", { email });
    return "Code sent — check your email.";
  }, []);

  const emailCodeSignIn = useCallback(
    async (email: string, code: string) => {
      setAuthenticating(true);
      try {
        await afterLogin(
          await api<MeResponse>("POST", "/api/auth/email/code/signin", {
            email,
            code,
            container_id: installationContainer(),
          }),
        );
      } finally {
        setAuthenticating(false);
      }
    },
    [afterLogin],
  );

  const emailReset = useCallback(async (email: string) => {
    await api("POST", "/api/auth/email/reset", { email });
    return "If that email exists, a reset is on its way.";
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("POST", "/api/auth/logout", {});
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
    }
    await refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ status, me, refresh, oauthStart, emailSignIn, emailCodeSend, emailCodeSignIn, emailReset, logout }),
    [status, me, refresh, oauthStart, emailSignIn, emailCodeSend, emailCodeSignIn, emailReset, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
