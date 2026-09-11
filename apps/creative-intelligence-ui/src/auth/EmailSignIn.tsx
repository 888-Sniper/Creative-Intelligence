import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError } from "@/api/client";

// localStorage holds the work email ONLY (never the password) when the
// employee ticks "Remember me". Session lifetime stays server-controlled
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

  const submit = async (fn: () => Promise<string | void>) => {
    try {
      const msg = await fn();
      setMessage(typeof msg === "string" ? msg : "");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Sign-In Failed.");
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
    submit(async () => {
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
        <input
          id="login-email"
          type="email"
          placeholder="name@company.com"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        {!codeSent ? (
          <button type="button" className="login-primary" disabled={authenticating} onClick={() => void submit(async () => {
            const msg = await emailCodeSend(email);
            setCodeSent(true);
            return msg;
          })}>
            Send Sign-In Code
          </button>
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
            <button type="button" className="login-primary" disabled={authenticating} onClick={() => void submit(() => emailCodeSignIn(email, code))}>
              Verify &amp; Sign In
            </button>
          </>
        )}
        <button type="button" className="login-link" onClick={() => switchMode("password")}>
          Back to password sign in
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
      <input
        id="login-email"
        type="email"
        placeholder="name@company.com"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <label className="login-label" htmlFor="login-password">
        Password
      </label>
      <div className="login-password-wrap">
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
          className="login-link login-show"
          aria-label={showPassword ? "Hide Password" : "Show Password"}
          aria-pressed={showPassword}
          onClick={() => setShowPassword((v) => !v)}
        >
          {showPassword ? "Hide" : "Show"}
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
          Remember me
        </label>
        <button type="button" className="login-link" onClick={() => void submit(() => emailReset(email))}>
          Forgot password?
        </button>
      </div>
      <button type="button" className="login-primary" disabled={authenticating} onClick={() => void signInPassword()}>
        {authenticating ? "Signing In…" : "Sign In"}
      </button>
      <button type="button" className="login-link login-mode" onClick={() => switchMode("code")}>
        Use a sign-in code instead
      </button>
      <p className="muted login-status" role="status">{message}</p>
    </div>
  );
}
