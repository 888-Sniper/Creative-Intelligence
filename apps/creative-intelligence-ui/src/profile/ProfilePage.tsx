import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { useSessionCount } from "@/auth/useSessionCount";
import { Icon } from "@/components/icons";
import { EmployeeAvatar, EmptyState, PageHeader, Panel, Toggle, plural } from "@/components/product";
import { LoadingButton } from "@/components/LoadingButton";
import { loadNotificationPrefs, saveNotificationPrefs } from "@/state/notificationPrefs";
import type { MeResponse, PublicEmployee } from "@/types/auth";

interface ProfileResponse {
  ok: boolean;
  employee: PublicEmployee;
}

interface RevokeResponse {
  ok: boolean;
  revoked: number;
}

function displayName(em: PublicEmployee): string {
  return `${em.first_name || ""} ${em.last_name || ""}`.trim() || em.email || "—";
}

/** Backend stores lowercase codes ("admin", "google"): present them
 *  Title Cased. Unknown/empty values render as-is, never invented. */
function cap(raw: string): string {
  if (!raw) return "—";
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

/** Friendly date for profile surfaces: never a raw ISO string. Empty
 *  or unparseable input renders as "—", never invented. */
export function friendlyDate(raw: string): string {
  if (!raw) return "—";
  const d = new Date(raw.length <= 10 ? `${raw}T00:00:00` : raw);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

/** Employee profile (legacy Web/Index.html v-profile). Email is a verified
 *  identity and stays read-only; first/last name plus avatar URL save via
 *  PATCH /api/auth/me, manual image uploads go to POST /api/auth/me/avatar
 *  as multipart FormData, and removal clears via {avatar_url: ""}. */
export function ProfilePage() {
  const { logout, refresh } = useAuth();
  // Genuine session state for the single adaptive logout action (§9):
  // unknown renders loading/retry, never an invented count.
  const { count: sessionCount, error: sessionError, reload: reloadSessions } = useSessionCount();
  const multiSession = (sessionCount ?? 0) > 1;
  const [notif, setNotif] = useState(loadNotificationPrefs);
  const [notifStatus, setNotifStatus] = useState("");
  const [employee, setEmployee] = useState<PublicEmployee | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [status, setStatus] = useState("");
  const [sessionStatus, setSessionStatus] = useState("");
  const [op, setOp] = useState<null | "save" | "avatar" | "revoke">(null);
  const [copied, setCopied] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const firstRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setLoadError(null);
    api<MeResponse>("GET", "/api/auth/me")
      .then((me) => {
        if (!live) return;
        setEmployee(me.employee);
        if (me.employee) {
          setFirst(me.employee.first_name || "");
          setLast(me.employee.last_name || "");
          const url = me.employee.avatar_url || "";
          setAvatarUrl(url.startsWith("/api/auth/avatar/") ? "" : url);
        }
      })
      .catch((e: unknown) => {
        if (live) setLoadError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  const applyEmployee = (em: PublicEmployee) => {
    setEmployee(em);
    setFirst(em.first_name || "");
    setLast(em.last_name || "");
    const url = em.avatar_url || "";
    setAvatarUrl(url.startsWith("/api/auth/avatar/") ? "" : url);
  };

  const save = async () => {
    if (!employee || op !== null) return;
    setOp("save");
    setStatus("");
    try {
      let current = employee;
      const file = fileRef.current?.files?.[0];
      if (file) {
        const form = new FormData();
        form.append("avatar", file);
        const up = await fetch("/api/auth/me/avatar", { method: "POST", body: form });
        const uj = (await up.json().catch(() => ({}))) as {
          error?: string;
          employee?: PublicEmployee;
        };
        if (!up.ok) throw new Error(uj.error || String(up.status));
        if (uj.employee) {
          current = uj.employee;
          setEmployee(uj.employee);
        }
      }
      const typed = avatarUrl.trim();
      const currentUrl = current.avatar_url || "";
      const payload: { first_name: string; last_name: string; avatar_url?: string } = {
        first_name: first,
        last_name: last,
      };
      if (typed || !currentUrl.startsWith("/api/auth/avatar/")) payload.avatar_url = typed;
      const r = await api<ProfileResponse>("PATCH", "/api/auth/me", payload);
      applyEmployee(r.employee);
      if (fileRef.current) fileRef.current.value = "";
      // Header/account menu reads the auth identity: re-fetch it so the
      // new photo appears everywhere without a hard reload.
      void refresh();
      setStatus("Saved.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setOp((cur) => (cur === "save" ? null : cur));
    }
  };

  const removeAvatar = async () => {
    if (!employee || op !== null) return;
    setOp("avatar");
    setStatus("");
    try {
      const r = await api<ProfileResponse>("PATCH", "/api/auth/me", { avatar_url: "" });
      applyEmployee(r.employee);
      void refresh();
      setStatus("Avatar Removed.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setOp((cur) => (cur === "avatar" ? null : cur));
    }
  };

  /* Single adaptive logout (§9): the action always matches the label
   *  rendered from the same server count — one session ends just this
   *  session, several revoke everything (with confirmation). */
  const signOut = async () => {
    if (op !== null || sessionCount === null) return;
    if (multiSession && !window.confirm(
      "Log Out All Sessions? Every device and browser signed in as this account is signed out immediately.",
    )) return;
    setOp("revoke");
    setSessionStatus("");
    try {
      if (multiSession) {
        const r = await api<RevokeResponse>("POST", "/api/auth/sessions/revoke-all", {});
        await refresh();
        setSessionStatus(`Signed Out Of ${plural(Number(r.revoked ?? 0), "Session")}.`);
      } else {
        await logout();
      }
    } catch (e: unknown) {
      setSessionStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setOp((cur) => (cur === "revoke" ? null : cur));
    }
  };

  /* Notification quick-preferences (§3): same localStorage source and
   * merge semantics as Settings — preference only, no delivery claim. */
  const setNotifPref = (patch: { emailReports?: boolean; productUpdates?: boolean }) => {
    const { prefs, saved } = saveNotificationPrefs(patch);
    setNotif(prefs);
    setNotifStatus(saved ? "Preferences Saved." : "Could Not Save Preferences In This Browser.");
  };

  const heroStats = employee ? [
    { icon: "user", label: "Account Status", value: employee.status ? employee.status.charAt(0).toUpperCase() + employee.status.slice(1) : "Unavailable" },
    { icon: "check", label: "Sign-In Method", value: employee.provider ? `${employee.provider.charAt(0).toUpperCase() + employee.provider.slice(1)} SSO` : "Work Email" },
    { icon: "clock", label: "Member Since", value: employee.created_at ? friendlyDate(employee.created_at) : "Unavailable" },
  ] : [];

  const activity = employee ? [
    { icon: "clock", label: "Last Signed In", value: employee.last_login_at ? friendlyDate(employee.last_login_at) : "—" },
    { icon: "check", label: "Access Approved", value: employee.approved_at ? friendlyDate(employee.approved_at) : "—" },
    { icon: "user", label: "Account Created", value: employee.created_at ? friendlyDate(employee.created_at) : "—" },
  ] : [];

  return (
    <>
      <PageHeader
        title="Profile"
        sub="Your employee profile. Changes are saved to your account immediately."
      />
      {loading && <p className="muted">Loading Profile…</p>}
      {!loading && loadError && <p className="muted">{loadError}</p>}
      {!loading && !loadError && !employee && <p className="muted">Signed Out.</p>}
      {!loading && !loadError && employee && (
        <>
          {/* Hero card (§2): no "Profile Card" header, no greeting — the
            account-summary stack sits at the top, aligned with the
            identity block. */}
          <Panel>
            <div className="profile-hero">
              <div className="profile-hero-left">
                <EmployeeAvatar
                  url={employee.avatar_url || ""}
                  name={displayName(employee)}
                  email={employee.email || ""}
                  size={140}
                />
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: "2px 0 0", fontSize: 22, fontWeight: 800, color: "var(--shell-navy)" }}>
                    {displayName(employee)}
                  </p>
                  <p className="panel-sub" style={{ marginTop: 4 }}>
                    {`${cap(employee.role)} · ${cap(employee.status)}`}
                  </p>
                  <p className="panel-sub" style={{ marginTop: 2 }}>{employee.email}</p>
                  <p className="panel-sub" style={{ marginTop: 2 }}>
                    Team — · Member since {employee.created_at ? friendlyDate(employee.created_at) : "unavailable"}
                    {employee.provider ? ` · Signed in via ${cap(employee.provider)}` : ""}
                  </p>
                  <div className="chip-row" style={{ marginTop: 12 }}>
                    <button type="button" className="btn-outline" onClick={() => firstRef.current?.focus()}>
                      <Icon name="user" size={14} /> Edit Profile
                    </button>
                    <button
                      type="button"
                      className="btn-primary"
                      title="JPEG, PNG or WebP, up to 2 MB"
                      onClick={() => fileRef.current?.click()}
                    >
                      <Icon name="download" size={14} /> Upload Photo
                    </button>
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
              aria-label="Avatar Image File"
              style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
            />
          </Panel>

          <div className="section-gap" />
          <div className="cols-3">
            <Panel title="Personal Info" sub="Name and avatar for your account.">
              <div className="cols-2-even" style={{ marginTop: 0 }}>
                <div className="field">
                  <label htmlFor="p-first">First Name</label>
                  <input
                    id="p-first"
                    ref={firstRef}
                    type="text"
                    value={first}
                    onChange={(e) => setFirst(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="p-last">Last Name</label>
                  <input
                    id="p-last"
                    type="text"
                    value={last}
                    onChange={(e) => setLast(e.target.value)}
                  />
                </div>
              </div>
              <details style={{ marginTop: 12 }}>
                <summary className="panel-sub" style={{ cursor: "pointer", fontWeight: 600 }}>
                  Advanced Avatar Options
                </summary>
                <div className="field" style={{ marginTop: 8 }}>
                  <label htmlFor="p-avatar">Avatar URL (Optional)</label>
                  <input
                    id="p-avatar"
                    type="text"
                    value={avatarUrl}
                    onChange={(e) => setAvatarUrl(e.target.value)}
                    placeholder="avatar image link or blank"
                  />
                </div>
              </details>
              <div className="chip-row" style={{ marginTop: 12 }}>
                <LoadingButton type="button" className="btn-primary" loading={op === "save"} loadingLabel="Saving…" disabled={op !== null} onClick={() => void save()}>
                  Save Profile
                </LoadingButton>
                <LoadingButton type="button" className="btn-outline" loading={op === "avatar"} loadingLabel="Removing…" spinnerClass="spinner dark" disabled={op !== null} onClick={() => void removeAvatar()}>
                  Remove Avatar
                </LoadingButton>
                <span className="panel-sub" role="status" style={{ margin: 0 }}>
                  {status}
                </span>
              </div>
            </Panel>
            <Panel title="Workspace" sub="Identity details managed by your admin.">
              <dl className="detail-list">
                <div>
                  <dt>Employee ID</dt>
                  <dd>
                    <span className="id-copy">
                      <code title={employee.id || undefined}>{employee.id || "—"}</code>
                      {employee.id ? (
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={copied ? "Employee ID copied" : "Copy Employee ID"}
                          title={copied ? "Copied" : "Copy Employee ID"}
                          onClick={() => {
                            try {
                              void navigator.clipboard?.writeText(employee.id);
                            } catch {
                              /* clipboard unavailable: selection still visible via title */
                            }
                            setCopied(true);
                            window.setTimeout(() => setCopied(false), 1500);
                          }}
                        >
                          <Icon name={copied ? "check" : "copy"} size={14} />
                        </button>
                      ) : null}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Work Email</dt>
                  <dd>{employee.email || "—"}</dd>
                </div>
                <div>
                  <dt>Role</dt>
                  <dd style={{ textTransform: "capitalize" }}>{employee.role || "—"}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd style={{ textTransform: "capitalize" }}>{employee.status || "—"}</dd>
                </div>
                <div>
                  <dt>Member Since</dt>
                  <dd>{employee.created_at ? friendlyDate(employee.created_at) : "—"}</dd>
                </div>
                <div>
                  <dt>Last Login</dt>
                  <dd>{employee.last_login_at ? friendlyDate(employee.last_login_at) : "—"}</dd>
                </div>
              </dl>
            </Panel>
            <Panel title="Connections" sub="Ways you can sign in.">
              <div className="insight">
                <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                  <Icon name="user" size={18} />
                </span>
                <div style={{ flex: 1 }}>
                  <h4>Work Email</h4>
                  <p>{employee.email} — verified identity, always available for sign-in.</p>
                </div>
                <span className="pill pill-ok">Connected</span>
              </div>
              {employee.provider ? (
                <div className="insight">
                  <span className="insight-ico" style={{ background: "var(--shell-teal-soft)" }}>
                    <Icon name="check" size={18} />
                  </span>
                  <div style={{ flex: 1 }}>
                    <h4 style={{ textTransform: "capitalize" }}>{employee.provider} SSO</h4>
                    <p>Single sign-on via {employee.provider} is linked to this account.</p>
                  </div>
                  <span className="pill pill-ok">Connected</span>
                </div>
              ) : null}
            </Panel>
          </div>

          <div className="section-gap" />
          <div className="cols-3">
            <Panel title="Security">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "14px 0", borderBottom: "1px solid var(--shell-line)" }}>
                <div style={{ minWidth: 0 }}>
                  <strong style={{ display: "block", fontSize: 13 }}>Two-Factor Authentication</strong>
                  <span className="panel-sub" style={{ fontSize: 12 }}>Managed by your sign-in provider or administrator.</span>
                </div>
                <span className="badge-demo" style={{ flexShrink: 0 }} title="Two-factor status comes from your sign-in provider">Unavailable</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "14px 0" }}>
                <div style={{ minWidth: 0 }}>
                  <strong style={{ display: "block", fontSize: 13 }}>Active Sessions</strong>
                  <span className="panel-sub" style={{ fontSize: 12 }}>
                    {sessionCount !== null
                      ? `${plural(sessionCount, "Active Session")} On This Account.`
                      : sessionError
                        ? "Could Not Load Sessions."
                        : "Checking Sessions…"}
                  </span>
                </div>
                {sessionCount !== null ? (
                  <LoadingButton type="button" className="btn-outline" loading={op === "revoke"} loadingLabel="Signing Out…" spinnerClass="spinner dark" disabled={op !== null} onClick={() => void signOut()}>
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
              {sessionStatus ? (
                <p className="panel-sub" role="status" style={{ margin: "4px 0 0", fontSize: 12 }}>
                  {sessionStatus}
                </p>
              ) : null}
            </Panel>
            <Panel title="Notifications">
              <Toggle label="Email Reports" body="Receive Reports And Insights By Email."
                checked={notif.emailReports} onChange={(v) => setNotifPref({ emailReports: v })} />
              <Toggle label="Product Updates" body="Get Updates On New Features."
                checked={notif.productUpdates} onChange={(v) => setNotifPref({ productUpdates: v })} />
              {notifStatus ? (
                <p className="panel-sub" role="status" style={{ margin: "8px 0 0", fontSize: 12 }}>
                  {notifStatus}
                </p>
              ) : null}
            </Panel>
            <Panel title="Recent Activity" sub="Latest account events.">
              {activity.every((a) => a.value === "—") ? (
                <EmptyState text="No recent activity yet." />
              ) : (
                <div>
                  {activity.map((a) => (
                    <div className="insight" key={a.label}>
                      <span className="insight-ico" style={{ background: "var(--shell-bg)" }}>
                        <Icon name={a.icon} size={18} />
                      </span>
                      <div>
                        <h4>{a.label}</h4>
                        <p>{a.value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
