import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Avatar } from "@/auth/AccountMenu";
import { useTheme } from "@/app/useTheme";
import type { ThemeMode } from "@/app/useTheme";

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  microsoft: "Microsoft",
  apple: "Apple",
  github: "GitHub",
  email: "Email",
};

/** Settings area (item 21): Account (name, email, avatar, provider, role,
 *  logout, logout-all-sessions) + Appearance (light/dark/system). */
export function SettingsPage() {
  const { me, refresh, logout } = useAuth();
  const { mode, set } = useTheme();
  const [message, setMessage] = useState("");
  const employee = me?.employee;

  if (!employee) return <p className="muted">Sign in to manage settings.</p>;
  const name = `${employee.first_name} ${employee.last_name}`.trim() || employee.email;

  const logoutAll = async () => {
    setMessage("");
    if (!window.confirm("Log out all sessions? Every device and browser signed in as this account is signed out immediately.")) {
      return;
    }
    try {
      await api("POST", "/api/auth/sessions/revoke-all", {});
      await refresh();
      setMessage("All sessions signed out.");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Could not sign out all sessions.");
    }
  };

  const modes: Array<{ id: ThemeMode; label: string }> = [
    { id: "light", label: "Light" },
    { id: "dark", label: "Dark" },
    { id: "system", label: "System" },
  ];

  return (
    <>
      <h1 className="page-title">Settings</h1>
      <div className="card">
        <h3>Account</h3>
        <div style={{ display: "flex", alignItems: "center" }}>
          <Avatar url={employee.avatar_url} label={name} />
          <span>
            <strong>{name}</strong>
            <br />
            <span className="muted">{employee.email} (verified, read-only)</span>
          </span>
        </div>
        <p>
          Authentication provider: <strong>{PROVIDER_LABELS[employee.provider] ?? "—"}</strong>
          <br />
          Current role: <strong>{employee.role}</strong> · status: <strong>{employee.status}</strong>
        </p>
        <button type="button" className="secondary" onClick={() => void logout()}>
          Log out
        </button>{" "}
        <button type="button" className="secondary" onClick={() => void logoutAll()}>
          Log out all sessions
        </button>
        {message ? <p className="muted" role="status">{message}</p> : null}
      </div>
      <div className="card">
        <h3>Appearance</h3>
        <div role="radiogroup" aria-label="Appearance">
          {modes.map((m) => (
            <label key={m.id} style={{ marginRight: 16 }}>
              <input
                type="radio"
                name="appearance"
                value={m.id}
                checked={mode === m.id}
                onChange={() => set(m.id)}
              />{" "}
              {m.label}
              {m.id === "system" ? " (follows your device)" : ""}
            </label>
          ))}
        </div>
      </div>
    </>
  );
}
