import { useAuth } from "@/auth/AuthProvider";
import { AccessPending, AccessRevoked, AccessSuspended, LoginPage } from "@/auth/AuthScreens";
import type { ReactNode } from "react";

/** App-level auth gate (item 5). Protected content renders ONLY when the
 *  backend reports an authenticated session with gate === "app" (active
 *  employee). Route hiding is presentation; the backend stays authoritative
 *  and re-checks status on every request. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  switch (status) {
    // An explicit sign-in keeps the login card mounted (busy) so
    // success/error outcomes render instead of flashing a loader.
    case "AUTHENTICATING":
      return <LoginPage />;
    case "INITIALISING":
      return (
        <div id="auth-screen">
          <div className="login-shell">
            <img src="/foap-logo.png" alt="Foap" className="login-logo" />
            <div className="auth-card">
              <p className="muted" role="status">Checking Your Session…</p>
            </div>
          </div>
        </div>
      );
    // A07: while the account switch is in flight, no protected
    // content from either account is rendered.
    case "SWITCHING":
      return (
        <div id="auth-screen">
          <div className="login-shell">
            <img src="/foap-logo.png" alt="Foap" className="login-logo" />
            <div className="auth-card">
              <p className="muted" role="status">Switching Accounts…</p>
            </div>
          </div>
        </div>
      );
    case "SIGNED_OUT":
      return <LoginPage />;
    case "PENDING":
      return <AccessPending />;
    case "SUSPENDED":
      return <AccessSuspended />;
    case "REVOKED":
      return <AccessRevoked />;
    case "AUTHENTICATED":
      return <>{children}</>;
  }
}
