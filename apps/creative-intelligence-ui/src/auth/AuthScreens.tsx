import { useAuth } from "@/auth/AuthProvider";
import { OAuthButtons } from "@/auth/OAuthButton";
import { EmailSignIn } from "@/auth/EmailSignIn";

const TITLES: Record<string, string> = {
  pending: "Access pending",
  suspended: "Access suspended",
  revoked: "Access revoked",
};

const NOTES: Record<string, string> = {
  pending:
    "Your account has been authenticated, but you don't currently have access to Creative Intelligence. An administrator needs to approve your account.",
  suspended:
    "Your access to Creative Intelligence has been suspended. Contact an administrator if you believe this is incorrect.",
  revoked:
    "Your access to Creative Intelligence has been revoked. Contact an administrator if you believe this is incorrect.",
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

function GateScreen({ gate }: { gate: "pending" | "suspended" | "revoked" }) {
  const { me, refresh, logout } = useAuth();
  const employee = me?.employee;
  const who =
    `${employee?.first_name ?? ""} ${employee?.last_name ?? ""}`.trim() ||
    employee?.email ||
    "";
  return (
    <div id="auth-screen">
      <div className="auth-card" role="alert">
        <h1>{TITLES[gate]}</h1>
        <p className="muted">{who}</p>
        <p>{NOTES[gate]}</p>
        <button type="button" className="auth-btn" onClick={() => void refresh()}>
          Refresh access
        </button>
        <button type="button" className="auth-btn" onClick={() => void logout()}>
          Log out
        </button>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { me } = useAuth();
  const params = new URLSearchParams(window.location.search);
  const authError = params.get("auth_error") ?? "";
  if (authError) window.history.replaceState(null, "", window.location.pathname);
  return (
    <div id="auth-screen">
      <div className="auth-card">
        <h1>Welcome to Creative Intelligence</h1>
        <p className="muted">Sign in with your work account to continue.</p>
        {authError ? <p className="muted">Sign-in failed: {authError}</p> : null}
        <OAuthButtons />
        <EmailSignIn />
        {me?.workos_configured === false ? (
          <p className="muted">WorkOS is not configured on this server yet — ask your administrator to set it up.</p>
        ) : null}
      </div>
    </div>
  );
}
