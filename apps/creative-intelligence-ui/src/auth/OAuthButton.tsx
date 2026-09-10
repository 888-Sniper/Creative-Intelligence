import { useAuth } from "@/auth/AuthProvider";

const PROVIDERS = [
  { id: "google", label: "Continue with Google" },
  { id: "microsoft", label: "Continue with Microsoft" },
  { id: "apple", label: "Continue with Apple" },
  { id: "github", label: "Continue with GitHub" },
] as const;

/** One OAuth provider button. Redirects to WorkOS; secrets never touch
 *  the browser (item 8). */
export function OAuthButton({ provider, label }: { provider: string; label?: string }) {
  const { oauthStart } = useAuth();
  return (
    <button type="button" className="auth-btn" onClick={() => void oauthStart(provider)}>
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
