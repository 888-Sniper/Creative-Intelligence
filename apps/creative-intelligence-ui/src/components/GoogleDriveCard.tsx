import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";

/** Private Drive/Sheets connection. Server-side OAuth only: the browser
 *  is bounced to Google and back; tokens stay server-side. */
export function GoogleDriveCard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [connected, setConnected] = useState<boolean | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  /* One truthful state source (§10): a failed status lookup is retryable
   * feedback, never a silent "disconnected". */
  const loadStatus = async () => {
    setStatusError(false);
    try {
      const res = await api<{ connected: boolean }>("GET", "/api/auth/google/status");
      setConnected(res.connected === true);
    } catch {
      setConnected(null);
      setStatusError(true);
    }
  };

  useEffect(() => {
    void loadStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    <div className="insight" id="integration-google">
      <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
        <Icon name="info" size={18} />
      </span>
      <div style={{ flex: 1 }}>
        <h4>Google Drive</h4>
        <p>Read-only access to analyze your creative assets.</p>
        {notice ? <p role="status" style={{ margin: "4px 0 0" }}>{notice}</p> : null}
      </div>
      {/* Single right-side state/action area (§10): no duplicate status
        line beside it. Google sign-in alone never marks this connected —
        only the Drive authorisation status does. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {connected === true ? <span className="pill pill-ok">Connected</span> : null}
        {statusError && connected === null ? (
          <>
            <span className="panel-sub">Could not check status.</span>
            <button type="button" className="btn-outline" onClick={() => void loadStatus()}>
              Retry
            </button>
          </>
        ) : connected === true ? (
          <LoadingButton type="button" className="btn-outline" loading={busy} loadingLabel="Working…" spinnerClass="spinner dark" disabled={busy} onClick={() => void disconnect()}>
            Disconnect
          </LoadingButton>
        ) : connected === false ? (
          <LoadingButton type="button" className="btn-outline" loading={busy} loadingLabel="Connecting…" spinnerClass="spinner dark" disabled={busy} onClick={() => void connect()}>
            Connect
          </LoadingButton>
        ) : (
          <button type="button" className="btn-outline" disabled aria-busy="true">
            Checking…
          </button>
        )}
      </div>
    </div>
  );
}
