import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Icon } from "@/components/icons";
import { EmployeeAvatar } from "@/components/product";

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

/* Compat alias: new code uses EmployeeAvatar directly so every face
 *  resolves THAT employee's photo with error fallback. */
export function Avatar({ url, label }: { url: string; label: string }) {
  return <EmployeeAvatar url={url} name={label} email="" />;
}

/** Employee account menu + switcher. Switching re-runs authorization via
 *  GET /api/auth/me afterwards; nothing is inherited from the previous
 *  account (item 19). */
export function AccountMenu() {
  const { me, switching, switchAccount, logout } = useAuth();
  const [accounts, setAccounts] = useState<StoredAccount[] | null>(null);
  const [error, setError] = useState("");
  // Collapsed by default: the menu is position:fixed, so an always-open
  // panel physically overlaps page content parked at the viewport's
  // bottom-left. Collapsed it is a single compact row that cannot
  // cover interactive controls.
  const [expanded, setExpanded] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
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

  /* Close on outside click or Escape. */
  useEffect(() => {
    if (!expanded) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setExpanded(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [expanded]);

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
    <div id="account-menu" ref={boxRef}>
      <button
        type="button"
        className="menu-toggle"
        aria-label="Toggle Account Menu"
        aria-expanded={expanded}
        aria-controls="account-menu-body"
        onClick={() => setExpanded((v) => !v)}
      >
        <EmployeeAvatar url={employee.avatar_url} name={name} email={employee.email} />
        <span>
          <strong>{name}</strong>
          <br />
          <span className="muted">
            {employee.role} · {employee.status}
          </span>
        </span>
        <span aria-hidden="true" className="menu-chevron"
          style={{ transform: expanded ? "rotate(-90deg)" : "rotate(90deg)" }}>
          <Icon name="chev" size={15} />
        </span>
      </button>
      {expanded ? (
        <div id="account-menu-body">
          <Link to="/profile" className="link-btn" onClick={() => setExpanded(false)}>
            Profile
          </Link>
          {accounts === null ? (
            <p className="muted">Loading Accounts…</p>
          ) : (
            <ul className="plain">
              {accounts
                .filter((a) => a.employee_id !== employee.id)
                .map((a) => (
                  <li key={a.employee_id}>
                    <button type="button" className="link-btn" disabled={switching} onClick={() => void switchTo(a.employee_id)}>
                      <EmployeeAvatar
                        url={a.avatar_url}
                        name={`${a.first_name} ${a.last_name}`.trim()}
                        email={a.email}
                        size={24}
                      />
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
      ) : null}
    </div>
  );
}

export type { StoredAccount };
