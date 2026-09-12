import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { EmptyState, PageHeader, Panel } from "@/components/product";
import { LoadingButton } from "@/components/LoadingButton";
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

/** Legacy avatar_html parity: provider avatar URL when set, else initials.
 *  Display logic only — a manual avatar is never overwritten on login
 *  (the server fills empty fields when linking, never clobbers). */
function ProfileAvatar({ employee }: { employee: PublicEmployee }) {
  const url = employee.avatar_url || "";
  if (url) {
    return (
      <img
        className="avatar"
        src={url}
        alt=""
        referrerPolicy="no-referrer"
        style={{ width: 64, height: 64 }}
      />
    );
  }
  const first = ((employee.first_name || "") || " ")[0] || "?";
  const last = ((employee.last_name || "") || " ")[0] || "";
  return (
    <span
      className="avatar"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        width: 64,
        height: 64,
      }}
    >
      {`${first}${last}`.trim() || "?"}
    </span>
  );
}

/** Employee profile (legacy Web/Index.html v-profile). Email is a verified
 *  identity and stays read-only; first/last name plus avatar URL save via
 *  PATCH /api/auth/me, manual image uploads go to POST /api/auth/me/avatar
 *  as multipart FormData, and removal clears via {avatar_url: ""}. */
export function ProfilePage() {
  const [employee, setEmployee] = useState<PublicEmployee | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [status, setStatus] = useState("");
  const [sessionStatus, setSessionStatus] = useState("");
  const [op, setOp] = useState<null | "save" | "avatar" | "revoke">(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

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
      setStatus("Avatar Removed.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setOp((cur) => (cur === "avatar" ? null : cur));
    }
  };

  const revokeAll = async () => {
    if (op !== null) return;
    setOp("revoke");
    setSessionStatus("");
    try {
      const r = await api<RevokeResponse>("POST", "/api/auth/sessions/revoke-all", {});
      setSessionStatus(`Signed Out Of ${Number(r.revoked ?? 0)} Session(s).`);
    } catch (e: unknown) {
      setSessionStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setOp((cur) => (cur === "revoke" ? null : cur));
    }
  };

  const activity = employee ? [
    { icon: "clock", label: "Last signed in", value: employee.last_login_at || "—" },
    { icon: "check", label: "Access approved", value: employee.approved_at || "—" },
    { icon: "user", label: "Account created", value: employee.created_at || "—" },
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
          <Panel title="Profile Card" sub="How you appear across the workspace.">
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <ProfileAvatar employee={employee} />
              <div>
                <p style={{ margin: 0, fontSize: 19, fontWeight: 800, color: "var(--shell-navy)" }}>
                  {displayName(employee)}
                </p>
                <p className="panel-sub" style={{ marginTop: 2 }}>{employee.email}</p>
                <p className="panel-sub" style={{ marginTop: 4 }}>
                  {`${employee.role} · ${employee.status}`}
                </p>
                {employee.provider ? (
                  <p className="panel-sub" style={{ marginTop: 2 }}>
                    Signed in via {employee.provider}
                  </p>
                ) : null}
              </div>
            </div>
          </Panel>

          <div className="section-gap" />
          <div className="cols-2">
            <Panel title="Personal Information" sub="Name and avatar for your account.">
              <div className="filter-grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 0 }}>
                <div className="field">
                  <label htmlFor="p-first">First Name</label>
                  <input
                    id="p-first"
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
              <div className="field" style={{ marginTop: 12 }}>
                <label htmlFor="p-avatar">Avatar URL (Optional)</label>
                <input
                  id="p-avatar"
                  type="text"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="avatar image link or blank"
                />
              </div>
              <p className="panel-sub" style={{ marginTop: 10 }}>
                …Or upload an image (JPEG/PNG/WebP, up to 2 MB):
              </p>
              <input
                ref={fileRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                aria-label="Avatar Image File"
              />
              <div className="chip-row" style={{ marginTop: 14 }}>
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
            <Panel title="Workspace Information" sub="Identity details managed by your admin.">
              <dl className="detail-list">
                <div>
                  <dt>Employee ID</dt>
                  <dd>{employee.id || "—"}</dd>
                </div>
                <div>
                  <dt>Work Email</dt>
                  <dd>{employee.email ? `${employee.email} (verified)` : "—"}</dd>
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
                  <dd>{employee.created_at || "—"}</dd>
                </div>
                <div>
                  <dt>Last Login</dt>
                  <dd>{employee.last_login_at || "—"}</dd>
                </div>
              </dl>
            </Panel>
          </div>

          <div className="section-gap" />
          <div className="cols-2">
            <Panel title="Connected Accounts" sub="Ways you can sign in.">
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
            <Panel title="Security" sub="Protect every session on every device.">
              <p className="panel-sub" style={{ marginTop: 0 }}>
                Signing out everywhere revokes all sessions immediately — you will need to sign in again on each device.
              </p>
              <div className="chip-row" style={{ marginTop: 12 }}>
                <LoadingButton type="button" className="btn-outline" loading={op === "revoke"} loadingLabel="Signing Out…" spinnerClass="spinner dark" disabled={op !== null} onClick={() => void revokeAll()}>
                  Log Out Everywhere
                </LoadingButton>
                <span className="panel-sub" role="status" style={{ margin: 0 }}>
                  {sessionStatus}
                </span>
              </div>
            </Panel>
          </div>

          <div className="section-gap" />
          <div className="cols-2">
            <Panel title="Notifications" sub="Choose what you want to be notified about.">
              <p className="panel-sub" style={{ marginTop: 0 }}>
                Email and in-app notification preferences live in Settings and apply to this account.
              </p>
              <div style={{ marginTop: 12 }}>
                <a className="btn-soft" href="/settings">Manage In Settings</a>
              </div>
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
