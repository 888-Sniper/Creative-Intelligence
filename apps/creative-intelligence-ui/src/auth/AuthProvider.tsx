import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, setGateHandler } from "@/api/client";
import { installationContainer } from "@/auth/container";
import type { AuthStatus, MeResponse } from "@/types/auth";
import { statusForMe } from "@/types/auth";

interface AuthContextValue {
  status: AuthStatus;
  me: MeResponse | null;
  switching: boolean;
  // True while an explicit sign-in operation is in flight. The login
  // card stays mounted (form disabled) so result messages land on a
  // live component instead of being lost across an unmount.
  authenticating: boolean;
  refresh: () => Promise<void>;
  switchAccount: (employeeId: string) => Promise<void>;
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
  const [switching, setSwitching] = useState(false);
  // Monotonic refresh generation: only the latest /me resolution may
  // apply, so a slow pre-switch response can never clobber the
  // post-switch identity (A07).
  const refreshSeq = useRef(0);
  // Employee id the container bind was last attempted for (item 18).
  const bindTriedFor = useRef<string | null>(null);
  // Set when the container bind is refused: this browser is foreign to the
  // session, so late refresh resolutions must not resurrect the dashboard.
  // Cleared only by a fresh explicit login (afterLogin).
  const bindRefused = useRef(false);

  const refresh = useCallback(async () => {
    const seq = ++refreshSeq.current;
    const apply = (next: MeResponse) => {
      if (seq === refreshSeq.current) setMe(next);
    };
    try {
      const res = await fetchMe();
      if (bindRefused.current && res.authenticated) {
        apply({ authenticated: false, gate: "login", employee: null, is_admin: false, message: "", workos_configured: res.workos_configured });
      } else {
        apply(res);
      }
    } catch {
      apply({ authenticated: false, gate: "login", employee: null, is_admin: false, message: "", workos_configured: false });
    }
  }, []);

  // Account switch with a dedicated switching state (A07). While
  // switching is true the gate hides protected content, and the
  // generation bump below invalidates every in-flight pre-switch
  // refresh so late responses cannot resurrect the old identity.
  // Pages additionally remount by employee id (router) and reject
  // late account-stale payloads (AnalystPage accountKey).
  const switchAccount = useCallback(
    async (employeeId: string) => {
      setSwitching(true);
      refreshSeq.current++;
      try {
        await api("POST", "/api/auth/switch", { employee_id: employeeId });
        await refresh();
      } finally {
        setSwitching(false);
      }
    },
    [refresh],
  );

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
  // The attempt happens ONCE per signed-in employee: /api/auth/me is
  // container-blind, so a refused session still reads authenticated and
  // refreshing on refusal loops bind/refuse forever (request storm, gate
  // never settles). A fresh explicit login resets the guard below.
  useEffect(() => {
    const empId = me?.employee?.id ?? null;
    if (me === null || !me.authenticated || empId === null) return;
    if (bindTriedFor.current === empId) return;
    bindTriedFor.current = empId;
    const id = installationContainer();
    if (!id) return;
    api<{ container_id: string }>("POST", "/api/auth/container", {
      container_id: id,
    }).catch(() => {
      // Refused: this session belongs to another installation. Sign out
      // locally instead of refreshing back into the loop.
      bindRefused.current = true;
      setMe({
        authenticated: false, gate: "login", employee: null,
        is_admin: false, message: "", workos_configured: me.workos_configured,
      });
    });
  }, [me]);

  const status: AuthStatus = useMemo(() => {
    if (me === null) return "INITIALISING";
    if (authenticating) return "AUTHENTICATING";
    if (switching) return "SWITCHING";
    return statusForMe(me);
  }, [me, authenticating, switching]);

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
      // New session: clear the refusal pin and allow one container-bind
      // attempt for it, even when the same employee signs in again.
      bindRefused.current = false;
      bindTriedFor.current = null;
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
    return "Code Sent — Check Your Email.";
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
    return "If That Email Exists, A Reset Is On Its Way.";
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
    () => ({ status, me, switching, authenticating, refresh, switchAccount, oauthStart, emailSignIn, emailCodeSend, emailCodeSignIn, emailReset, logout }),
    [status, me, switching, authenticating, refresh, switchAccount, oauthStart, emailSignIn, emailCodeSend, emailCodeSignIn, emailReset, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
