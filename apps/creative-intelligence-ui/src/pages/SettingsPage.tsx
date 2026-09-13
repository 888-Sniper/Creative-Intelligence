import { useEffect, useState } from "react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { GoogleDriveCard } from "@/components/GoogleDriveCard";
import { CohortBuilder, RetentionPatterns } from "@/components/DataTools";
import { useTheme } from "@/app/useTheme";
import type { ThemeMode } from "@/app/useTheme";
import { Icon } from "@/components/icons";
import { PageHeader, Panel, Toggle } from "@/components/product";
import { LoadingButton } from "@/components/LoadingButton";
import { useSessionCount } from "@/auth/useSessionCount";

/* Settings matches the approved reference. Workspace preferences persist
 * locally per browser; identity/security/drive actions stay backend-backed
 * (logout, session revoke, password-reset email, Drive OAuth status). */

interface Prefs {
  workspace: string;
  timezone: string;
  theme: ThemeMode;
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

const TIMEZONES = [
  "(GMT-08:00) Pacific Time (US & Canada)",
  "(GMT-05:00) Eastern Time (US & Canada)",
  "(GMT+00:00) London",
  "(GMT+10:00) Sydney",
];

/** First-run timezone guess from the browser: mapped onto the fixed
 *  option list so a new account never starts on a mock default. */
function guessTimezone(): string {
  let tz = "";
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    tz = "";
  }
  if (/Australia/i.test(tz)) return "(GMT+10:00) Sydney";
  if (/Pacific\/Auckland|Pacific\/Fiji/i.test(tz)) return "(GMT+10:00) Sydney";
  if (/Europe\/London|Europe\/Dublin|Europe\/Lisbon/i.test(tz)) return "(GMT+00:00) London";
  if (/Europe\//i.test(tz)) return "(GMT+00:00) London";
  if (/America\/Los_Angeles|America\/Vancouver|America\/Tijuana|US\/Pacific/i.test(tz))
    return "(GMT-08:00) Pacific Time (US & Canada)";
  if (/America\/Chicago|America\/Denver|America\/Phoenix|US\/(Central|Mountain|Arizona)/i.test(tz))
    return "(GMT-05:00) Eastern Time (US & Canada)";
  if (/America\//i.test(tz)) return "(GMT-05:00) Eastern Time (US & Canada)";
  return "(GMT+00:00) London";
}

const DEFAULTS: Prefs = {
  workspace: "Foap Creative Intelligence",
  timezone: guessTimezone(),
  theme: "dark",
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

/* Accent overrides repoint the shared primary token (§6) so saved
 * choices keep working: Teal resolves to the logo teal with a dark
 * label (7.2:1; white would be 2.1:1), Blue/Violet keep white labels
 * (5.1:1 / 5.2:1). Hover/pressed derive via color-mix in CSS. */
const ACCENTS: Record<string, { teal: string; dark: string; ink: string }> = {
  "Teal (Default)": { teal: "#00C7B2", dark: "#08786E", ink: "#182536" },
  "Blue": { teal: "#2F6FBE", dark: "#1F4E86", ink: "#FFFFFF" },
  "Violet": { teal: "#6D5BD0", dark: "#4A3F96", ink: "#FFFFFF" },
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
      const prefs = { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) };
      // Retire the old mock default: anyone still carrying it gets the
      // neutral product name (a deliberately renamed workspace is kept).
      if (prefs.workspace === "Alex's Workspace") prefs.workspace = DEFAULTS.workspace;
      return prefs;
    } catch {
      /* corrupt value: fall through to defaults */
    }
  }
  return { ...DEFAULTS };
}

/** Provider mark for integrations with no backend connection endpoint.
 *  Uses the shared stroke icon set (never letter placeholders) tinted per
 *  provider. The mark is iconography only — connection state stays honest
 *  ("Not Connected") and is never implied by the icon. */
function IntegrationMark({ name }: { name: string }) {
  const mark: Record<string, { bg: string; fg: string; icon: string }> = {
    "Meta": { bg: "#E7F1FB", fg: "#2F6FBE", icon: "meta" },
    "TikTok": { bg: "#F0E9FA", fg: "#1F2A37", icon: "tiktok" },
    "Google Analytics 4": { bg: "#FBF3E2", fg: "#C2521F", icon: "google" },
  };
  const m = mark[name] ?? { bg: "#EDF1F6", fg: "#5C6B7A", icon: "grid" };
  return (
    <span className="insight-ico" aria-hidden="true" style={{ background: m.bg, color: m.fg }}>
      <Icon name={m.icon} size={18} />
    </span>
  );
}

/** Static appearance mockup: previews the current theme, accent, and
 *  density choices with plain boxes (no live app preview). */
function AppearancePreview({ accent, density, mode }: { accent: string; density: string; mode: string }) {
  const accents: Record<string, string> = {
    "Teal (Default)": "#00C7B2",
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
        <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 34, padding: "4px 6px",
          background: dark ? "#2B3448" : "#fff", border: `1px solid ${dark ? "#3A465E" : "#E3E9F0"}`, borderRadius: 6 }}>
          {[10, 18, 14, 24, 20, 30].map((h, i) => (
            <div key={i} style={{ flex: 1, height: h, borderRadius: 2, background: i === 5 ? color : dark ? "#3A465E" : "#C9D6E2" }} />
          ))}
        </div>
        <div style={{ height: 8, borderRadius: 4, background: dark ? "#3A465E" : "#fff", border: `1px solid ${dark ? "#3A465E" : "#E3E9F0"}` }} />
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { me, logout, refresh } = useAuth();
  const { mode, theme: resolvedTheme, set } = useTheme();
  /* Staged edits (prefs) vs applied state (saved): accent, density, and
   * theme apply only when Save Changes is clicked, so leaving the page
   * with unsaved edits never mutates the live app appearance. */
  const [prefs, setPrefs] = useState<Prefs>(() => ({ ...loadPrefs(), theme: mode }));
  const [saved, setSaved] = useState<Prefs>(() => ({ ...loadPrefs(), theme: mode }));
  const [status, setStatus] = useState("");
  const [sessionOp, setSessionOp] = useState<null | "password" | "logout" | "logout-all">(null);
  // One adaptive button (§9): "Log Out All Sessions" only when the
  // server reports several live sessions, plain "Log Out" for exactly
  // one. An unknown count renders loading/retry — never a guess.
  const { count: sessionCount, error: sessionError, reload: reloadSessions } = useSessionCount();
  const multiSession = (sessionCount ?? 0) > 1;
  const employee = me?.employee;
  const dirty = JSON.stringify(prefs) !== JSON.stringify(saved);

  useEffect(() => {
    const accent = ACCENTS[saved.accent] ?? ACCENTS["Teal (Default)"];
    document.documentElement.style.setProperty("--shell-teal", accent.teal);
    document.documentElement.style.setProperty("--shell-teal-dark", accent.dark);
    document.documentElement.style.setProperty("--brand-teal", accent.teal);
    document.documentElement.style.setProperty("--brand-teal-ink", accent.ink);
    document.body.dataset.density = saved.density === "Compact" ? "compact" : "";
  }, [saved.accent, saved.density]);

  if (!employee) return <p className="muted">Sign In To Manage Settings.</p>;
  const setPref = <K extends keyof Prefs>(k: K, v: Prefs[K]) =>
    setPrefs((p) => ({ ...p, [k]: v }));

  const save = () => {
    if (!storageSet(JSON.stringify(prefs))) {
      setStatus("Could Not Save Settings In This Browser.");
      return;
    }
    setSaved(prefs);
    /* Theme persists in its own key via the theme hook: apply the staged
     * choice here so Save is the single commit point for appearance. */
    set(prefs.theme);
    setStatus("Settings Saved.");
  };
  const reset = () => {
    const next = { ...DEFAULTS, theme: "dark" as const };
    setPrefs(next);
    setSaved(next);
    set("dark");
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
    { id: "light", label: "Light" },
    { id: "dark", label: "Dark (Default)" },
    { id: "system", label: "System" },
  ];

  return (
    <>
      <PageHeader
        title="Settings"
        sub="Control your workspace, data, integrations, and application preferences."
      />
      <div className="cols-2-even" style={{ marginTop: 12 }}>
          <Panel title="General Settings" icon="gear">
            <div className="filter-grid" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))" }}>
              <div className="field">
                <label htmlFor="s-workspace">Workspace Name</label>
                <input id="s-workspace" value={prefs.workspace} onChange={(e) => setPref("workspace", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="s-tz">Time Zone</label>
                <select id="s-tz" value={prefs.timezone} onChange={(e) => setPref("timezone", e.target.value)}>
                  {TIMEZONES.includes(prefs.timezone) ? null : <option>{prefs.timezone}</option>}
                  {TIMEZONES.map((o) => <option key={o}>{o}</option>)}
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
          <Panel title="Notifications" icon="bell">
            <Toggle label="Email Reports" body="Receive Reports And Insights By Email."
              checked={prefs.emailReports} onChange={(v) => setPref("emailReports", v)} />
            <Toggle label="Campaign Updates" body="Get Notified When Campaigns Are Updated."
              checked={prefs.campaignUpdates} onChange={(v) => setPref("campaignUpdates", v)} />
            <Toggle label="AI Insights" body="Receive Alerts For New AI Analysis."
              checked={prefs.aiInsights} onChange={(v) => setPref("aiInsights", v)} />
            <Toggle label="Product Updates" body="Get Updates On New Features."
              checked={prefs.productUpdates} onChange={(v) => setPref("productUpdates", v)} />
          </Panel>
          <Panel title="Data & Privacy" icon="eye">
            <Toggle label="Data Usage" body="Help Improve Foap With Anonymous Usage Data."
              checked={prefs.dataUsage} onChange={(v) => setPref("dataUsage", v)} />
            <Toggle label="Share Analytics Data" body="Contribute Anonymous Data To Benchmarks."
              checked={prefs.shareAnalytics} onChange={(v) => setPref("shareAnalytics", v)} />
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "11px 0" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Data Retention Period</strong>
                <span className="panel-sub" title="Browser preference only — actual workspace retention is managed by your administrator.">Choose Your Preferred Data Retention Period.</span>
              </div>
              <select aria-label="Data Retention Period" value={prefs.retention} onChange={(e) => setPref("retention", e.target.value)}>
                {["12 Months", "24 Months", "36 Months"].map((o) => <option key={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "11px 0" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Export Your Data</strong>
                <span className="panel-sub">Download Your Account And Workspace Data.</span>
              </div>
              <button type="button" className="btn-outline" onClick={exportData}>
                <Icon name="download" size={15} /> Export Data
              </button>
            </div>
          </Panel>
          <Panel title="Integrations" icon="grid"
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
          <Panel title="Appearance" icon="spark">
            <div className="filter-grid" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))" }}>
              <div className="field">
                <label htmlFor="s-theme">Theme</label>
                <select id="s-theme" value={prefs.theme} onChange={(e) => setPref("theme", e.target.value as ThemeMode)}>
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
            <p className="panel-sub" style={{ marginTop: 10 }}>Preview — shows your staged choices before you save.</p>
            <AppearancePreview
              accent={prefs.accent}
              density={prefs.density}
              mode={prefs.theme === "system" ? resolvedTheme : prefs.theme}
            />
            {dirty ? <p className="panel-sub">Unsaved changes — click Save Changes to apply.</p> : null}
          </Panel>
          <Panel title="Security" icon="lock">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "11px 0", borderBottom: "1px solid var(--shell-line)" }}>
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
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", padding: "11px 0", borderBottom: "1px solid var(--shell-line)" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Two-Factor Authentication</strong>
                <span className="panel-sub">Managed by your sign-in provider or administrator.</span>
              </div>
              <span className="badge-demo" style={{ marginTop: 2, flexShrink: 0 }} title="Two-factor status comes from your sign-in provider">Unavailable</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "11px 0", flexWrap: "wrap" }}>
              <div>
                <strong style={{ display: "block", fontSize: 13.5 }}>Active Sessions</strong>
                <span className="panel-sub">
                  {sessionCount !== null
                    ? `${sessionCount} Active Session${sessionCount === 1 ? "" : "s"} On This Account.`
                    : sessionError
                      ? "Could Not Load Sessions."
                      : "Checking Sessions…"}
                </span>
              </div>
              {sessionCount !== null ? (
                <LoadingButton type="button" className="btn-outline" loading={sessionOp !== null && sessionOp !== "password"} loadingLabel="Signing Out…" spinnerClass="spinner dark" disabled={sessionOp !== null} onClick={() => void runSessionOp(multiSession ? "logout-all" : "logout", multiSession ? logoutAll : logout)}>
                  {multiSession ? "Log Out All Sessions" : "Log Out"}
                </LoadingButton>
              ) : sessionError ? (
                <button type="button" className="btn-outline" onClick={reloadSessions}>
                  Retry
                </button>
              ) : (
                <button type="button" className="btn-outline" disabled aria-busy="true">
                  Checking Sessions…
                </button>
              )}
            </div>
          </Panel>
      </div>
      <details className="panel" style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontSize: 15.5, fontWeight: 700, color: "var(--shell-navy)" }}>
          Advanced
        </summary>
        <p className="panel-sub">Power-user analysis tooling.</p>
        <div style={{ marginTop: 12 }}>
          <RetentionPatterns />
        </div>
        <div style={{ marginTop: 16 }}>
          <CohortBuilder />
        </div>
      </details>
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, marginTop: 12 }}>
        {status ? (
          <span className="panel-sub" role="status" style={{ marginRight: "auto" }}>
            {status}
          </span>
        ) : null}
        <button type="button" className="btn-outline" onClick={reset}>Reset Defaults</button>
        <button type="button" className="btn-primary" disabled={!dirty} onClick={save}>Save Changes</button>
      </div>
    </>
  );
}

