import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { GoogleDriveCard } from "@/components/GoogleDriveCard";
import { CohortBuilder, RetentionPatterns } from "@/components/DataTools";
import { EmployeeAvatar } from "@/components/product";
import {
  EmptyState,
  PageHeader,
  PageSkeleton,
  Panel,
  Toast,
  Toggle,
  codeLabel,
} from "@/components/product";
import { useGoogleStatus } from "@/auth/useGoogleStatus";
import { useSessionCount } from "@/auth/useSessionCount";
import { useTheme, type Theme } from "@/app/useTheme";
import { useLocale } from "@/i18n";
import {
  DEFAULTS,
  TIMEZONES,
  loadPrefs,
  savePrefs,
  type Prefs,
} from "@/state/prefs";
import type { PublicEmployee } from "@/types/auth";
import metaLogo from "@/assets/meta.svg";
import tiktokLogo from "@/assets/tiktok.svg";

const ACCENTS: Record<string, { teal: string; dark: string; ink: string }> = {
  "Teal (Default)": { teal: "#00C7B2", dark: "#08786E", ink: "#182536" },
  "Blue": { teal: "#2F6FBE", dark: "#1F4E86", ink: "#FFFFFF" },
  "Violet": { teal: "#6D5BD0", dark: "#4A3F96", ink: "#FFFFFF" },
};

/** Stored accent values stay stable English identifiers (persisted user
 *  data); only the displayed option names go through the UI locale. */
const ACCENT_LABEL_KEYS: Record<string, string> = {
  "Teal (Default)": "settings.appearance.accents.tealDefault",
  Blue: "settings.appearance.accents.blue",
  Violet: "settings.appearance.accents.violet",
};

/** Stored retention values stay stable ("6 Months", …); display names
 *  are localized. */
const RETENTION_LABEL_KEYS: Record<string, string> = {
  "6 Months": "settings.privacy.retentionOptions.r6",
  "12 Months": "settings.privacy.retentionOptions.r12",
  "24 Months": "settings.privacy.retentionOptions.r24",
  Indefinite: "settings.privacy.retentionOptions.indefinite",
};

function applyAccent(accentName: string, density: string): void {
  const accent = ACCENTS[accentName] ?? ACCENTS["Teal (Default)"];
  document.documentElement.style.setProperty("--shell-teal", accent.teal);
  document.documentElement.style.setProperty("--shell-teal-dark", accent.dark);
  document.documentElement.style.setProperty("--brand-teal", accent.teal);
  document.documentElement.style.setProperty("--brand-teal-ink", accent.ink);
  document.body.dataset.density = density === "Compact" ? "compact" : "";
}
const VIEWS = ["Dashboard", "Campaigns", "Creatives", "Compare", "Ask The Data", "Reports"];
const CURRENCIES = ["USD – US Dollar", "AUD – Australian Dollar", "EUR – Euro", "GBP – British Pound"];
const RANGES = ["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"];
const CAMPAIGN_VIEWS = ["All Campaigns", "Active Only", "By Platform"];
const RETENTIONS = ["6 Months", "12 Months", "24 Months", "Indefinite"];
const DENSITIES = ["Comfortable", "Compact"];

function cap(v: string): string {
  return v ? v.charAt(0).toUpperCase() + v.slice(1) : v;
}

/** Load prefs, honoring an explicit legacy `ci-theme` choice until the
 *  stored prefs carry their own theme (useTheme owns that key and stays
 *  the live source of truth; every autosave commit re-syncs both). */
function adoptPrefs(employeeId: string, liveTheme: Prefs["theme"]): Prefs {
  const loaded = loadPrefs(employeeId);
  try {
    const keys = employeeId
      ? [`ci-settings-prefs:${employeeId}`, "ci-settings-prefs"]
      : ["ci-settings-prefs"];
    for (const k of keys) {
      const raw = window.localStorage.getItem(k);
      if (!raw) continue;
      const parsed = JSON.parse(raw) as Partial<Prefs>;
      if (typeof parsed.theme === "string") return loaded;
      return { ...loaded, theme: liveTheme };
    }
  } catch {
    /* unreadable storage: fall through to the live theme */
  }
  return { ...loaded, theme: liveTheme };
}

const AVATAR_MIME = ["image/jpeg", "image/png", "image/webp"];
const AVATAR_MAX = 2 * 1024 * 1024;

/** Resolve the live theme choice for the appearance preview: an
 *  explicit mode wins, while "system" follows the OS (falling back
 *  to the live resolved theme where matchMedia is unavailable,
 *  e.g. unit tests). */
function resolvePreviewTheme(live_choice: Prefs["theme"], live: Theme): Theme {
  if (live_choice !== "system") return live_choice;
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch {
      /* fall through to the live theme */
    }
  }
  return live;
}

/** Appearance preview driven by the LIVE theme, accent and density
 *  (§8): choosing in the selects above visibly changes this mockup
 *  at once, because every choice saves automatically. */
function AppearancePreview({ accent, density, mode }: { accent: string; density: string; mode: Theme }) {
  const color = ACCENTS[accent]?.teal ?? ACCENTS["Teal (Default)"].teal;
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
  const { me, logout: authLogout } = useAuth();
  const { mode: liveThemeMode, theme: liveTheme, set: setThemeMode } = useTheme();
  const { t, tp, fmtDate, setLang, setTimezone } = useLocale();

  const [employee, setEmployee] = useState<PublicEmployee | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  // Workspace preferences (§9: per-employee key with legacy
  // fallback, IANA time zones). Autosaved: every control persists
  // immediately (text fields debounced + validated), so there is no
  // staged form and no Save button. `prefs` is the live truth.
  const [prefs, setPrefs] = useState<Prefs>(() => adoptPrefs(me?.employee?.id ?? "", liveThemeMode));
  const [prefOwner, setPrefOwner] = useState(me?.employee?.id ?? "");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState("");
  const [status, setStatus] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const closeToast = useCallback(() => setToast(null), []);
  const notifyOk = useCallback((message: string) => {
    setStatus("");
    setToast(message);
  }, []);

  // Personal-info editing (merged from Profile).
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [avatarOpen, setAvatarOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const firstRef = useRef<HTMLInputElement | null>(null);
  const [op, setOp] = useState<string | null>(null);

  // Session actions (bounded hook, §11).
  const sessions = useSessionCount();
  const [sessionOp, setSessionOp] = useState<string | null>(null);

  // Provider connection badge: Google sign-in alone never marks the
  // provider row connected — only a live Google check does. Bounded
  // like the Drive card (§11): a stalled lookup fails instead of
  // leaving the badge on an assumed state forever.
  const google = useGoogleStatus();
  const googleConnected = google.connected;

  const loadEmployee = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const r = await api<{ employee: PublicEmployee | null }>("GET", "/api/auth/me");
      if (r.employee) {
        setEmployee(r.employee);
        setFirst(r.employee.first_name || "");
        setLast(r.employee.last_name || "");
        setAvatarUrl(r.employee.avatar_url || "");
      } else {
        setLoadError(t("settings.footer.accountUnavailable"));
      }
    } catch {
      setLoadError(t("settings.footer.couldNotLoad"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadEmployee();
  }, [loadEmployee]);

  // Live mirror of prefs for debounced commits (avoids stale
  // closures inside timers).
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  // Monotonic revision: each commit bumps it, so a debounced text
  // commit only lands when no newer keystroke superseded it
  // (last-write-wins with an in-flight guard against lost updates).
  const revRef = useRef(0);
  const nameTimer = useRef<number | null>(null);
  const [nameDraft, setNameDraft] = useState(prefs.workspace);
  const [nameError, setNameError] = useState("");
  const nameDraftRef = useRef(nameDraft);
  nameDraftRef.current = nameDraft;

  const applyLive = useCallback((next: Prefs) => {
    setThemeMode(next.theme);
    applyAccent(next.accent, next.density);
    setLang(next.language);
    setTimezone(next.timezone);
  }, [setThemeMode, setLang, setTimezone]);

  /** Persist one autosave commit synchronously (localStorage).
   *  Optimistic: live values apply first so the controls never snap
   *  back; storage failure keeps them visible with an error + Retry
   *  (which re-persists exactly what is shown). */
  const commit = useCallback((next: Prefs) => {
    const id = employee?.id ?? me?.employee?.id ?? "";
    revRef.current += 1;
    setPrefs(next);
    if (next.workspace !== nameDraftRef.current) setNameDraft(next.workspace);
    applyLive(next);
    setSaveState("saving");
    setSaveError("");
    const ok = savePrefs(id, next);
    if (!ok) {
      setSaveState("error");
      setSaveError(t("settings.footer.couldNotSave"));
      return false;
    }
    setSaveState("saved");
    return true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employee?.id, t, applyLive]);

  const retrySave = useCallback(() => {
    commit(prefsRef.current);
  }, [commit]);

  const update = useCallback(<K extends keyof Prefs>(key: K, value: Prefs[K]) => {
    commit({ ...prefsRef.current, [key]: value });
  }, [commit]);

  const onWorkspaceInput = useCallback((raw: string) => {
    setNameDraft(raw);
    setNameError("");
    setSaveState("saving");
    const rev = revRef.current + 1;
    revRef.current = rev;
    if (nameTimer.current !== null) window.clearTimeout(nameTimer.current);
    nameTimer.current = window.setTimeout(() => {
      // In-flight guard: a newer keystroke already superseded this
      // commit — drop it so the latest text wins.
      if (rev !== revRef.current || raw !== nameDraftRef.current) return;
      const value = raw.trim();
      if (!value) {
        setNameError(t("settings.general.workspaceRequired"));
        setSaveState("idle");
        return;
      }
      commit({ ...prefsRef.current, workspace: value.slice(0, 80) });
    }, 450);
  }, [commit, t]);

  useEffect(() => () => {
    if (nameTimer.current !== null) window.clearTimeout(nameTimer.current);
  }, []);

  // Adopt the signed-in employee's own preference key once identity
  // arrives. With autosave there is no staged form to clobber, but a
  // debounced name commit still in flight must not be lost: persist
  // the live values under the new key instead of reloading.
  useEffect(() => {
    const id = employee?.id ?? me?.employee?.id ?? "";
    if (id && id !== prefOwner) {
      setPrefOwner(id);
      if (saveState === "saving" || nameDraftRef.current !== prefsRef.current.workspace) {
        savePrefs(id, { ...prefsRef.current, workspace: nameDraftRef.current.trim() || prefsRef.current.workspace });
      } else {
        const loaded = adoptPrefs(id, liveThemeMode);
        setPrefs(loaded);
        setNameDraft(loaded.workspace);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employee?.id]);

  useEffect(() => {
    applyAccent(prefs.accent, prefs.density);
  }, [prefs.accent, prefs.density]);

  const resetDefaults = () => {
    // Reset applies full defaults immediately (autosave: live values,
    // not a staged form): persist them under this employee's key
    // (never delete it — deletion lets a stale legacy global record
    // resurface on the next load), and apply every one live —
    // including the locale context (§9), so the active language/time
    // zone return to defaults instead of staying on the previous
    // selection.
    const next = { ...DEFAULTS };
    const id = employee?.id ?? me?.employee?.id ?? "";
    savePrefs(id, next);
    setPrefs(next);
    setNameDraft(next.workspace);
    setNameError("");
    setSaveState("saved");
    setSaveError("");
    setThemeMode(next.theme);
    applyAccent(next.accent, next.density);
    setLang(next.language);
    setTimezone(next.timezone);
    notifyOk(t("toast.defaultsRestored"));
  };

  const saveFeedback = saveState === "saving" ? t("settings.autosave.saving")
    : saveState === "saved" ? t("settings.autosave.saved")
    : saveState === "error" ? saveError : "";

  const saveProfile = async () => {
    setOp("profile");
    try {
      // PATCH is the backend's update route; only send avatar_url when it
      // changed so a plain name save can never clear the avatar.
      const payload: { first_name: string; last_name: string; avatar_url?: string } = {
        first_name: first.trim(),
        last_name: last.trim(),
      };
      if (avatarUrl.trim() !== (employee?.avatar_url || "")) {
        payload.avatar_url = avatarUrl.trim();
      }
      const r = await api<{ employee: PublicEmployee }>("PATCH", "/api/auth/me", payload);
      setEmployee(r.employee);
      setFirst(r.employee.first_name || "");
      setLast(r.employee.last_name || "");
      setAvatarUrl(r.employee.avatar_url || "");
      notifyOk(t("toast.profileSaved"));
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("settings.footer.couldNotSaveProfile"));
    } finally {
      setOp(null);
    }
  };

  const removeAvatar = async () => {
    // No DELETE route exists; an empty avatar_url in PATCH clears the avatar.
    setOp("avatar");
    try {
      const r = await api<{ employee: PublicEmployee }>("PATCH", "/api/auth/me", {
        avatar_url: "",
      });
      setEmployee(r.employee);
      setAvatarUrl("");
      notifyOk(t("toast.avatarRemoved"));
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : "Could not remove avatar.");
    } finally {
      setOp(null);
    }
  };

  const onAvatarFile = async (file: File | undefined) => {
    if (!file) return;
    if (!AVATAR_MIME.includes(file.type) || file.size > AVATAR_MAX) {
      setStatus(t("settings.personalInfo.uploadHint"));
      return;
    }
    setOp("avatar");
    setStatus("");
    try {
      // The upload endpoint accepts multipart FormData only (avatar file field).
      const form = new FormData();
      form.append("avatar", file);
      const up = await fetch("/api/auth/me/avatar", { method: "POST", body: form });
      const uj = (await up.json().catch(() => ({}))) as {
        error?: string;
        employee?: PublicEmployee;
      };
      if (!up.ok) throw new Error(uj.error || String(up.status));
      if (uj.employee) {
        setEmployee(uj.employee);
        setAvatarUrl(uj.employee.avatar_url || "");
      }
      notifyOk(t("toast.profileSaved"));
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("settings.footer.couldNotUploadPhoto"));
    } finally {
      setOp(null);
    }
  };

  const changePassword = async () => {
    if (!employee) return;
    setSessionOp("password");
    setStatus("");
    try {
      // /email/reset sends the reset email; /password/reset completes one.
      await api("POST", "/api/auth/email/reset", { email: employee.email });
      notifyOk(t("settings.security.passwordResetSent"));
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("settings.footer.couldNotSendReset"));
    } finally {
      setSessionOp(null);
    }
  };

  const logOut = async () => {
    // Gate-driven logout (prior behavior): the provider refreshes identity
    // and the auth gate routes to login client-side. A full-document
    // navigation would hit the API origin, which has no SPA fallback.
    setSessionOp("logout");
    try {
      await authLogout();
    } catch {
      setSessionOp(null);
    }
  };

  const logOutAll = async () => {
    // Destructive session action: confirm first, matching prior behavior.
    if (typeof window.confirm === "function" && !window.confirm(t("settings.security.logOutAllConfirm"))) {
      return;
    }
    setSessionOp("logout-all");
    setStatus("");
    try {
      await api("POST", "/api/auth/sessions/revoke-all", {});
      notifyOk(t("settings.security.allSessionsSignedOut"));
      sessions.reload();
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("settings.footer.couldNotSignOut"));
    } finally {
      setSessionOp(null);
    }
  };

  const exportData = async () => {
    setOp("export");
    setStatus("");
    try {
      const r = await api<{ exported?: boolean }>("POST", "/api/auth/export", {});
      if (r && r.exported === false) setStatus(t("settings.privacy.exportUnavailable"));
      else notifyOk(t("settings.privacy.exported"));
    } catch (err) {
      setStatus(err instanceof ApiError ? err.message : t("settings.privacy.exportUnavailable"));
    } finally {
      setOp(null);
    }
  };

  if (loading || !employee) {
    return (
      <div className="settings">
        <PageHeader title={t("settings.title")} sub={t("settings.sub")} />
        {loadError ? (
          <p role="alert" className="muted">{loadError}</p>
        ) : (
          <PageSkeleton label={t("settings.title")} panels={6} />
        )}
      </div>
    );
  }

  const empNo = employee.employee_no || employee.id;
  const lastSignIn = employee.last_login_at
    ? fmtDate(employee.last_login_at, { hour: "numeric", minute: "2-digit" })
    : t("settings.workspace.neverSignedIn");
  const heroName = `${employee.first_name} ${employee.last_name}`.trim() || employee.email;
  const heroStats = [
    { label: t("settings.accountStatus"), value: employee.status ? codeLabel(t, "statuses", employee.status) : t("settings.workspace.unavailable") },
    { label: t("settings.signInMethod"), value: employee.provider ? `${cap(employee.provider)} SSO` : t("settings.workEmail") },
    { label: t("settings.lastSignIn"), value: lastSignIn },
  ];
  const providerName = cap(employee.provider || "email");
  const ssoBody = employee.provider === "google"
    ? t("settings.connections.googleLinked")
    : t("settings.connections.providerLinked", { provider: providerName });

  return (
    <div className="settings">
      <PageHeader
        title={t("settings.title")}
        sub={t("settings.sub")}
        actions={(
          <>
            {saveFeedback ? (
              <span className="panel-sub" role="status" style={{ margin: 0, fontSize: 12.5 }}>
                {saveFeedback}
              </span>
            ) : null}
            {saveState === "error" ? (
              <button type="button" className="link-teal" onClick={retrySave}>
                {t("common.retry")}
              </button>
            ) : null}
            <button type="button" className="btn-outline" onClick={() => resetDefaults()}>
              {t("settings.footer.resetDefaults")}
            </button>
          </>
        )}
      />

      <Panel>
        <div className="profile-hero">
          <div className="profile-hero-left">
            <EmployeeAvatar
              url={employee.avatar_url || ""}
              name={heroName}
              email={employee.email || ""}
              size={140}
            />
            <div style={{ minWidth: 0 }}>
              <p style={{ margin: "2px 0 0", fontSize: 22, fontWeight: 800, color: "var(--shell-navy)" }}>
                {heroName}
              </p>
              <p className="panel-sub" style={{ marginTop: 4 }}>
                {`${codeLabel(t, "roles", employee.role)} · ${codeLabel(t, "statuses", employee.status)}`}
              </p>
              <p className="panel-sub" style={{ marginTop: 2 }}>{employee.email}</p>
              <div className="chip-row" style={{ marginTop: 12 }}>
                <button type="button" className="btn-outline" onClick={() => firstRef.current?.focus()}>
                  <Icon name="user" size={14} /> {t("settings.personalInfo.editProfile")}
                </button>
                <LoadingButton type="button" className="btn-primary" loading={op === "avatar"}
                  loadingLabel={t("common.sending")} disabled={op !== null}
                  title={t("settings.personalInfo.uploadHint")}
                  onClick={() => fileRef.current?.click()}>
                  <Icon name="download" size={14} /> {t("settings.personalInfo.uploadPhoto")}
                </LoadingButton>
              </div>
            </div>
          </div>
          <div className="profile-hero-right">
            {heroStats.map((s) => (
              <div key={s.label} style={{ background: "var(--shell-bg)", border: "1px solid var(--shell-line)", borderRadius: 10, padding: "10px 12px", minWidth: 0 }}>
                <p className="panel-sub" style={{ margin: 0, fontSize: 11.5 }}>{s.label}</p>
                <p style={{ margin: "2px 0 0", fontSize: 14, fontWeight: 700, color: "var(--shell-navy)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {s.value}
                </p>
              </div>
            ))}
          </div>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          aria-label={t("settings.personalInfo.uploadPhoto")}
          style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
          onChange={(e) => {
            void onAvatarFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </Panel>

      <div className="section-gap" />
      <div className="cols-3">
        <Panel title={t("settings.personalInfo.title")} sub={t("settings.personalInfo.sub")}>
          <div className="cols-2-even" style={{ marginTop: 0 }}>
            <div className="field">
              <label htmlFor="s-first">{t("settings.personalInfo.firstName")}</label>
              <input
                id="s-first"
                ref={firstRef}
                type="text"
                value={first}
                autoComplete="given-name"
                onChange={(e) => setFirst(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="s-last">{t("settings.personalInfo.lastName")}</label>
              <input
                id="s-last"
                type="text"
                value={last}
                autoComplete="family-name"
                onChange={(e) => setLast(e.target.value)}
              />
            </div>
          </div>
          <div className="chip-row" style={{ marginTop: 12 }}>
            <LoadingButton type="button" className="btn-primary" loading={op === "profile"}
              loadingLabel={t("common.saving")} disabled={op !== null} onClick={() => void saveProfile()}>
              {t("settings.personalInfo.saveProfile")}
            </LoadingButton>
            {employee.avatar_url ? (
              <LoadingButton type="button" className="btn-outline" loading={op === "avatar"}
                loadingLabel={t("common.sending")} disabled={op !== null} onClick={() => void removeAvatar()}>
                {t("settings.personalInfo.removeAvatar")}
              </LoadingButton>
            ) : null}
            {status && op !== null ? (
              <span className="panel-sub" role="status" style={{ margin: 0 }}>{status}</span>
            ) : null}
          </div>
          <details className="disclosure" style={{ marginTop: 12 }} open={avatarOpen} onToggle={(e) => setAvatarOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="panel-sub" style={{ fontWeight: 600 }}>
              {t("settings.personalInfo.advancedAvatar")}
              <span className="disc-chev" aria-hidden="true"><Icon name="chev" size={15} /></span>
            </summary>
            <div className="field" style={{ marginTop: 8 }}>
              <label htmlFor="s-avatar">{t("settings.personalInfo.avatarUrl")}</label>
              <input
                id="s-avatar"
                type="text"
                value={avatarUrl}
                onChange={(e) => setAvatarUrl(e.target.value)}
                placeholder={t("settings.personalInfo.avatarUrlPlaceholder")}
              />
            </div>
          </details>
        </Panel>

        <Panel title={t("settings.workspace.title")} sub={t("settings.workspace.sub")}>
          <dl className="detail-list">
            <div>
              <dt>{t("settings.workspace.employeeId")}</dt>
              <dd>
                <span className="id-copy">
                  <code title={empNo}>{empNo}</code>
                </span>
              </dd>
            </div>
            <div>
              <dt>{t("settings.workspace.role")}</dt>
              <dd>{codeLabel(t, "roles", employee.role)}</dd>
            </div>
            <div>
              <dt>{t("settings.workspace.status")}</dt>
              <dd>{codeLabel(t, "statuses", employee.status)}</dd>
            </div>
            <div>
              <dt>{t("settings.workspace.workEmail")}</dt>
              <dd>{employee.email || "—"}</dd>
            </div>
            <div>
              <dt>{t("settings.workspace.lastLogin")}</dt>
              <dd>{lastSignIn}</dd>
            </div>
            <div>
              <dt>{t("settings.workspace.accountCreated")}</dt>
              <dd>{employee.created_at ? fmtDate(employee.created_at) : t("settings.activity.none")}</dd>
            </div>
          </dl>
        </Panel>

        <Panel title={t("settings.connections.title")} sub={t("settings.connections.sub")}>
          <div className="insight">
            <span className="insight-ico">
              <Icon name="user" size={18} />
            </span>
            <div style={{ flex: 1 }}>
              <h4>{t("settings.connections.workEmail")}</h4>
              <p>{employee.email}</p>
            </div>
            <span className="pill pill-ok">{t("settings.connections.connected")}</span>
          </div>
          {employee.provider ? (
            <div className="insight">
              <span className="insight-ico">
                <Icon name="check" size={18} />
              </span>
              <div style={{ flex: 1 }}>
                <h4 style={{ textTransform: "capitalize" }}>{providerName} SSO</h4>
                <p>{ssoBody}</p>
              </div>
              {google.loading && googleConnected === null ? (
                <span className="panel-sub">{t("drive.checking")}</span>
              ) : googleConnected === false && employee.provider === "google" ? (
                <span className="pill pill-ok">{t("settings.connections.notConnected")}</span>
              ) : (
                <span className="pill pill-ok">{t("settings.connections.connected")}</span>
              )}
            </div>
          ) : null}
          <GoogleDriveCard />
        </Panel>
      </div>

      <div className="section-gap" />
      <div className="cols-3">
        <Panel title={t("settings.security.title")}>
          <SecRow
            title={t("settings.security.password")}
            body={t("settings.security.passwordBody")}
            action={(
              <LoadingButton type="button" className="btn-outline" loading={sessionOp === "password"}
                loadingLabel={t("common.sending")} disabled={sessionOp !== null}
                onClick={() => void changePassword()}>
                {t("settings.security.changePassword")}
              </LoadingButton>
            )}
          />
          <SecRow
            title={t("settings.security.activeSessions")}
            body={
              sessions.loading
                ? t("settings.security.checkingSessions")
                : sessions.error
                  ? t("settings.security.couldNotLoadSessions")
                  : tp("settings.security.activeSessions", sessions.count ?? 0, { count: sessions.count ?? 0 })
            }
            action={(
              sessions.loading ? null : sessions.error ? (
                <button type="button" className="link-teal" onClick={() => sessions.reload()}>
                  {t("common.retry")}
                </button>
              ) : (sessions.count ?? 0) >= 2 ? (
                <LoadingButton type="button" className="btn-outline" loading={sessionOp === "logout-all"}
                  loadingLabel={t("common.signingOut")} disabled={sessionOp !== null}
                  onClick={() => void logOutAll()}>
                  {t("settings.security.logOutAll")}
                </LoadingButton>
              ) : (
                <LoadingButton type="button" className="btn-outline" loading={sessionOp === "logout"}
                  loadingLabel={t("common.signingOut")} disabled={sessionOp !== null}
                  onClick={() => void logOut()}>
                  {t("settings.security.logOut")}
                </LoadingButton>
              )
            )}
          />
          <SecRow
            title={t("settings.security.twoFactor")}
            body={t("settings.security.twoFactorBody")}
            action={(
              <span className="pill pill-info" title={t("settings.security.twoFactorBody")}>
                {t("settings.connections.unavailable")}
              </span>
            )}
            last
          />
        </Panel>

        <Panel title={t("settings.notifications.title")}>
          <Toggle label={t("settings.notifications.emailReports")} body={t("settings.notifications.emailReportsBody")}
            checked={prefs.emailReports} onChange={(v) => update("emailReports", v)} />
          <Toggle label={t("settings.notifications.campaignUpdates")} body={t("settings.notifications.campaignUpdatesBody")}
            checked={prefs.campaignUpdates} onChange={(v) => update("campaignUpdates", v)} />
          <Toggle label={t("settings.notifications.aiInsights")} body={t("settings.notifications.aiInsightsBody")}
            checked={prefs.aiInsights} onChange={(v) => update("aiInsights", v)} />
          <Toggle label={t("settings.notifications.productUpdates")} body={t("settings.notifications.productUpdatesBody")}
            checked={prefs.productUpdates} onChange={(v) => update("productUpdates", v)} />
        </Panel>

        <Panel title={t("settings.activity.title")} sub={t("settings.activity.sub")}>
          <ActivityList
            items={[
              { icon: "user", label: t("settings.activity.accountCreated"), value: employee.created_at ? fmtDate(employee.created_at) : t("settings.activity.none") },
              { icon: "check", label: t("settings.activity.accessApproved"), value: employee.approved_at ? fmtDate(employee.approved_at) : t("settings.activity.none") },
              { icon: "clock", label: t("settings.activity.lastSignedIn"), value: employee.last_login_at ? fmtDate(employee.last_login_at) : t("settings.activity.none") },
            ]}
            emptyText={t("settings.activity.empty")}
            noneText={t("settings.activity.none")}
          />
        </Panel>
      </div>
      <div className="section-gap" />
      <div className="cols-2-even">
        <Panel title={t("settings.general.title")} icon="sliders">
          {/* Balanced three-column rows: Workspace Name spans two
            (wide), Time Zone spans two on its row so long zone labels
            never truncate, and every label holds one line at desktop. */}
          <div className="filter-grid gen-grid">
            <div className="field span-2">
              <label htmlFor="s-workspace">{t("settings.general.workspaceName")}</label>
              <input
                id="s-workspace"
                type="text"
                value={nameDraft}
                maxLength={80}
                aria-invalid={nameError ? true : undefined}
                aria-describedby={nameError ? "s-workspace-error" : undefined}
                onChange={(e) => onWorkspaceInput(e.target.value)}
              />
              {nameError ? (
                <p id="s-workspace-error" role="alert" className="panel-sub" style={{ margin: "6px 0 0", fontSize: 12 }}>
                  {nameError}
                </p>
              ) : null}
            </div>
            <div className="field">
              <label htmlFor="s-language">{t("settings.general.language")}</label>
              <select
                id="s-language"
                value={prefs.language}
                onChange={(e) => update("language", e.target.value as Prefs["language"])}
              >
                <option value="en">{t("settings.languageNames.englishDefault")}</option>
                <option value="es">Español</option>
                <option value="pl">Polski</option>
              </select>
            </div>
            <div className="field span-2">
              <label htmlFor="s-timezone">{t("settings.general.timeZone")}</label>
              <select
                id="s-timezone"
                value={prefs.timezone}
                onChange={(e) => update("timezone", e.target.value)}
              >
                {TIMEZONES.map((z) => (
                  <option key={z.id} value={z.id}>{z.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="s-default-view">{t("settings.general.defaultView")}</label>
              <select
                id="s-default-view"
                value={prefs.defaultView}
                onChange={(e) => update("defaultView", e.target.value)}
              >
                {VIEWS.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="s-currency">{t("settings.general.defaultCurrency")}</label>
              <select
                id="s-currency"
                value={prefs.currency}
                onChange={(e) => update("currency", e.target.value)}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="s-range">{t("settings.general.defaultDateRange")}</label>
              <select
                id="s-range"
                value={prefs.dateRange}
                onChange={(e) => update("dateRange", e.target.value)}
              >
                {RANGES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="s-campaign-view">{t("settings.general.defaultCampaignView")}</label>
              <select
                id="s-campaign-view"
                value={prefs.campaignView}
                onChange={(e) => update("campaignView", e.target.value)}
              >
                {CAMPAIGN_VIEWS.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>
          </div>
        </Panel>

        <Panel title={t("settings.appearance.title")} icon="moon">
          {/* One top row at content-sized widths (never forced equal
            columns); the live preview sits underneath. */}
          <div className="appear-row">
            <div className="field">
              <label htmlFor="s-theme">{t("settings.appearance.theme")}</label>
              <select
                id="s-theme"
                value={prefs.theme}
                onChange={(e) => update("theme", e.target.value as Prefs["theme"])}
              >
                <option value="light">{t("settings.appearance.themeLight")}</option>
                <option value="dark">{t("settings.appearance.themeDark")}</option>
                <option value="system">{t("settings.appearance.themeSystem")}</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="s-accent">{t("settings.appearance.accent")}</label>
              <select
                id="s-accent"
                value={prefs.accent}
                onChange={(e) => update("accent", e.target.value)}
              >
                {Object.keys(ACCENTS).map((a) => (
                  <option key={a} value={a}>{t(ACCENT_LABEL_KEYS[a] ?? a)}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="s-density">{t("settings.appearance.density")}</label>
              <select
                id="s-density"
                value={prefs.density}
                onChange={(e) => update("density", e.target.value)}
              >
                {DENSITIES.map((d) => (
                  <option key={d} value={d}>
                    {d === "Comfortable" ? t("settings.appearance.comfortable") : t("settings.appearance.compact")}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="panel-sub" style={{ fontSize: 12 }}>
            {t("settings.appearance.previewIntro")}
          </p>
          <AppearancePreview
            accent={prefs.accent}
            density={prefs.density}
            mode={resolvePreviewTheme(prefs.theme, liveTheme)}
          />
        </Panel>

        <Panel title={t("settings.integrations.title")} icon="grid">
          <div className="insight">
            <span className="insight-ico svc-tile" aria-hidden="true">
              <img className="svc-logo" src={metaLogo} alt="" />
            </span>
            <div style={{ flex: 1 }}>
              <h4>Meta Ads</h4>
              <p>{t("settings.integrations.metaBody")}</p>
            </div>
            <span className="pill pill-ok">{t("settings.connections.unavailable")}</span>
          </div>
          <div className="insight">
            <span className="insight-ico svc-tile" aria-hidden="true">
              <img className="svc-logo" src={tiktokLogo} alt="" />
            </span>
            <div style={{ flex: 1 }}>
              <h4>TikTok Ads</h4>
              <p>{t("settings.integrations.tiktokBody")}</p>
            </div>
            <span className="pill pill-ok">{t("settings.connections.unavailable")}</span>
          </div>
          <div className="insight">
            <span className="insight-ico" aria-hidden="true">
              <Icon name="report" size={18} />
            </span>
            <div style={{ flex: 1 }}>
              <h4>Google Analytics 4</h4>
              <p>{t("settings.integrations.ga4Body")}</p>
            </div>
            <span className="pill pill-ok">{t("settings.connections.unavailable")}</span>
          </div>
        </Panel>

        <Panel title={t("settings.privacy.title")} icon="shield">
          <Toggle label={t("settings.privacy.dataUsage")} body={t("settings.privacy.dataUsageBody")}
            checked={prefs.dataUsage} onChange={(v) => update("dataUsage", v)} />
          <Toggle label={t("settings.privacy.shareAnalytics")} body={t("settings.privacy.shareAnalyticsBody")}
            checked={prefs.shareAnalytics} onChange={(v) => update("shareAnalytics", v)} />
          <div className="field" style={{ marginTop: 4 }}>
            <label htmlFor="s-retention">{t("settings.privacy.retention")}</label>
            <select
              id="s-retention"
              value={prefs.retention}
              onChange={(e) => update("retention", e.target.value)}
            >
              {RETENTIONS.map((r) => (
                <option key={r} value={r}>{t(RETENTION_LABEL_KEYS[r] ?? r)}</option>
              ))}
            </select>
            <p className="panel-sub" style={{ margin: "6px 0 0", fontSize: 12 }}>
              {t("settings.privacy.retentionHint")}
            </p>
          </div>
          <SecRow
            title={t("settings.privacy.exportData")}
            body={t("settings.privacy.exportDataBody")}
            action={(
              <LoadingButton type="button" className="btn-outline" loading={op === "export"}
                loadingLabel={t("common.sending")} disabled={op !== null} onClick={() => void exportData()}>
                {t("settings.privacy.exportButton")}
              </LoadingButton>
            )}
            last
          />
        </Panel>
      </div>

      <div className="section-gap" />
      <Panel title={t("settings.advanced.title")} sub={t("settings.advanced.sub")} icon="flask">
        <div style={{ marginTop: 12 }}>
          <RetentionPatterns />
        </div>
        <div style={{ marginTop: 16 }}>
          <CohortBuilder />
        </div>
      </Panel>

      {toast ? <Toast message={toast} onClose={closeToast} /> : null}
    </div>
  );
}

function SecRow({ title, body, action, last }: {
  title: string; body: string; action: ReactNode; last?: boolean;
}) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center",
      padding: "14px 0", borderBottom: last ? 0 : "1px solid var(--shell-line)",
    }}>
      <div style={{ minWidth: 0 }}>
        <strong style={{ display: "block", fontSize: 13 }}>{title}</strong>
        <span className="panel-sub" style={{ fontSize: 12 }}>{body}</span>
      </div>
      {action}
    </div>
  );
}

function ActivityList({ items, emptyText, noneText }: {
  items: Array<{ icon: string; label: string; value: string }>;
  emptyText: string; noneText: string;
}) {
  if (items.every((a) => a.value === noneText)) {
    return <EmptyState text={emptyText} />;
  }
  return (
    <div>
      {items.map((a) => (
        <div className="insight" key={a.label}>
          <span className="insight-ico">
            <Icon name={a.icon} size={18} />
          </span>
          <div>
            <h4>{a.label}</h4>
            <p>{a.value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
