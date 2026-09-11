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
    case "INITIALISING":
    case "AUTHENTICATING":
      return (
        <div id="auth-screen">
          <div className="auth-card">
            <h1>Creative Intelligence</h1>
            <p className="muted" role="status">Checking your session…</p>
          </div>
        </div>
      );
    // A07: while the account switch is in flight, no protected
    // content from either account is rendered.
    case "SWITCHING":
      return (
        <div id="auth-screen">
          <div className="auth-card">
            <h1>Creative Intelligence</h1>
            <p className="muted" role="status">Switching accounts…</p>
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
