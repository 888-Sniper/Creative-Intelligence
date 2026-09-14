import { useAuth } from "@/auth/AuthProvider";
import { AccessPending, AccessRevoked, AccessSuspended, LoginPage } from "@/auth/AuthScreens";
import { Skeleton } from "@/components/product";
import { useLocale } from "@/i18n";
import type { ReactNode } from "react";

/** App-level auth gate (item 5). Protected content renders ONLY when the
 *  backend reports an authenticated session with gate === "app" (active
 *  employee). Route hiding is presentation; the backend stays authoritative
 *  and re-checks status on every request. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const { t } = useLocale();
  switch (status) {
    // An explicit sign-in keeps the login card mounted (busy) so
    // success/error outcomes render instead of flashing a loader.
    case "AUTHENTICATING":
      return <LoginPage />;
    case "INITIALISING":
      return <BootShell announcement={t("auth.checkingSession")} />;
    // A07: while the account switch is in flight, no protected
    // content from either account is rendered.
    case "SWITCHING":
      return <BootShell announcement={t("auth.switchingAccounts")} />;
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

/** Startup/switch loading shell (§10): skeleton blocks that mirror the
 *  app chrome (brand row, header bar, content panels) instead of
 *  text-only "Checking…" copy. The announcement lives in an sr-only
 *  live region — no visible text. */
function BootShell({ announcement }: { announcement: string }) {
  return (
    <div id="auth-screen">
      <span className="sr-only" role="status">{announcement}</span>
      <div className="login-shell" aria-hidden="true" style={{ maxWidth: 880 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
          <div className="skel" style={{ width: 120, height: 28, borderRadius: 6 }} />
          <div className="skel" style={{ flex: 1, height: 34, borderRadius: 8 }} />
          <div className="skel" style={{ width: 34, height: 34, borderRadius: "50%" }} />
        </div>
        <Skeleton height={64} />
        <div className="cols-2-even" style={{ marginTop: 12 }}>
          <Skeleton height={150} />
          <Skeleton height={150} />
        </div>
      </div>
    </div>
  );
}
