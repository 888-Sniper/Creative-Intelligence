import { useAuth } from "@/auth/AuthProvider";

const PROVIDERS = [
  { id: "google", label: "Continue With Google" },
  { id: "microsoft", label: "Continue With Microsoft" },
  { id: "apple", label: "Continue With Apple" },
  { id: "github", label: "Continue With GitHub" },
] as const;

// The employee login shows Google + Microsoft only. Apple/GitHub stay
// supported backend-side (WorkOS/providers untouched) but are hidden
// from this internal login UI — no documented Foap-employee use.
const EMPLOYEE_PROVIDERS = ["google", "microsoft"] as const;

function ProviderIcon({ provider }: { provider: string }) {
  if (provider === "google") {
    return (
      <svg
        aria-hidden="true"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        focusable="false"
      >
        <path fill="#4285F4" d="M21.6 12.23c0-.79-.07-1.55-.2-2.28H12v4.31h5.37a4.59 4.59 0 0 1-1.99 3.01v2.5h3.22c1.89-1.74 3-4.3 3-7.54Z" />
        <path fill="#34A853" d="M12 22c2.7 0 4.97-.89 6.62-2.42l-3.22-2.5c-.9.6-2.04.96-3.4.96-2.6 0-4.8-1.76-5.59-4.12H3.08v2.58A10 10 0 0 0 12 22Z" />
        <path fill="#FBBC05" d="M6.41 13.92A6 6 0 0 1 6.1 12c0-.67.11-1.32.31-1.92V7.5H3.08A10 10 0 0 0 2 12c0 1.61.39 3.13 1.08 4.5l3.33-2.58Z" />
        <path fill="#EA4335" d="M12 5.96c1.47 0 2.78.51 3.82 1.49l2.86-2.86C16.96 2.98 14.7 2 12 2a10 10 0 0 0-8.92 5.5l3.33 2.58C7.2 7.72 9.4 5.96 12 5.96Z" />
      </svg>
    );
  }

  if (provider === "microsoft") {
    return (
      <svg
        aria-hidden="true"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        focusable="false"
      >
        <path fill="#F25022" d="M2 2h9v9H2z" />
        <path fill="#7FBA00" d="M13 2h9v9h-9z" />
        <path fill="#00A4EF" d="M2 13h9v9H2z" />
        <path fill="#FFB900" d="M13 13h9v9h-9z" />
      </svg>
    );
  }

  return null;
}

/** One OAuth provider button. Redirects to WorkOS; secrets never touch
 *  the browser (item 8). */
export function OAuthButton({ provider, label }: { provider: string; label?: string }) {
  const { authenticating, oauthStart } = useAuth();
  return (
    <button
      type="button"
      className="auth-btn"
      disabled={authenticating}
      onClick={() => void oauthStart(provider)}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "10px",
        }}
      >
        <ProviderIcon provider={provider} />
        <span>{label ?? `Continue with ${provider}`}</span>
      </span>
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
