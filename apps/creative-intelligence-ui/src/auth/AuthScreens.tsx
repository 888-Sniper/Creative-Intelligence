import { useAuth } from "@/auth/AuthProvider";
import { EmployeeOAuthButtons } from "@/auth/OAuthButton";
import { EmailSignIn } from "@/auth/EmailSignIn";
import { Icon } from "@/components/icons";
import { useLocale } from "@/i18n";

// Brand single-source: served by the backend from Web/assets
// (GET /foap-logo.png); never duplicated into the frontend tree.
const FOAP_LOGO = "/foap-logo.png";

/** Gate titles/notes render through the UI locale (§9); the who-line
 *  stays account data, never translated. */

export function AccessPending() {
  return <GateScreen gate="pending" />;
}

export function AccessSuspended() {
  return <GateScreen gate="suspended" />;
}

export function AccessRevoked() {
  return <GateScreen gate="revoked" />;
}

/** Shared centred shell: Foap logo above the card on every auth screen,
 *  over pale aqua decorative blobs (approved login treatment). */
function AuthShell({ children, dense = false }: { children: React.ReactNode; dense?: boolean }) {
  return (
    <div id="auth-screen">
      <div className="auth-blobs" aria-hidden="true">
        <span className="auth-blob b1" />
        <span className="auth-blob b2" />
        <span className="auth-blob b3" />
      </div>
      <div className="login-shell" style={dense ? { maxWidth: 520 } : undefined}>
        <img
          src={FOAP_LOGO}
          alt="Foap"
          className="login-logo"
          style={dense ? { height: 38, marginBottom: 20 } : undefined}
        />
        {children}
      </div>
    </div>
  );
}

function GateScreen({ gate }: { gate: "pending" | "suspended" | "revoked" }) {
  const { me, refresh, logout } = useAuth();
  const { t } = useLocale();
  const titles = { pending: t("auth.gate.pending"), suspended: t("auth.gate.suspended"), revoked: t("auth.gate.revoked") };
  const notes = { pending: t("auth.gate.pendingNote"), suspended: t("auth.gate.suspendedNote"), revoked: t("auth.gate.revokedNote") };
  const employee = me?.employee;
  const who =
    `${employee?.first_name ?? ""} ${employee?.last_name ?? ""}`.trim() ||
    employee?.email ||
    "";
  return (
    <AuthShell>
      <div className="auth-card" role="alert">
        <h1>{titles[gate]}</h1>
        <p className="muted">{who}</p>
        <p>{notes[gate]}</p>
        <button type="button" className="auth-btn" onClick={() => void refresh()}>
          {t("auth.gate.refresh")}
        </button>
        <button type="button" className="auth-btn" onClick={() => void logout()}>
          {t("auth.gate.logout")}
        </button>
      </div>
    </AuthShell>
  );
}

export function LoginPage() {
  const { t } = useLocale();
  const params = new URLSearchParams(window.location.search);
  const authError = params.get("auth_error") ?? "";
  if (authError) window.history.replaceState(null, "", window.location.pathname);
  return (
    <AuthShell dense>
      <div className="auth-card login-card" style={{ maxWidth: 520, padding: "36px 40px 28px" }}>
        <h1>{t("auth.login.welcome")}</h1>
        <p className="muted login-sub">{t("auth.login.sub")}</p>
        {authError ? <p className="muted">{t("auth.login.failed", { error: authError })}</p> : null}
        <EmailSignIn />
        <div className="login-separator" aria-hidden="true">
          <span>{t("auth.login.orContinue")}</span>
        </div>
        <div className="login-providers">
          <EmployeeOAuthButtons />
        </div>
        <p className="muted login-footer">
          <Icon name="lock" size={14} /> {t("auth.login.employeesOnly")}
        </p>
      </div>
    </AuthShell>
  );
}
