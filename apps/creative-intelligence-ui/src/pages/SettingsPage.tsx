import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
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

/** Private Drive/Sheets connection (item 31). Server-side OAuth only:
 *  the browser is bounced to Google and back; tokens stay server-side. */
function GoogleDriveCard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [connected, setConnected] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let live = true;
    api<{ connected: boolean }>("GET", "/api/auth/google/status")
      .then((res) => { if (live) setConnected(res.connected); })
      .catch(() => { if (live) setConnected(false); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    const flag = searchParams.get("google");
    if (flag === "connected") setNotice("Google Drive Connected.");
    else if (flag === "failed") setNotice("Google Connection Failed. Try Again.");
    else if (flag === "expired") setNotice("That Google Sign-In Expired. Try Again.");
    if (flag) {
      const next = new URLSearchParams(searchParams);
      next.delete("google");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = async () => {
    setBusy(true);
    setNotice("");
    try {
      const res = await api<{ url: string }>("POST", "/api/auth/google/start", {});
      window.location.href = res.url;
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could Not Start Google Sign-In.");
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setNotice("");
    try {
      await api("POST", "/api/auth/google/disconnect", {});
      setConnected(false);
      setNotice("Google Drive Disconnected.");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could Not Disconnect Google Drive.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>Google Drive</h3>
      <p className="muted">
        Connect Google Drive For Private Sheets And Drive Sync. Read-Only Access;
        Tokens Stay On The Server.
      </p>
      <p>
        Status: <strong>{connected === null ? "…" : connected ? "Connected" : "Not Connected"}</strong>
      </p>
      {connected ? (
        <button type="button" className="secondary" disabled={busy} onClick={() => void disconnect()}>
          Disconnect Google Drive
        </button>
      ) : (
        <button type="button" className="secondary" disabled={busy || connected === null} onClick={() => void connect()}>
          Connect Google Drive
        </button>
      )}
      {notice ? <p className="muted" role="status">{notice}</p> : null}
    </div>
  );
}

/** Settings area (item 21): Account (name, email, avatar, provider, role,
 *  logout, logout-all-sessions) + Appearance (light/dark/system). */
export function SettingsPage() {
  const { me, refresh, logout } = useAuth();
  const { mode, set } = useTheme();
  const [message, setMessage] = useState("");
  const employee = me?.employee;

  if (!employee) return <p className="muted">Sign In To Manage Settings.</p>;
  const name = `${employee.first_name} ${employee.last_name}`.trim() || employee.email;

  const logoutAll = async () => {
    setMessage("");
    if (!window.confirm("Log Out All Sessions? Every Device And Browser Signed In As This Account Is Signed Out Immediately.")) {
      return;
    }
    try {
      await api("POST", "/api/auth/sessions/revoke-all", {});
      await refresh();
      setMessage("All Sessions Signed Out.");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Could Not Sign Out All Sessions.");
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
            <span className="muted">{employee.email} (Verified, Read-Only)</span>
          </span>
        </div>
        <p>
          Authentication Provider: <strong>{PROVIDER_LABELS[employee.provider] ?? "—"}</strong>
          <br />
          Current Role: <strong>{employee.role}</strong> · Status: <strong>{employee.status}</strong>
        </p>
        <button type="button" className="secondary" onClick={() => void logout()}>
          Log Out
        </button>{" "}
        <button type="button" className="secondary" onClick={() => void logoutAll()}>
          Log Out All Sessions
        </button>
        {message ? <p className="muted" role="status">{message}</p> : null}
      </div>
      <GoogleDriveCard />
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
              {m.id === "system" ? " (Follows Your Device)" : ""}
            </label>
          ))}
        </div>
      </div>
    </>
  );
}
