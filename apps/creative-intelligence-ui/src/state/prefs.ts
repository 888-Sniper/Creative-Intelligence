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

/** Per-account explicit campaign-status choice, VALUE included.
 *  Flag and value live together (sessionStorage + memory) so a
 *  reload — which resets shared filters to empty — restores the
 *  chosen status instead of keeping the flag but losing the value
 *  (which used to strand the page on "All"). Scoped per employee;
 *  also marked when Analyst restores a scope containing status. */
const _statusTouchedMemory = new Map<string, string>();

export function markCampaignStatusTouched(employeeId: string,
                                          value = ""): void {
  _statusTouchedMemory.set(employeeId, value);
  try {
    window.sessionStorage.setItem(
      `ci-status-touched:${employeeId}`, value || "1");
  } catch {
    /* memory copy still applies */
  }
}

/** The explicitly chosen status for this account, or null if none.
 *  Legacy flag-only entries ("1") return "" (touched, value lost
 *  before this fix — treated as touched with no value to restore). */
export function touchedCampaignStatus(employeeId: string): string | null {
  if (_statusTouchedMemory.has(employeeId)) {
    return _statusTouchedMemory.get(employeeId) ?? "";
  }
  try {
    const raw = window.sessionStorage.getItem(
      `ci-status-touched:${employeeId}`);
    if (raw === null) return null;
    return raw === "1" ? "" : raw;
  } catch {
    return null;
  }
}

export function campaignStatusTouched(employeeId: string): boolean {
  return touchedCampaignStatus(employeeId) !== null;
}

/** Forget an explicit status choice entirely (back to "never
 *  chosen", so the saved default applies again). Used when a
 *  temporary scope that cleared filters programmatically ends
 *  and the pre-scope untouched state must be restored. */
export function clearCampaignStatusTouched(employeeId: string): void {
  _statusTouchedMemory.delete(employeeId);
  try {
    window.sessionStorage.removeItem(`ci-status-touched:${employeeId}`);
  } catch {
    /* memory copy already cleared */
  }
}

/** Last SERVER-ISSUED prefs version seen for an account, persisted
 *  in localStorage so it survives reloads and is shared across
 *  tabs (unlike the in-memory edit counter above, which only
 *  guards in-flight merges within one tab). */
export function serverPrefsRevision(employeeId: string): number | null {
  try {
    const raw = window.localStorage.getItem(
      `ci-prefs-server-rev:${employeeId}`);
    const n = raw === null ? NaN : Number(raw);
    return Number.isInteger(n) ? n : null;
  } catch {
    return null;
  }
}

export function noteServerPrefsRevision(employeeId: string,
                                        prefs: Record<string, unknown>): void {
  const rev = prefs["_rev"];
  if (typeof rev !== "number" || !Number.isInteger(rev)) return;
  try {
    window.localStorage.setItem(
      `ci-prefs-server-rev:${employeeId}`, String(rev));
  } catch {
    /* storage unavailable: next save bootstraps with unknown base */
  }
}

/** THIS TAB's last confirmed server snapshot per account
 *  (server-shaped, including `_rev`). The version a save claims
 *  as its base must describe the snapshot the tab actually
 *  edited — the localStorage revision above is shared across
 *  tabs, so pairing it with a stale whole document let one tab
 *  overwrite another tab's unrelated edits. Saves therefore
 *  send only the keys that differ from this snapshot. */
const _serverSnapshots = new Map<string, Record<string, unknown>>();

function prefsRevisionOf(prefs: Record<string, unknown> | null): number | null {
  const rev = prefs?.["_rev"];
  return typeof rev === "number" && Number.isInteger(rev) ? rev : null;
}

/** Newest server version this browser has confirmed for the
 *  account (in-memory snapshot or the persisted note). */
function confirmedRevision(employeeId: string): number | null {
  const a = prefsRevisionOf(_serverSnapshots.get(employeeId) ?? null);
  const b = serverPrefsRevision(employeeId);
  if (a === null) return b;
  if (b === null) return a;
  return Math.max(a, b);
}

/** True when a GET response is OLDER than state this browser
 *  already confirmed (e.g. it was read before an in-flight PUT
 *  landed, then delivered after it — possibly to a remounted
 *  page whose local guards know nothing of that save). Server
 *  versions only move forward, so an older response can be
 *  dropped wholesale. */
export function isStaleServerPrefs(employeeId: string,
                                   prefs: Record<string, unknown>): boolean {
  const incoming = prefsRevisionOf(prefs);
  const confirmed = confirmedRevision(employeeId);
  return incoming !== null && confirmed !== null && incoming < confirmed;
}

export function noteServerPrefsSnapshot(employeeId: string,
                                        prefs: Record<string, unknown>): void {
  // The snapshot never moves backward: a stale response must
  // not downgrade the confirmed state (or its base version).
  if (isStaleServerPrefs(employeeId, prefs)) return;
  _serverSnapshots.set(employeeId, { ...prefs });
  noteServerPrefsRevision(employeeId, prefs);
}

export function serverPrefsSnapshot(employeeId: string): Record<string, unknown> | null {
  return _serverSnapshots.get(employeeId) ?? null;
}

/** Server-shaped keys THIS commit changed (prev local → next
 *  local). Saves are built from these — never from a
 *  local-vs-snapshot diff, which would re-send stale local
 *  values for keys another tab changed after this tab's
 *  snapshot (the form legitimately diverges from the snapshot
 *  until a merge reconciles it). */
export function serverPrefsChanges(prev: Prefs,
                                   next: Prefs): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  for (const [local, server] of SERVER_PREF_MAP) {
    if (prev[local] !== next[local]) changes[server] = next[local];
  }
  return changes;
}

/** Unconfirmed changed keys per account, accumulated across
 *  commits until the server accepts them. Each entry carries
 *  the GENERATION (sequence) of the edit that produced it: a
 *  delayed response confirms only the edits it actually
 *  carried, never a newer edit that merely returns to the
 *  same value. A failed or still-queued write leaves its
 *  entries here, so Retry (which re-commits identical prefs,
 *  an empty diff) still flushes them. */
interface PendingEntry { value: unknown; seq: number }
const _pendingPrefs = new Map<string, Record<string, PendingEntry>>();
let _pendingSeq = 0;

export function queuePrefsChanges(employeeId: string,
                                  changes: Record<string, unknown>): void {
  if (!Object.keys(changes).length) return;
  const seq = ++_pendingSeq;
  const pending = { ...(_pendingPrefs.get(employeeId) ?? {}) };
  for (const [k, v] of Object.entries(changes)) pending[k] = { value: v, seq };
  _pendingPrefs.set(employeeId, pending);
}

/** Reset Defaults: EVERY key is an intended write, superseding
 *  any accumulated pending changes. */
export function replacePendingPrefs(employeeId: string,
                                    serverPrefs: Record<string, unknown>): void {
  const seq = ++_pendingSeq;
  const pending: Record<string, PendingEntry> = {};
  for (const [k, v] of Object.entries(serverPrefs)) pending[k] = { value: v, seq };
  _pendingPrefs.set(employeeId, pending);
}

export function pendingPrefsChanges(employeeId: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, e] of Object.entries(_pendingPrefs.get(employeeId) ?? {})) {
    out[k] = e.value;
  }
  return out;
}

/** A server prefs copy minus keys with unconfirmed local edits:
 *  merging it can never undo an edit whose write is still in
 *  flight (including one started by a previous mount of the
 *  page — pending state is module-level and survives remount). */
export function withoutPendingPrefs(employeeId: string,
                                    prefs: Record<string, unknown>):
    Record<string, unknown> {
  const out = { ...prefs };
  for (const k of Object.keys(_pendingPrefs.get(employeeId) ?? {})) {
    delete out[k];
  }
  return out;
}

/** A flush batch: values to send plus the generation of each,
 *  captured together so confirmation can tell "the edit this
 *  response carried" from "a newer edit with an equal value". */
export function takePendingBatch(employeeId: string): {
  values: Record<string, unknown>;
  seqs: Record<string, number>;
} {
  const values: Record<string, unknown> = {};
  const seqs: Record<string, number> = {};
  for (const [k, e] of Object.entries(_pendingPrefs.get(employeeId) ?? {})) {
    values[k] = e.value;
    seqs[k] = e.seq;
  }
  return { values, seqs };
}

/** Drop keys the server just accepted — only the exact
 *  generations the accepted batch carried. */
export function confirmPrefsChanges(employeeId: string,
                                    seqs: Record<string, number>): void {
  const pending = _pendingPrefs.get(employeeId);
  if (!pending) return;
  const next = { ...pending };
  for (const [key, seq] of Object.entries(seqs)) {
    if (next[key]?.seq === seq) delete next[key];
  }
  _pendingPrefs.set(employeeId, next);
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
