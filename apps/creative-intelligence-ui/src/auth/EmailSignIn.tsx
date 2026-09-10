import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { ApiError } from "@/api/client";

/** Email + password / magic-code / password-reset sign-in (legacy parity). */
export function EmailSignIn() {
  const { emailSignIn, emailCodeSend, emailCodeSignIn, emailReset } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");

  const submit = async (fn: () => Promise<string | void>) => {
    try {
      const msg = await fn();
      setMessage(typeof msg === "string" ? msg : "");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Sign-in failed.");
    }
  };

  return (
    <div>
      <h3>Or continue with email</h3>
      <input type="text" placeholder="work email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Work email" />
      <input type="password" placeholder="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Password" />
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailSignIn(email, password))}>
        Sign in with email
      </button>
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailCodeSend(email))}>
        Email me a sign-in code
      </button>
      <input type="text" placeholder="6-digit code" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Sign-in code" />
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailCodeSignIn(email, code))}>
        Verify code &amp; sign in
      </button>
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailReset(email))}>
        Forgot password — send reset
      </button>
      <p className="muted" role="status">{message}</p>
    </div>
  );
}
