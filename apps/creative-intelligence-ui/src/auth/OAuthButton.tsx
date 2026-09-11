import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";

const PROVIDERS = [
  { id: "google", label: "Continue With Google" },
  { id: "microsoft", label: "Continue With Microsoft" },
  { id: "apple", label: "Continue With Apple" },
  { id: "github", label: "Continue With GitHub" },
] as const;

function ProviderMark({ provider }: { provider: string }) {
  if (provider === "google") {
    return (
      <svg width={20} height={20} viewBox="0 0 24 24" aria-hidden="true">
        <path fill="#4285F4" d="M23.5 12.3c0-.9-.1-1.8-.2-2.6H12v5h6.5c-.3 1.4-1.1 2.6-2.3 3.4v2.8h3.7c2.2-2 3.6-5 3.6-8.6Z" />
        <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.7-2.8c-1 .7-2.4 1.2-4.3 1.2-3.3 0-6-2.2-7-5.2H1.1v2.9C3.1 21.5 7.3 24 12 24Z" />
        <path fill="#FBBC05" d="M5 14.3c-.2-.7-.4-1.5-.4-2.3s.1-1.6.4-2.3V6.8H1.1A12 12 0 0 0 0 12c0 1.9.5 3.7 1.1 5.2L5 14.3Z" />
        <path fill="#EA4335" d="M12 4.7c1.8 0 3.3.6 4.6 1.8l3.3-3.3C17.9 1.2 15.2 0 12 0 7.3 0 3.1 2.5 1.1 6.8L5 9.7c1-3 3.7-5 7-5Z" />
      </svg>
    );
  }
  if (provider === "microsoft") {
    return (
      <svg width={20} height={20} viewBox="0 0 24 24" aria-hidden="true">
        <rect x={1.5} y={1.5} width={10} height={10} fill="#F25022" />
        <rect x={12.5} y={1.5} width={10} height={10} fill="#7FBA00" />
        <rect x={1.5} y={12.5} width={10} height={10} fill="#00A4EF" />
        <rect x={12.5} y={12.5} width={10} height={10} fill="#FFB900" />
      </svg>
    );
  }
  return null;
}

// The employee login shows Google + Microsoft only. Apple/GitHub stay
// supported backend-side (WorkOS/providers untouched) but are hidden
// from this internal login UI — no documented Foap-employee use.
const EMPLOYEE_PROVIDERS = ["google", "microsoft"] as const;

/** One OAuth provider button. Redirects to WorkOS; secrets never touch
 *  the browser (item 8). */
export function OAuthButton({ provider, label }: { provider: string; label?: string }) {
  const { authenticating, oauthStart } = useAuth();
  const [starting, setStarting] = useState(false);
  const busy = starting || authenticating;
  return (
    <button
      type="button"
      className="auth-btn oauth-btn"
      disabled={busy}
      aria-busy={busy}
      onClick={() => {
        if (busy) return;
        setStarting(true);
        void oauthStart(provider).finally(() => setStarting(false));
      }}
    >
      {busy ? <span className="spinner dark" aria-hidden="true" /> : <ProviderMark provider={provider} />}
      <span>{starting ? "Connecting…" : (label ?? `Continue With ${provider}`)}</span>
    </button>
  );
}

export function OAuthButtons() {
  return (
    <>
      {PROVIDERS.map((p) => (
        <OAuthButton key={p.id} provider={p.id} label={p.label} />
      ))}
    </>
  );
}

export function EmployeeOAuthButtons() {
  return (
    <>
      {PROVIDERS.filter((p) =>
        (EMPLOYEE_PROVIDERS as readonly string[]).includes(p.id),
      ).map((p) => (
        <OAuthButton key={p.id} provider={p.id} label={p.label} />
      ))}
    </>
  );
}
