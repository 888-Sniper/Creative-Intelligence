/** Workspace preferences: the application's settings mechanism.
 *
 *  Persisted per signed-in employee in browser localStorage
 *  (`ci-settings-prefs:<employeeId>`), falling back to the legacy
 *  global key, which is migrated forward once. Identity, security,
 *  and integration actions stay backend-backed; these are local
 *  presentation preferences only.
 */

import type { ThemeMode } from "@/app/useTheme";
import { isLang, type Lang } from "@/i18n/core";

export interface Prefs {
  workspace: string;
  /** IANA time-zone identity (e.g. "Europe/Warsaw"): DST is handled
   *  by the platform, never by a fixed offset. */
  timezone: string;
  language: Lang;
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

/** Selectable time zones: IANA identities with friendly labels. */
export const TIMEZONES: Array<{ id: string; label: string }> = [
  { id: "America/Los_Angeles", label: "(GMT-08:00) Pacific Time (US & Canada)" },
  { id: "America/New_York", label: "(GMT-05:00) Eastern Time (US & Canada)" },
  { id: "Europe/London", label: "(GMT+00:00) London" },
  { id: "Europe/Warsaw", label: "(GMT+01:00) Warsaw, Poland" },
  { id: "Europe/Madrid", label: "(GMT+01:00) Madrid" },
  { id: "Australia/Sydney", label: "(GMT+10:00) Sydney" },
];

export function isTimezone(v: unknown): v is string {
  return typeof v === "string" && TIMEZONES.some((t) => t.id === v);
}

/** Legacy fixed-offset labels mapped onto IANA identities (§9). */
const LEGACY_TZ: Array<[RegExp, string]> = [
  [/pacific/i, "America/Los_Angeles"],
  [/eastern/i, "America/New_York"],
  [/london/i, "Europe/London"],
  [/sydney|auckland|fiji/i, "Australia/Sydney"],
];

function migrateTimezone(raw: unknown): string {
  if (typeof raw !== "string" || !raw) return guessTimezone();
  if (isTimezone(raw)) return raw;
  for (const [re, id] of LEGACY_TZ) {
    if (re.test(raw)) return id;
  }
  return guessTimezone();
}

/** First-run timezone guess from the browser as an IANA identity. */
export function guessTimezone(): string {
  let tz = "";
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    tz = "";
  }
  if (tz && isTimezone(tz)) return tz;
  if (/Australia|Pacific\/Auckland|Pacific\/Fiji/i.test(tz)) return "Australia/Sydney";
  if (/Europe\/London|Europe\/Dublin|Europe\/Lisbon/i.test(tz)) return "Europe/London";
  if (/Europe\/Madrid/i.test(tz)) return "Europe/Madrid";
  if (/Europe\//i.test(tz)) return "Europe/London";
  if (/America\/Los_Angeles|America\/Vancouver|America\/Tijuana|US\/Pacific/i.test(tz)) {
    return "America/Los_Angeles";
  }
  if (/America\//i.test(tz)) return "America/New_York";
  return "Europe/London";
}

export const DEFAULTS: Prefs = {
  workspace: "Foap Creative Intelligence",
  timezone: guessTimezone(),
  language: "en",
  theme: "light",
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

const LEGACY_KEY = "ci-settings-prefs";

function keyFor(employeeId: string): string {
  return employeeId ? `${LEGACY_KEY}:${employeeId}` : LEGACY_KEY;
}

function storageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function normalize(raw: Partial<Prefs>): Prefs {
  const prefs = { ...DEFAULTS, ...raw };
  if (prefs.workspace === "Alex's Workspace") prefs.workspace = DEFAULTS.workspace;
  prefs.timezone = migrateTimezone(prefs.timezone);
  if (!isLang(prefs.language)) prefs.language = "en";
  return prefs;
}

export function loadPrefs(employeeId = ""): Prefs {
  for (const key of [keyFor(employeeId), LEGACY_KEY]) {
    const raw = key ? storageGet(key) : null;
    if (!raw) continue;
    try {
      return normalize(JSON.parse(raw) as Partial<Prefs>);
    } catch {
      /* corrupt value: try the next key, then defaults */
    }
  }
  return { ...DEFAULTS };
}

/** Monotonic edit revision: every save bumps it, so a delayed
 *  server-prefs response can tell "edited then reverted to the
 *  same values" apart from "never edited" (value comparison
 *  cannot). Module-scoped: one app instance per tab. */
let prefsRevision = 0;

export function currentPrefsRevision(): number {
  return prefsRevision;
}

export function savePrefs(employeeId: string, prefs: Prefs): boolean {
  // Bump first: an edit ATTEMPT must invalidate in-flight server
  // merges even when storage itself fails (private mode).
  prefsRevision += 1;
  try {
    window.localStorage.setItem(keyFor(employeeId), JSON.stringify(prefs));
    return true;
  } catch {
    return false;
  }
}

export function clearPrefs(employeeId: string): void {
  try {
    window.localStorage.removeItem(keyFor(employeeId));
  } catch {
    /* private mode: nothing persisted */
  }
}

const ACCENTS: Record<string, { teal: string; dark: string; ink: string }> = {
  "Teal (Default)": { teal: "#00C7B2", dark: "#08786E", ink: "#182536" },
  Blue: { teal: "#2F6FBE", dark: "#1F4E86", ink: "#FFFFFF" },
  Violet: { teal: "#6D5BD0", dark: "#4A3F96", ink: "#FFFFFF" },
};

/** Apply a saved accent + density to the document. Shared by
 *  Settings (on change) and the app shell (on account init) so
 *  appearance follows the account everywhere, not only after a
 *  Settings visit. */
export function applyAccent(accentName: string, density: string): void {
  const accent = ACCENTS[accentName] ?? ACCENTS["Teal (Default)"];
  document.documentElement.style.setProperty("--shell-teal", accent.teal);
  document.documentElement.style.setProperty("--shell-teal-dark", accent.dark);
  document.documentElement.style.setProperty("--brand-teal", accent.teal);
  document.documentElement.style.setProperty("--brand-teal-ink", accent.ink);
  document.body.dataset.density = density === "Compact" ? "compact" : "";
}

/** Server preference keys (snake_case) <-> local Prefs (camelCase). */
export const SERVER_PREF_MAP: Array<[keyof Prefs, string]> = [
  ["workspace", "workspace"], ["defaultView", "default_view"],
  ["currency", "default_currency"], ["dateRange", "default_date_range"],
  ["campaignView", "default_campaign_view"], ["theme", "theme"],
  ["accent", "accent"], ["density", "density"], ["language", "language"],
  ["timezone", "timezone"], ["emailReports", "email_reports"],
  ["campaignUpdates", "campaign_updates"], ["aiInsights", "ai_insights"],
  ["productUpdates", "product_updates"], ["dataUsage", "data_usage"],
  ["shareAnalytics", "share_analytics"], ["retention", "retention"],
];

export function toServerPrefs(prefs: Prefs): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [local, server] of SERVER_PREF_MAP) out[server] = prefs[local];
  return out;
}

export function mergeServerPrefs(local: Prefs, server: Record<string, unknown>): Prefs {
  const next = { ...local };
  for (const [localKey, serverKey] of SERVER_PREF_MAP) {
    if (serverKey in server) {
      (next as Record<string, unknown>)[localKey] = server[serverKey];
    }
  }
  return next;
}

/** Per-account "user explicitly chose a campaign status" memory.
 *  Survives Campaigns unmount/remount within the tab session
 *  (sessionStorage), is scoped per employee so account A's choice
 *  never disables account B's saved default, and is also marked
 *  when Analyst restores a conversation scope containing status. */
const _statusTouchedMemory = new Set<string>();

export function markCampaignStatusTouched(employeeId: string): void {
  _statusTouchedMemory.add(employeeId);
  try {
    window.sessionStorage.setItem(`ci-status-touched:${employeeId}`, "1");
  } catch {
    /* memory copy still applies */
  }
}

export function campaignStatusTouched(employeeId: string): boolean {
  if (_statusTouchedMemory.has(employeeId)) return true;
  try {
    return window.sessionStorage.getItem(
      `ci-status-touched:${employeeId}`) === "1";
  } catch {
    return false;
  }
}

/** Fired after server preferences are merged into local storage so
 *  mounted consumers (locale sync, campaign defaults) can react
 *  without waiting for an identity change or remount. */
export const PREFS_UPDATED_EVENT = "ci-prefs-updated";

export function notifyPrefsUpdated(): void {
  try {
    window.dispatchEvent(new CustomEvent(PREFS_UPDATED_EVENT));
  } catch {
    /* non-browser test env */
  }
}

/** Route for the saved Default View ("Dashboard" stays "/"). */
export function defaultViewPath(prefs: Prefs): string {
  const paths: Record<string, string> = {
    Dashboard: "/",
    Campaigns: "/campaigns",
    Creatives: "/creatives",
    Compare: "/compare",
    "Ask The Data": "/ask",
    Reports: "/reports",
  };
  return paths[prefs.defaultView] ?? "/";
}

/** ISO code of the saved Default Currency label ("EUR – Euro"). */
export function currencyCode(prefs: Prefs): string {
  const code = (prefs.currency || "").slice(0, 3).toUpperCase();
  return /^[A-Z]{3}$/.test(code) ? code : "USD";
}

/** Days for the saved Default Date Range; null means All Time. */
export function rangeDays(prefs: Prefs): number | null {
  if (prefs.dateRange === "Last 7 Days") return 7;
  if (prefs.dateRange === "Last 30 Days") return 30;
  if (prefs.dateRange === "Last 90 Days") return 90;
  return null;
}
