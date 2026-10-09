import { useEffect, useState } from "react";
import { api, ApiError } from "@/api/client";
import { LoadingButton } from "@/components/LoadingButton";
import { useLocale } from "@/i18n";

/** Authenticator setup on Profile Settings. The secret is shown once,
 *  before it is confirmed. Recovery codes are shown once, after. */
export function TwoFactorCard({ last = false }: { last?: boolean }) {
  const { t } = useLocale();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"idle" | "setup" | "recovery" | "disable">("idle");
  const [secret, setSecret] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [alert, setAlert] = useState("");

  const load = () => {
    setLoadError(false);
    api<{ enabled: boolean }>("GET", "/api/auth/2fa/status")
      .then((res) => setEnabled(res.enabled === true))
      .catch(() => {
        setEnabled(null);
        setLoadError(true);
      });
  };

  useEffect(() => {
    load();
  }, []);

  const fail = (err: unknown) => {
    setAlert(err instanceof ApiError ? err.message : t("settings.security.couldNotUpdate"));
    setBusy(false);
  };

  const startSetup = async () => {
    setBusy(true);
    setAlert("");
    setNotice("");
    try {
      const res = await api<{ secret: string }>("POST", "/api/auth/2fa/setup", {});
      setSecret(res.secret);
      setCode("");
      setMode("setup");
    } catch (err) {
      fail(err);
      return;
    }
    setBusy(false);
  };

  const confirm = async () => {
    setBusy(true);
    setAlert("");
    try {
      const res = await api<{ recovery_codes: string[] }>("POST", "/api/auth/2fa/confirm", { code });
      setCodes(res.recovery_codes ?? []);
      setEnabled(true);
      setSecret("");
      setCode("");
      setMode("recovery");
      setNotice(t("settings.security.enabledNotice"));
    } catch (err) {
      fail(err);
      return;
    }
    setBusy(false);
  };

  const cancel = async () => {
    setBusy(true);
    setAlert("");
    try {
      await api("POST", "/api/auth/2fa/cancel", {});
      setMode("idle");
      setSecret("");
      setCode("");
    } catch (err) {
      fail(err);
      return;
    }
    setBusy(false);
  };

  const turnOff = async () => {
    setBusy(true);
    setAlert("");
    try {
      await api("POST", "/api/auth/2fa/disable", { code });
      setEnabled(false);
      setMode("idle");
      setCode("");
      setNotice(t("settings.security.disabledNotice"));
    } catch (err) {
      fail(err);
      return;
    }
    setBusy(false);
  };

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(secret);
      setNotice(t("settings.security.copiedKey"));
    } catch {
      setAlert(t("settings.security.copyFailed"));
    }
  };

  let action = (
    <button type="button" className="btn-outline" disabled aria-busy="true">
      {t("settings.security.checking")}
    </button>
  );
  if (loadError) {
    action = (
      <button type="button" className="btn-outline" onClick={load}>
        {t("common.retry")}
      </button>
    );
  } else if (enabled === true && mode !== "disable") {
    action = (
      <>
        <span className="pill pill-ok">{t("settings.security.on")}</span>
        <button type="button" className="btn-outline" disabled={busy}
          onClick={() => { setMode("disable"); setAlert(""); setCode(""); }}>
          {t("settings.security.turnOff")}
        </button>
      </>
    );
  } else if (enabled === false && mode === "idle") {
    action = (
      <LoadingButton type="button" className="btn-outline" loading={busy}
        loadingLabel={t("settings.security.checking")} spinnerClass="spinner dark"
        onClick={() => void startSetup()}>
        {t("settings.security.setUp")}
      </LoadingButton>
    );
  } else if (enabled !== null && mode === "idle") {
    action = <span className="pill pill-ok">{t("settings.security.on")}</span>;
  } else {
    action = <></>;
  }

  return (
    <div style={{
      padding: "14px 0",
      borderBottom: last ? 0 : "1px solid var(--shell-line)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ minWidth: 0 }}>
          <strong style={{ display: "block", fontSize: 13 }}>{t("settings.security.twoFactor")}</strong>
          <span className="panel-sub" style={{ fontSize: 12 }}>{t("settings.security.twoFactorBody")}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {action}
        </div>
      </div>
      {notice ? <p role="status" className="panel-sub" style={{ margin: "8px 0 0" }}>{notice}</p> : null}
      {alert ? <p role="alert" className="panel-sub" style={{ margin: "8px 0 0" }}>{alert}</p> : null}
      {mode === "setup" ? (
        <div className="field" style={{ marginTop: 10 }}>
          <p className="panel-sub" style={{ fontSize: 12 }}>{t("settings.security.setupHint")}</p>
          <p><code data-testid="totp-secret">{secret}</code></p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn-outline" onClick={() => void copyKey()}>
              {t("settings.security.copyKey")}
            </button>
            <button type="button" className="btn-outline" disabled={busy} onClick={() => void cancel()}>
              {t("common.cancel")}
            </button>
          </div>
          <label htmlFor="totp-setup-code" style={{ marginTop: 8 }}>{t("settings.security.codeLabel")}</label>
          <input id="totp-setup-code" inputMode="numeric" autoComplete="one-time-code"
            maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} />
          <LoadingButton type="button" className="btn-primary" loading={busy}
            loadingLabel={t("settings.security.checking")} spinnerClass="spinner"
            style={{ marginTop: 8 }} onClick={() => void confirm()}>
            {t("settings.security.confirm")}
          </LoadingButton>
        </div>
      ) : null}
      {mode === "recovery" ? (
        <div style={{ marginTop: 10 }}>
          <strong style={{ display: "block", fontSize: 13 }}>{t("settings.security.recoveryTitle")}</strong>
          <p className="panel-sub" style={{ fontSize: 12 }}>{t("settings.security.recoveryHint")}</p>
          <ul>
            {codes.map((item) => <li key={item}><code>{item}</code></li>)}
          </ul>
          <button type="button" className="btn-primary" onClick={() => setMode("idle")}>
            {t("settings.security.savedCodes")}
          </button>
        </div>
      ) : null}
      {mode === "disable" ? (
        <div className="field" style={{ marginTop: 10 }}>
          <label htmlFor="totp-disable-code">{t("settings.security.codeLabel")}</label>
          <input id="totp-disable-code" inputMode="text" autoComplete="one-time-code"
            maxLength={32} value={code} onChange={(e) => setCode(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <LoadingButton type="button" className="btn-primary" loading={busy}
              loadingLabel={t("settings.security.checking")} spinnerClass="spinner"
              onClick={() => void turnOff()}>
              {t("settings.security.confirm")}
            </LoadingButton>
            <button type="button" className="btn-outline" disabled={busy}
              onClick={() => { setMode("idle"); setCode(""); setAlert(""); }}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
