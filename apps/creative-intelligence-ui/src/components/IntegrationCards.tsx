import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { LoadingButton } from "@/components/LoadingButton";
import { useLocale } from "@/i18n";
import metaLogo from "@/assets/meta.svg";
import tiktokLogo from "@/assets/tiktok.svg";
import ga4Logo from "@/assets/ga4.svg";

type Provider = "meta" | "tiktok" | "ga4";

const ROWS: Array<{ id: Provider; name: string; bodyKey: string; logo: string }> = [
  { id: "meta", name: "Meta Ads", bodyKey: "settings.integrations.metaBody", logo: metaLogo },
  { id: "tiktok", name: "TikTok Ads", bodyKey: "settings.integrations.tiktokBody", logo: tiktokLogo },
  { id: "ga4", name: "Google Analytics 4", bodyKey: "settings.integrations.ga4Body", logo: ga4Logo },
];

function useIntegrationStatus(provider: Provider) {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [account, setAccount] = useState("");
  const [error, setError] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError(false);
    api<{ connected: boolean; account?: string }>(
      "GET", `/api/auth/integrations/${provider}/status`,
    ).then((res) => {
      if (!live) return;
      setConnected(res.connected === true);
      setAccount(res.account ?? "");
    }).catch(() => {
      if (!live) return;
      setConnected(null);
      setError(true);
    });
    return () => { live = false; };
  }, [provider, tick]);
  return { connected, account, error, reload: () => setTick((n) => n + 1) };
}

function IntegrationRow({
  id, name, bodyKey, logo, flag,
}: { id: Provider; name: string; bodyKey: string; logo: string; flag: string }) {
  const { t } = useLocale();
  const status = useIntegrationStatus(id);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (flag === "connected") setNotice(t("settings.integrations.connectedNotice", { name }));
    else if (flag === "failed") setNotice(t("settings.integrations.failedNotice", { name }));
    else if (flag === "expired") setNotice(t("settings.integrations.expiredNotice"));
  }, [flag, name, t]);

  const connect = async () => {
    setBusy(true);
    setNotice("");
    try {
      const res = await api<{ url: string }>("POST", `/api/auth/integrations/${id}/start`, {});
      window.location.href = res.url;
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : t("settings.integrations.startFailed", { name }));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setNotice("");
    try {
      await api("POST", `/api/auth/integrations/${id}/disconnect`, {});
      status.reload();
      setNotice(t("settings.integrations.disconnected", { name }));
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : t("settings.integrations.disconnectFailed", { name }));
    } finally {
      setBusy(false);
    }
  };

  const connectLabel = `${t("settings.integrations.connect")} ${name}`;
  const disconnectLabel = `${t("settings.integrations.disconnect")} ${name}`;

  return (
    <div className="insight" id={`integration-${id}`}>
      <span className="insight-ico svc-tile" aria-hidden="true">
        <img className="svc-logo" src={logo} alt="" />
      </span>
      <div style={{ flex: 1 }}>
        <h4>{name}</h4>
        <p>{t(bodyKey)}</p>
        {status.connected && status.account ? (
          <p className="panel-sub" style={{ margin: "4px 0 0", fontSize: 12 }}>
            {t("settings.integrations.accountLine", { account: status.account })}
          </p>
        ) : null}
        {notice ? <p role="status" style={{ margin: "4px 0 0" }}>{notice}</p> : null}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {status.connected === true ? <span className="pill pill-ok">{t("settings.integrations.connected")}</span> : null}
        {status.error ? (
          <>
            <span className="panel-sub">{t("settings.integrations.couldNotCheck")}</span>
            <button type="button" className="btn-outline" onClick={() => status.reload()}>
              {t("common.retry")}
            </button>
          </>
        ) : status.connected === true ? (
          <LoadingButton type="button" className="btn-outline" loading={busy}
            loadingLabel={t("settings.integrations.working")} spinnerClass="spinner dark"
            aria-label={disconnectLabel} disabled={busy} onClick={() => void disconnect()}>
            {t("settings.integrations.disconnect")}
          </LoadingButton>
        ) : status.connected === false ? (
          <LoadingButton type="button" className="btn-outline" loading={busy}
            loadingLabel={t("settings.integrations.connecting")} spinnerClass="spinner dark"
            aria-label={connectLabel} disabled={busy} onClick={() => void connect()}>
            {t("settings.integrations.connect")}
          </LoadingButton>
        ) : (
          <button type="button" className="btn-outline" disabled aria-busy="true">
            {t("settings.integrations.checking")}
          </button>
        )}
      </div>
    </div>
  );
}

/** Meta Ads, TikTok Ads, and Google Analytics 4. Each row connects
 *  with server-side OAuth or says the app is not configured. */
export function IntegrationCards() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [flag, setFlag] = useState<{ name: string; result: string } | null>(null);

  useEffect(() => {
    const name = searchParams.get("integration");
    const result = searchParams.get("result");
    if (name && result) {
      setFlag({ name, result });
      const next = new URLSearchParams(searchParams);
      next.delete("integration");
      next.delete("result");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      {ROWS.map((row) => (
        <IntegrationRow key={row.id} {...row} flag={flag?.name === row.id ? flag.result : ""} />
      ))}
    </>
  );
}
