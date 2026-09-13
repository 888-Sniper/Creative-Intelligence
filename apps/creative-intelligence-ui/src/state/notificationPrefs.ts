/* Notification quick-preferences shared by Settings and Profile (§3).
 *
 * Same source: the browser-local settings document under PREFS_KEY.
 * Same semantics: patches merge into the stored document (other keys
 * untouched), mirroring how Settings persists. Callers report the
 * returned `saved` flag so failures surface instead of pretending. */

export const PREFS_KEY = "ci-settings-prefs";

export interface NotificationPrefs {
  emailReports: boolean;
  productUpdates: boolean;
}

const DEFAULTS: NotificationPrefs = {
  emailReports: true,
  productUpdates: false,
};

function readDocument(): Record<string, unknown> {
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    if (raw) return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    /* missing storage or corrupt JSON: fall through to defaults */
  }
  return {};
}

export function loadNotificationPrefs(): NotificationPrefs {
  const doc = readDocument();
  return {
    emailReports: typeof doc.emailReports === "boolean"
      ? doc.emailReports : DEFAULTS.emailReports,
    productUpdates: typeof doc.productUpdates === "boolean"
      ? doc.productUpdates : DEFAULTS.productUpdates,
  };
}

/** Merge a patch into the stored document; returns the merged prefs
 *  and whether the write persisted (false in private mode). */
export function saveNotificationPrefs(
  patch: Partial<NotificationPrefs>,
): { prefs: NotificationPrefs; saved: boolean } {
  const next = { ...loadNotificationPrefs(), ...patch };
  try {
    window.localStorage.setItem(
      PREFS_KEY, JSON.stringify({ ...readDocument(), ...next }),
    );
    return { prefs: next, saved: true };
  } catch {
    return { prefs: next, saved: false };
  }
}
