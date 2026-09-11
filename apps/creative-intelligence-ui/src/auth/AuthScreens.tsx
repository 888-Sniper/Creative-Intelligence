import { useAuth } from "@/auth/AuthProvider";
import { EmployeeOAuthButtons } from "@/auth/OAuthButton";
import { EmailSignIn } from "@/auth/EmailSignIn";

// Brand single-source: served by the backend from Web/assets
// (GET /foap-logo.png); never duplicated into the frontend tree.
const FOAP_LOGO = "/foap-logo.png";

const TITLES: Record<string, string> = {
  pending: "Access Pending",
  suspended: "Access Suspended",
  revoked: "Access Revoked",
};

const NOTES: Record<string, string> = {
  pending:
    "Your Account Has Been Authenticated, But You Don't Currently Have Access To Creative Intelligence. An Administrator Needs To Approve Your Account.",
  suspended:
    "Your Access To Creative Intelligence Has Been Suspended. Contact An Administrator If You Believe This Is Incorrect.",
  revoked:
    "Your Access To Creative Intelligence Has Been Revoked. Contact An Administrator If You Believe This Is Incorrect.",
};

export function AccessPending() {
  return <GateScreen gate="pending" />;
}

export function AccessSuspended() {
  return <GateScreen gate="suspended" />;
}

export function AccessRevoked() {
  return <GateScreen gate="revoked" />;
}

/** Shared centred shell: Foap logo above the card on every auth screen. */
function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div id="auth-screen">
      <div className="login-shell">
        <img src={FOAP_LOGO} alt="Foap" className="login-logo" />
        {children}
      </div>
    </div>
  );
}

function GateScreen({ gate }: { gate: "pending" | "suspended" | "revoked" }) {
  const { me, refresh, logout } = useAuth();
  const employee = me?.employee;
  const who =
    `${employee?.first_name ?? ""} ${employee?.last_name ?? ""}`.trim() ||
    employee?.email ||
    "";
  return (
    <AuthShell>
      <div className="auth-card" role="alert">
        <h1>{TITLES[gate]}</h1>
        <p className="muted">{who}</p>
        <p>{NOTES[gate]}</p>
        <button type="button" className="auth-btn" onClick={() => void refresh()}>
          Refresh Access
        </button>
        <button type="button" className="auth-btn" onClick={() => void logout()}>
          Log Out
        </button>
      </div>
    </AuthShell>
  );
}

export function LoginPage() {
  const { me } = useAuth();
  const params = new URLSearchParams(window.location.search);
  const authError = params.get("auth_error") ?? "";
  if (authError) window.history.replaceState(null, "", window.location.pathname);
  return (
    <AuthShell>
      <div className="auth-card login-card">
        <h1>Welcome Back</h1>
        <p className="muted login-sub">Sign in to your employee workspace.</p>
        {authError ? <p className="muted">Sign-In Failed: {authError}</p> : null}
        <EmailSignIn />
        <div className="login-separator" aria-hidden="true">
          <span>Or continue with</span>
        </div>
        <div className="login-providers">
          <EmployeeOAuthButtons />
        </div>
        <p className="muted login-footer">
          <span aria-hidden="true">🔒</span> For Foap employees only.
        </p>
        {me?.workos_configured === false ? (
          <p className="muted">WorkOS Is Not Configured On This Server Yet — Ask Your Administrator To Set It Up.</p>
        ) : null}
      </div>
    </AuthShell>
  );
}
