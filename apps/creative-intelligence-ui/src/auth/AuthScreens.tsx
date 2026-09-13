import { useAuth } from "@/auth/AuthProvider";
import { EmployeeOAuthButtons } from "@/auth/OAuthButton";
import { EmailSignIn } from "@/auth/EmailSignIn";
import { Icon } from "@/components/icons";

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
  const params = new URLSearchParams(window.location.search);
  const authError = params.get("auth_error") ?? "";
  if (authError) window.history.replaceState(null, "", window.location.pathname);
  return (
    <AuthShell dense>
      <div className="auth-card login-card" style={{ maxWidth: 520, padding: "36px 40px 28px" }}>
        <h1>Welcome Back</h1>
        <p className="muted login-sub">Sign In To Your Employee Workspace.</p>
        {authError ? <p className="muted">Sign-In Failed: {authError}</p> : null}
        <EmailSignIn />
        <div className="login-separator" aria-hidden="true">
          <span>Or Continue With</span>
        </div>
        <div className="login-providers">
          <EmployeeOAuthButtons />
        </div>
        <p className="muted login-footer">
          <Icon name="lock" size={14} /> For Foap Employees Only.
        </p>
      </div>
    </AuthShell>
  );
}
