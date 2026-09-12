import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";

// localStorage holds the work email ONLY (never the password) when the
// employee ticks "Remember Me". Session lifetime stays server-controlled
// (30-day cookie); there is no safe client-side session toggle, so the
// checkbox honestly means "remember my email on this device".
const REMEMBERED_EMAIL_KEY = "ci-remember-email";

function loadRememberedEmail(): { email: string; remember: boolean } {
  try {
    const email = window.localStorage.getItem(REMEMBERED_EMAIL_KEY) ?? "";
    return { email, remember: email.length > 0 };
  } catch {
    return { email: "", remember: false };
  }
}

/** Employee email sign-in. Two exclusive modes sharing one card section:
 *  password (default) and sign-in code (behind a secondary control).
 *  All operations reuse the existing AuthProvider calls; only the
 *  presentation changed. */
export function EmailSignIn() {
  const { authenticating, emailSignIn, emailCodeSend, emailCodeSignIn, emailReset } = useAuth();
  const [initial] = useState(loadRememberedEmail);
  const [mode, setMode] = useState<"password" | "code">("password");
  const [email, setEmail] = useState(initial.email);
  const [remember, setRemember] = useState(initial.remember);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [message, setMessage] = useState("");
  // Which async auth action this form started (null when idle). The
  // spinner renders ONLY on the button the employee actually pressed —
  // a global `authenticating` from another button must never light up
  // every control. It still disables everything to avoid double submit.
  const [op, setOp] = useState<null | "password" | "send" | "verify" | "reset">(null);
  const busy = authenticating || op !== null;

  const run = async (name: NonNullable<typeof op>, fn: () => Promise<string | void>) => {
    if (busy) return;
    setOp(name);
    try {
      const msg = await fn();
      setMessage(typeof msg === "string" ? msg : "");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Sign-In Failed.");
    } finally {
      setOp(null);
    }
  };

  const persistRememberedEmail = (value: string, want: boolean) => {
    try {
      if (want && value.trim()) {
        window.localStorage.setItem(REMEMBERED_EMAIL_KEY, value.trim());
      } else {
        window.localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      }
    } catch {
      // Private browsing etc: remembering email is best-effort only.
    }
  };

  const signInPassword = () =>
    run("password", async () => {
      await emailSignIn(email, password);
      persistRememberedEmail(email, remember);
    });

  const switchMode = (next: "password" | "code") => {
    setMode(next);
    setMessage("");
    setCodeSent(false);
    setCode("");
  };

  if (mode === "code") {
    return (
      <div className="login-form">
        <label className="login-label" htmlFor="login-email">
          Work Email
        </label>
        <div className="login-input">
          <span className="login-icon" aria-hidden="true"><Icon name="mail" size={18} /></span>
          <input
            id="login-email"
            type="email"
            placeholder="name@company.com"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        {!codeSent ? (
          <LoadingButton type="button" className="login-primary" loading={op === "send"} loadingLabel="Sending Code…" disabled={busy} onClick={() => void run("send", async () => {
            const msg = await emailCodeSend(email);
            setCodeSent(true);
            return msg;
          })}>
            Send Sign-In Code
          </LoadingButton>
        ) : (
          <>
            <label className="login-label" htmlFor="login-code">
              Verification Code
            </label>
            <input
              id="login-code"
              type="text"
              inputMode="numeric"
              placeholder="6-digit code"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <LoadingButton type="button" className="login-primary" loading={op === "verify"} loadingLabel="Verifying…" disabled={busy} onClick={() => void run("verify", () => emailCodeSignIn(email, code))}>
              <>Verify &amp; Sign In</>
            </LoadingButton>
          </>
        )}
        <button type="button" className="login-link" onClick={() => switchMode("password")}>
          Back To Password Sign In
        </button>
        <p className="muted login-status" role="status">{message}</p>
      </div>
    );
  }

  return (
    <div className="login-form">
      <label className="login-label" htmlFor="login-email">
        Work Email
      </label>
      <div className="login-input">
        <span className="login-icon" aria-hidden="true"><Icon name="mail" size={18} /></span>
        <input
          id="login-email"
          type="email"
          placeholder="name@company.com"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <label className="login-label" htmlFor="login-password">
        Password
      </label>
      <div className="login-password-wrap">
        <span className="login-icon" aria-hidden="true"><Icon name="lock" size={18} /></span>
        <input
          id="login-password"
          type={showPassword ? "text" : "password"}
          placeholder="Enter your password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          type="button"
          className="login-link login-show login-icon-btn"
          aria-label={showPassword ? "Hide Password" : "Show Password"}
          aria-pressed={showPassword}
          onClick={() => setShowPassword((v) => !v)}
        >
          <Icon name="eye" size={18} />
        </button>
      </div>
      <div className="login-remember-row">
        <label className="login-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => {
              const want = e.target.checked;
              setRemember(want);
              persistRememberedEmail(email, want);
            }}
          />
          Remember Me
        </label>
        <LoadingButton type="button" className="login-link" loading={op === "reset"} loadingLabel="Sending…" disabled={busy} onClick={() => void run("reset", () => emailReset(email))}>
          Forgot Password?
        </LoadingButton>
      </div>
      <LoadingButton type="button" className="login-primary" loading={op === "password"} loadingLabel="Signing In…" disabled={busy} onClick={() => void signInPassword()}>
        Sign In
      </LoadingButton>
      <button type="button" className="login-link login-mode" onClick={() => switchMode("code")}>
        Use A Sign-In Code Instead
      </button>
      <p className="muted login-status" role="status">{message}</p>
    </div>
  );
}
