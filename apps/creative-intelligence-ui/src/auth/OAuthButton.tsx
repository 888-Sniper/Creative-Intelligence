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

/** One OAuth provider button. Redirects to WorkOS; secrets never touch
 *  the browser (item 8). */
export function OAuthButton({ provider, label }: { provider: string; label?: string }) {
  const { authenticating, oauthStart } = useAuth();
  return (
    <button type="button" className="auth-btn" disabled={authenticating} onClick={() => void oauthStart(provider)}>
      {label ?? `Continue with ${provider}`}
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
