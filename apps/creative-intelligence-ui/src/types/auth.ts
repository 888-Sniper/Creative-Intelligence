export interface PublicEmployee {
  id: string;
  /** Short readable display number (EMP-001…); optional for payloads
   *  minted before the server assigned one. */
  employee_no?: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url: string;
  provider: string;
  role: string;
  status: string;
  created_at: string;
  approved_at: string;
  approved_by: string;
  last_login_at: string;
  updated_at: string;
}

export type Gate = "login" | "pending" | "suspended" | "revoked" | "app";

export interface MeResponse {
  authenticated: boolean;
  gate: Gate;
  employee: PublicEmployee | null;
  is_admin: boolean;
  message: string;
  workos_configured: boolean;
}

/** Centralized auth state model (item 4). Backend remains authoritative:
 *  every transition originates from GET /api/auth/me, never from local
 *  guesswork. */
export type AuthStatus =
  | "INITIALISING"
  | "SIGNED_OUT"
  | "AUTHENTICATING"
  | "SWITCHING"
  | "PENDING"
  | "SUSPENDED"
  | "REVOKED"
  | "AUTHENTICATED";

export function statusForMe(me: MeResponse | null): AuthStatus {
  if (me === null) return "INITIALISING";
  if (!me.authenticated || me.gate === "login") return "SIGNED_OUT";
  if (me.gate === "pending") return "PENDING";
  if (me.gate === "suspended") return "SUSPENDED";
  if (me.gate === "revoked") return "REVOKED";
  return "AUTHENTICATED";
}
