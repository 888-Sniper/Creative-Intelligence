import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { LoadingButton } from "@/components/LoadingButton";
import { useLocale } from "@/i18n";
import metaLogo from "@/assets/meta.svg";
import tiktokLogo from "@/assets/tiktok.svg";
import ga4Logo from "@/assets/ga4.svg";

type Provider = "meta" | "tiktok" | "ga4";

const ROWS: Array<{ id: Provider; name: string; bodyKey: string; logo: string; ink?: boolean }> = [
  { id: "meta", name: "Meta Ads", bodyKey: "settings.integrations.metaBody", logo: metaLogo },
  { id: "tiktok", name: "TikTok Ads", bodyKey: "settings.integrations.tiktokBody", logo: tiktokLogo, ink: true },
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
  id, name, bodyKey, logo, ink, flag,
}: { id: Provider; name: string; bodyKey: string; logo: string; ink?: boolean; flag: string }) {
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
        <img className={ink ? "svc-logo svc-logo-ink" : "svc-logo"} src={logo} alt="" />
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
      <Ga4Tools />
    </>
  );
}

interface Ga4Property { property_id: string; display_name: string }
interface Ga4Row {
  property_id?: string;
  date: string; session_source: string; session_medium: string;
  sessions: number; total_users: number; conversions: number;
}

/** GA4 property selection + manual import + own imported rows.
 *  Website analytics only — kept visibly separate from ad metrics. */
function Ga4Tools() {
  const { t } = useLocale();
  const [properties, setProperties] = useState<Ga4Property[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rows, setRows] = useState<Ga4Row[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  // Generation guard: a slower earlier response must never
  // overwrite rows for the property selected most recently.
  const rowsGen = useRef(0);
  const selectedRef = useRef("");

  const loadRows = async (pid: string) => {
    const gen = ++rowsGen.current;
    selectedRef.current = pid;
    try {
      const q = pid ? `?property_id=${encodeURIComponent(pid)}` : "";
      const res = await api<{ rows: Ga4Row[] }>(
        "GET", `/api/integrations/ga4/rows${q}`);
      if (gen !== rowsGen.current || selectedRef.current !== pid) return;
      setRows(res.rows ?? []);
    } catch {
      /* rows are optional context; import status carries errors */
    }
  };

  useEffect(() => {
    let live = true;
    api<{ properties: Ga4Property[] }>(
      "GET", "/api/integrations/ga4/properties",
    ).then((res) => {
      if (!live) return;
      setProperties(res.properties ?? []);
      if (res.properties?.[0]) setPropertyId(res.properties[0].property_id);
    }).catch(() => live && setProperties([]));
    void loadRows("");
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doImport = async () => {
    setBusy(true);
    setStatus("");
    try {
      const res = await api<{ rows: number; note: string }>(
        "POST", "/api/integrations/ga4/import",
        { property_id: propertyId, start_date: start, end_date: end });
      setStatus(t("settings.integrations.ga4Imported", { count: res.rows }));
      await loadRows(propertyId);
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message
        : t("settings.integrations.ga4ImportFailed"));
    } finally {
      setBusy(false);
    }
  };

  if (!properties.length && !rows.length) return null;
  return (
    <div className="insight" id="integration-ga4-tools">
      <div style={{ flex: 1 }}>
        <h4>{t("settings.integrations.ga4ToolsTitle")}</h4>
        <p>{t("settings.integrations.ga4ToolsBody")}</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
          <select aria-label={t("settings.integrations.ga4PropertyLabel")}
            value={propertyId} onChange={(e) => {
              setPropertyId(e.target.value);
              setRows([]);
              void loadRows(e.target.value);
            }}>
            {properties.map((p) => (
              <option key={p.property_id} value={p.property_id}>
                {p.display_name} ({p.property_id})
              </option>
            ))}
          </select>
          <input type="date" aria-label={t("settings.integrations.ga4StartLabel")}
            value={start} onChange={(e) => setStart(e.target.value)} />
          <input type="date" aria-label={t("settings.integrations.ga4EndLabel")}
            value={end} onChange={(e) => setEnd(e.target.value)} />
          <LoadingButton type="button" className="btn-outline" loading={busy}
            loadingLabel={t("settings.integrations.working")} disabled={busy || !propertyId || !start || !end}
            onClick={() => void doImport()}>
            {t("settings.integrations.ga4ImportBtn")}
          </LoadingButton>
        </div>
        {status ? <p role="status" style={{ margin: "6px 0 0" }}>{status}</p> : null}
        {rows.length ? (
          <table className="tbl" style={{ marginTop: 8 }}>
            <thead><tr>
              <th>{t("settings.integrations.ga4PropertyLabel")}</th>
              <th>{t("settings.integrations.ga4Date")}</th>
              <th>{t("settings.integrations.ga4Source")}</th>
              <th>{t("settings.integrations.ga4Sessions")}</th>
              <th>{t("settings.integrations.ga4Users")}</th>
            </tr></thead>
            <tbody>
              {rows.slice(0, 10).map((r, i) => (
                <tr key={`${r.property_id ?? ""}-${r.date}-${r.session_source}-${i}`}>
                  <td>{r.property_id ?? propertyId}</td>
                  <td>{r.date}</td>
                  <td>{r.session_source} / {r.session_medium}</td>
                  <td>{r.sessions}</td>
                  <td>{r.total_users}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}
