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
      setMessage(err instanceof ApiError ? err.message : "Sign-In Failed.");
    }
  };

  return (
    <div>
      <h3>Or Continue With Email</h3>
      <input type="text" placeholder="work email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Work Email" />
      <input type="password" placeholder="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Password" />
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailSignIn(email, password))}>
        Sign In With Email
      </button>
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailCodeSend(email))}>
        Email Me A Sign-In Code
      </button>
      <input type="text" placeholder="6-digit code" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Sign-In Code" />
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailCodeSignIn(email, code))}>
        Verify Code &amp; Sign In
      </button>
      <button type="button" className="auth-btn" onClick={() => void submit(() => emailReset(email))}>
        Forgot Password — Send Reset
      </button>
      <p className="muted" role="status">{message}</p>
    </div>
  );
}
