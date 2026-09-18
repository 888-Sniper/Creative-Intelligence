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

export function savePrefs(employeeId: string, prefs: Prefs): boolean {
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
