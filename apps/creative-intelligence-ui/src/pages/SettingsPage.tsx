import { useEffect, useState } from "react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Avatar } from "@/auth/AccountMenu";
import { GoogleDriveCard } from "@/components/GoogleDriveCard";
import { CohortBuilder, RetentionPatterns } from "@/components/DataTools";
import { useTheme } from "@/app/useTheme";
import type { ThemeMode } from "@/app/useTheme";
import { Icon } from "@/components/icons";
import { PageHeader, Panel } from "@/components/product";
import { LoadingButton } from "@/components/LoadingButton";

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  microsoft: "Microsoft",
  apple: "Apple",
  github: "GitHub",
  email: "Email",
};

/* Settings matches the approved reference. Workspace preferences persist
 * locally per browser; identity/security/drive actions stay backend-backed
 * (logout, session revoke, password-reset email, Drive OAuth status). */

interface Prefs {
  workspace: string;
  timezone: string;
  defaultView: string;
  currency: string;
  dateRange: string;
  campaignView: string;
  emailReports: boolean;
  campaignUpdates: boolean;
  aiInsights: boolean;
  productUpdates: boolean;
  dataUsage: boolean;
  shareAnalytics: boolean;
  retention: string;
  accent: string;
  density: string;
}

const DEFAULTS: Prefs = {
  workspace: "Alex's Workspace",
  timezone: "(GMT-05:00) Eastern Time (US & Canada)",
  defaultView: "Dashboard",
  currency: "USD – US Dollar",
  dateRange: "Last 30 Days",
  campaignView: "All Campaigns",
  emailReports: true,
  campaignUpdates: true,
  aiInsights: true,
  productUpdates: false,
  dataUsage: true,
  shareAnalytics: true,
  retention: "24 Months",
  accent: "Teal (Default)",
  density: "Comfortable",
};

const ACCENTS: Record<string, { teal: string; dark: string }> = {
  "Teal (Default)": { teal: "#0E7C8C", dark: "#0A5A66" },
  "Blue": { teal: "#2F6FBE", dark: "#1F4E86" },
  "Violet": { teal: "#6D5BD0", dark: "#4A3F96" },
};

const PREFS_KEY = "ci-settings-prefs";

function storageGet(): string | null {
  try {
    return window.localStorage.getItem(PREFS_KEY);
  } catch {
    return null;
  }
}

function storageSet(raw: string): boolean {
  try {
    window.localStorage.setItem(PREFS_KEY, raw);
    return true;
  } catch {
    return false;
  }
}

function storageRemove(): void {
  try {
    window.localStorage.removeItem(PREFS_KEY);
  } catch {
    /* private mode: nothing persisted */
  }
}

function loadPrefs(): Prefs {
  const raw = storageGet();
  if (raw) {
    try {
      return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) };
    } catch {
      /* corrupt value: fall through to defaults */
    }
  }
  return { ...DEFAULTS };
}

function Toggle({ label, body, checked, onChange }: {
  label: string; body: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", padding: "7px 0", borderBottom: "1px solid var(--shell-line)" }}>
      <div style={{ minWidth: 0 }}>
        <strong style={{ display: "block", fontSize: 13 }}>{label}</strong>
        <span className="panel-sub" style={{ fontSize: 12 }}>{body}</span>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        style={{
          width: 40, height: 22, borderRadius: 999, border: 0, cursor: "pointer", flex: "none",
          background: checked ? "var(--shell-teal)" : "#CBD5E1", position: "relative",
        }}
      >
        <span style={{
          position: "absolute", top: 2, left: checked ? 20 : 2, width: 18, height: 18,
          borderRadius: "50%", background: "#fff", transition: "left .15s",
        }} />
      </button>
    </div>
  );
}

/** Recognizable brand mark for integrations with no backend connection
 *  endpoint. The mark is iconography only — connection state stays
 *  honest ("Not Connected") and is never implied by the icon. */
function IntegrationMark({ name }: { name: string }) {
  const mark: Record<string, { bg: string; fg: string; glyph: string }> = {
    "Meta": { bg: "#E7F1FB", fg: "#2F6FBE", glyph: "M" },
    "TikTok": { bg: "#F0E9FA", fg: "#1F2A37", glyph: "♪" },
    "Google Analytics 4": { bg: "#FBF3E2", fg: "#C2521F", glyph: "GA" },
  };
  const m = mark[name] ?? { bg: "#EDF1F6", fg: "#5C6B7A", glyph: "◦" };
  return (
    <span className="insight-ico" aria-hidden="true"
      style={{ background: m.bg, color: m.fg, fontWeight: 800, fontSize: m.glyph.length > 1 ? 12 : 16 }}>
      {m.glyph}
    </span>
  );
}

/** Static appearance mockup: previews the current theme, accent, and
 *  density choices with plain boxes (no live app preview). */
function AppearancePreview({ accent, density, mode }: { accent: string; density: string; mode: string }) {
  const accents: Record<string, string> = {
    "Teal (Default)": "#0E7C8C",
    "Blue": "#2F6FBE",
    "Violet": "#6D5BD0",
  };
  const color = accents[accent] ?? accents["Teal (Default)"];
  const dark = mode === "dark";
  const pad = density === "Compact" ? 4 : 8;
  return (
    <div aria-hidden="true" style={{
      display: "flex", gap: 6, marginTop: 12, border: "1px solid var(--shell-line)",
      borderRadius: 10, overflow: "hidden", background: dark ? "#1F2A37" : "#F4F7FA",
    }}>
      <div style={{ width: 44, background: dark ? "#2B3448" : "#fff", padding: pad, display: "grid", gap: 4, alignContent: "start" }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ height: 8, borderRadius: 4, background: i === 0 ? color : dark ? "#3A465E" : "#E3E9F0" }} />
        ))}
      </div>
      <div style={{ flex: 1, padding: pad, display: "grid", gap: 4, alignContent: "start" }}>
        <div style={{ height: 10, borderRadius: 4, background: color, width: "55%" }} />
        {[0, 1].map((i) => (
          <div key={i} style={{ height: 8, borderRadius: 4, background: dark ? "#3A465E" : "#fff", border: `1px solid ${dark ? "#3A465E" : "#E3E9F0"}` }} />
        ))}
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { me, logout, refresh } = useAuth();
  const { mode, set } = useTheme();
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [saved, setSaved] = useState<Prefs>(loadPrefs);
  const [status, setStatus] = useState("");
  const [sessionOp, setSessionOp] = useState<null | "password" | "logout" | "logout-all">(null);
  const employee = me?.employee;
  const dirty = JSON.stringify(prefs) !== JSON.stringify(saved);

  useEffect(() => {
    const accent = ACCENTS[prefs.accent] ?? ACCENTS["Teal (Default)"];
    document.documentElement.style.setProperty("--shell-teal", accent.teal);
    document.documentElement.style.setProperty("--shell-teal-dark", accent.dark);
    document.body.dataset.density = prefs.density === "Compact" ? "compact" : "";
  }, [prefs.accent, prefs.density]);

  if (!employee) return <p className="muted">Sign In To Manage Settings.</p>;
  const name = `${employee.first_name} ${employee.last_name}`.trim() || employee.email;
  const setPref = <K extends keyof Prefs>(k: K, v: Prefs[K]) =>
    setPrefs((p) => ({ ...p, [k]: v }));

  const save = () => {
    if (!storageSet(JSON.stringify(prefs))) {
      setStatus("Could Not Save Settings In This Browser.");
      return;
    }
    setSaved(prefs);
    setStatus("Settings Saved.");
  };
  const reset = () => {
    setPrefs({ ...DEFAULTS });
    setSaved({ ...DEFAULTS });
    storageRemove();
    setStatus("Defaults Restored.");
  };

  const runSessionOp = async (name: NonNullable<typeof sessionOp>, fn: () => Promise<unknown>) => {
    if (sessionOp !== null) return;
    setSessionOp(name);
    try {
      await fn();
    } finally {
      setSessionOp((cur) => (cur === name ? null : cur));
    }
  };

  const changePassword = async () => {
    setStatus("");
    try {
      await api("POST", "/api/auth/email/reset", { email: employee.email });
      setStatus("Password Reset Email Sent.");
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : "Could Not Send Reset Email.");
    }
  };

  const logoutAll = async () => {
    setStatus("");
    if (!window.confirm("Log Out All Sessions? Every device and browser signed in as this account is signed out immediately.")) return;
    try {
      await api("POST", "/api/auth/sessions/revoke-all", {});
      await refresh();
      setStatus("All Sessions Signed Out.");
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : "Could Not Sign Out All Sessions.");
    }
  };

  const exportData = () => {
    const blob = new Blob(
      [JSON.stringify({ profile: employee, preferences: prefs, exported_at: new Date().toISOString() }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "workspace-data.json";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Workspace Data Exported.");
  };

  const modes: Array<{ id: ThemeMode; label: string }> = [
    { id: "light", label: "Light (Default)" },
    { id: "dark", label: "Dark" },
    { id: "system", label: "System" },
  ];

  return (
    <>
      <PageHeader
        title="Settings"
        sub="Control your workspace, data, integrations, and application preferences."
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 12, marginTop: 12 }}>
          <Panel title="General Settings" sub="Manage your workspace details and default preferences.">
            <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
              <Avatar url={employee.avatar_url} label={name} />
              <div>
                <strong style={{ fontSize: 14 }}>{name}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>{employee.email} · {employee.role} · {employee.status} · {PROVIDER_LABELS[employee.provider] ?? "—"}</p>
              </div>
            </div>
            <div className="filter-grid" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))" }}>
              <div className="field">
                <label htmlFor="s-workspace">Workspace Name</label>
                <input id="s-workspace" value={prefs.workspace} onChange={(e) => setPref("workspace", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="s-tz">Time Zone</label>
                <select id="s-tz" value={prefs.timezone} onChange={(e) => setPref("timezone", e.target.value)}>
                  <option>{prefs.timezone}</option>
                  <option>(GMT-08:00) Pacific Time (US &amp; Canada)</option>
                  <option>(GMT-05:00) Eastern Time (US &amp; Canada)</option>
                  <option>(GMT+00:00) London</option>
                  <option>(GMT+10:00) Sydney</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-view">Default View</label>
                <select id="s-view" value={prefs.defaultView} onChange={(e) => setPref("defaultView", e.target.value)}>
                  {["Dashboard", "Campaigns", "Creatives", "Compare", "Ask The Data", "AI Analyst"].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-currency">Default Currency</label>
                <select id="s-currency" value={prefs.currency} onChange={(e) => setPref("currency", e.target.value)}>
                  {["USD – US Dollar", "AUD – Australian Dollar", "EUR – Euro", "GBP – British Pound"].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-range">Default Date Range</label>
                <select id="s-range" value={prefs.dateRange} onChange={(e) => setPref("dateRange", e.target.value)}>
                  {["Last 7 Days", "Last 30 Days", "Last 90 Days"].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-campview">Default Campaign View</label>
                <select id="s-campview" value={prefs.campaignView} onChange={(e) => setPref("campaignView", e.target.value)}>
                  {["All Campaigns", "Active Only", "Top 10 by Spend"].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
            </div>
          </Panel>
          <Panel title="Notifications" sub="Choose what you want to be notified about. Stored in this browser only — workspace policies are set by your administrator.">
            <Toggle label="Email Reports" body="Receive scheduled reports and key insights via email."
              checked={prefs.emailReports} onChange={(v) => setPref("emailReports", v)} />
            <Toggle label="Campaign Updates" body="Get notified when campaigns are completed or updated."
              checked={prefs.campaignUpdates} onChange={(v) => setPref("campaignUpdates", v)} />
            <Toggle label="AI Insights" body="Receive alerts for new AI analysis and recommendations."
              checked={prefs.aiInsights} onChange={(v) => setPref("aiInsights", v)} />
            <Toggle label="Product Updates" body="Be the first to know about new features and improvements."
              checked={prefs.productUpdates} onChange={(v) => setPref("productUpdates", v)} />
          </Panel>
          <Panel title="Data & Privacy" sub="Manage how your data is used and your privacy preferences. These preferences live in this browser; workspace policy is set by your administrator.">
            <Toggle label="Data Usage" body="Help improve Foap by allowing anonymized usage data."
              checked={prefs.dataUsage} onChange={(v) => setPref("dataUsage", v)} />
            <Toggle label="Share Analytics Data" body="Allow aggregated, anonymized data to contribute to workspace benchmark averages."
              checked={prefs.shareAnalytics} onChange={(v) => setPref("shareAnalytics", v)} />
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "10px 0" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Data Retention Period</strong>
                <span className="panel-sub">Browser preference only — actual workspace retention is managed by your administrator.</span>
              </div>
              <select aria-label="Data Retention Period" value={prefs.retention} onChange={(e) => setPref("retention", e.target.value)}>
                {["12 Months", "24 Months", "36 Months"].map((o) => <option key={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "10px 0" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Export Your Data</strong>
                <span className="panel-sub">Download a copy of your data and account information.</span>
              </div>
              <button type="button" className="btn-outline" onClick={exportData}>
                <Icon name="download" size={15} /> Export Data
              </button>
            </div>
          </Panel>
          <Panel title="Integrations" sub="Connect your data sources to unlock deeper insights."
            action={<a className="link-teal" href="#integration-google">Manage Integrations</a>}>
            <GoogleDriveCard />
            {[["Meta", "Import campaign performance data from Meta Ads."],
              ["TikTok", "Connect your TikTok Ads account for deeper analysis."],
              ["Google Analytics 4", "Link your GA4 property to analyze web performance."]].map(([n, d]) => (
              <div key={n} className="insight">
                <IntegrationMark name={n} />
                <div style={{ flex: 1 }}>
                  <h4>{n}</h4>
                  <p>{d}</p>
                </div>
                <span className="badge-demo">Not Connected</span>
              </div>
            ))}
          </Panel>
          <Panel title="Appearance" sub="Customize how Foap looks and feels.">
            <div className="filter-grid" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))" }}>
              <div className="field">
                <label htmlFor="s-theme">Theme</label>
                <select id="s-theme" value={mode} onChange={(e) => set(e.target.value as ThemeMode)}>
                  {modes.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-accent">Accent Color</label>
                <select id="s-accent" value={prefs.accent} onChange={(e) => setPref("accent", e.target.value)}>
                  {Object.keys(ACCENTS).map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-density">Interface Density</label>
                <select id="s-density" value={prefs.density} onChange={(e) => setPref("density", e.target.value)}>
                  {["Comfortable", "Compact"].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
            </div>
            <p className="panel-sub" style={{ marginTop: 10 }}>Preview</p>
            <AppearancePreview accent={prefs.accent} density={prefs.density} mode={mode} />
          </Panel>
          <Panel title="Security" sub="Keep your account and workspace secure.">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--shell-line)" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Password</strong>
                <span className="panel-sub">Reset your password by email.</span>
              </div>
              <LoadingButton type="button" className="btn-outline" loading={sessionOp === "password"} loadingLabel="Sending…" spinnerClass="spinner dark" disabled={sessionOp !== null} onClick={() => void runSessionOp("password", changePassword)}>
                Change Password
              </LoadingButton>
            </div>
            {/* Two-factor enrolment lives with the sign-in provider, not
              in a browser preference: this control is explicitly
              unavailable rather than a toggle that proves nothing. */}
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--shell-line)" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Two-Factor Authentication</strong>
                <span className="panel-sub">Managed by your sign-in provider or administrator — not available as an in-app toggle.</span>
              </div>
              <span className="badge-demo" title="Two-factor status comes from your sign-in provider">Unavailable</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "10px 0", flexWrap: "wrap" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Active Sessions</strong>
                <span className="panel-sub">Manage your active sessions across devices.</span>
              </div>
              <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <LoadingButton type="button" className="btn-outline" loading={sessionOp === "logout"} loadingLabel="Signing Out…" spinnerClass="spinner dark" disabled={sessionOp !== null} onClick={() => void runSessionOp("logout", logout)}>
                  Log Out
                </LoadingButton>
                <LoadingButton type="button" className="btn-outline" loading={sessionOp === "logout-all"} loadingLabel="Signing Out…" spinnerClass="spinner dark" disabled={sessionOp !== null} onClick={() => void runSessionOp("logout-all", logoutAll)}>
                  Log Out All Sessions
                </LoadingButton>
              </span>
            </div>
          </Panel>
      </div>
      <div style={{ marginTop: 12 }}>
        <Panel title="Data Tools" sub="Advanced analysis tooling for power users.">
          <RetentionPatterns />
          <div style={{ marginTop: 16 }}>
            <CohortBuilder />
          </div>
        </Panel>
      </div>
      {status ? <p className="panel-sub" role="status" style={{ marginTop: 12 }}>{status}</p> : null}
      <Panel title="Save Preferences">
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" className="btn-outline" onClick={reset}>Reset Defaults</button>
          <button type="button" className="btn-primary" disabled={!dirty} onClick={save}>Save Changes</button>
        </div>
        {!dirty ? <p className="panel-sub">No unsaved changes.</p> : null}
      </Panel>
    </>
  );
}

