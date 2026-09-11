import { useEffect, useState } from "react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";

interface StoredAccount {
  employee_id: string;
  last_seen_at: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url: string;
  role: string;
  status: string;
}

export function Avatar({ url, label }: { url: string; label: string }) {
  if (url) return <img className="avatar" src={url} alt="" />;
  const init = label
    .split(/\s+/)
    .map((w) => w.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span className="avatar" aria-hidden="true" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}>
      {init || "?"}
    </span>
  );
}

/** Employee account menu + switcher. Switching re-runs authorization via
 *  GET /api/auth/me afterwards; nothing is inherited from the previous
 *  account (item 19). */
export function AccountMenu() {
  const { me, switching, switchAccount, logout } = useAuth();
  const [accounts, setAccounts] = useState<StoredAccount[] | null>(null);
  const [error, setError] = useState("");
  const employee = me?.employee;

  useEffect(() => {
    let live = true;
    api<{ accounts: StoredAccount[] }>("GET", "/api/auth/accounts")
      .then((r) => {
        if (live) setAccounts(r.accounts);
      })
      .catch((err) => {
        if (live) setError(err instanceof ApiError ? err.message : "Could Not Load Accounts.");
      });
    return () => {
      live = false;
    };
  }, []);

  if (!employee) return null;
  const name = `${employee.first_name} ${employee.last_name}`.trim() || employee.email;

  // A07: switching goes through the provider's dedicated switching
  // state (gate hides protected content, stale refreshes rejected,
  // pages remount by employee id). Nothing is inherited locally.
  const switchTo = async (employeeId: string) => {
    setError("");
    try {
      await switchAccount(employeeId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Switch Failed.");
    }
  };

  return (
    <div id="account-menu">
      <div style={{ display: "flex", alignItems: "center" }}>
        <Avatar url={employee.avatar_url} label={name} />
        <span>
          <strong>{name}</strong>
          <br />
          <span className="muted">
            {employee.role} · {employee.status}
          </span>
        </span>
      </div>
      {accounts === null ? (
        <p className="muted">Loading Accounts…</p>
      ) : (
        <ul className="plain">
          {accounts
            .filter((a) => a.employee_id !== employee.id)
            .map((a) => (
              <li key={a.employee_id}>
                <button type="button" className="link-btn" disabled={switching} onClick={() => void switchTo(a.employee_id)}>
                  Switch To {`${a.first_name} ${a.last_name}`.trim() || a.email}
                </button>{" "}
                <span className="muted">
                  ({a.role} · {a.status})
                </span>
              </li>
            ))}
        </ul>
      )}
      {error ? <p className="muted">{error}</p> : null}
      <button type="button" className="link-btn" onClick={() => void logout()}>
        Log Out
      </button>
    </div>
  );
}

export type { StoredAccount };
