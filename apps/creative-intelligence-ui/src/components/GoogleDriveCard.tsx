import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useGoogleStatus } from "@/auth/useGoogleStatus";
import { useLocale } from "@/i18n";
import { LoadingButton } from "@/components/LoadingButton";
import driveLogo from "@/assets/drive.svg";

/** Private Drive/Sheets connection. Server-side OAuth only: the browser
 *  is bounced to Google and back; tokens stay server-side. */
export function GoogleDriveCard() {
  const { t } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  /* Bounded status check (§11): a stalled lookup fails into the retry
   * state instead of sticking on "Checking…" forever. */
  const status = useGoogleStatus();
  const connected = status.connected;
  const statusError = status.error && connected === null;
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const flag = searchParams.get("google");
    if (flag === "connected") setNotice(t("drive.connectedNotice"));
    else if (flag === "failed") setNotice(t("drive.failedNotice"));
    else if (flag === "expired") setNotice(t("drive.expiredNotice"));
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
      setNotice(err instanceof ApiError ? err.message : t("drive.startFailed"));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setNotice("");
    try {
      await api("POST", "/api/auth/google/disconnect", {});
      status.reload();
      setNotice(t("drive.disconnected"));
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : t("drive.disconnectFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="insight" id="integration-google">
      <span className="insight-ico svc-tile" aria-hidden="true">
        <img className="svc-logo" src={driveLogo} alt="" />
      </span>
      <div style={{ flex: 1 }}>
        <h4>{t("drive.title")}</h4>
        <p>{t("drive.body")}</p>
        {notice ? <p role="status" style={{ margin: "4px 0 0" }}>{notice}</p> : null}
      </div>
      {/* Single right-side state/action area (§10): no duplicate status
        line beside it. Google sign-in alone never marks this connected —
        only the Drive authorisation status does. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {connected === true ? <span className="pill pill-ok">{t("drive.connected")}</span> : null}
        {statusError ? (
          <>
            <span className="panel-sub">{t("drive.couldNotCheck")}</span>
            <button type="button" className="btn-outline" onClick={() => status.reload()}>
              {t("common.retry")}
            </button>
          </>
        ) : connected === true ? (
          <LoadingButton type="button" className="btn-outline" loading={busy} loadingLabel={t("drive.working")} spinnerClass="spinner dark" disabled={busy} onClick={() => void disconnect()}>
            {t("drive.disconnect")}
          </LoadingButton>
        ) : connected === false ? (
          <LoadingButton type="button" className="btn-outline" loading={busy} loadingLabel={t("drive.connecting")} spinnerClass="spinner dark" disabled={busy} onClick={() => void connect()}>
            {t("drive.connect")}
          </LoadingButton>
        ) : (
          <button type="button" className="btn-outline" disabled aria-busy="true">
            {t("drive.checking")}
          </button>
        )}
      </div>
    </div>
  );
}
