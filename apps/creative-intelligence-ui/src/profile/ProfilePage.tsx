import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
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
    if (!employee) return;
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
    }
  };

  const removeAvatar = async () => {
    if (!employee) return;
    setStatus("");
    try {
      const r = await api<ProfileResponse>("PATCH", "/api/auth/me", { avatar_url: "" });
      applyEmployee(r.employee);
      setStatus("Avatar Removed.");
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  };

  const revokeAll = async () => {
    setSessionStatus("");
    try {
      const r = await api<RevokeResponse>("POST", "/api/auth/sessions/revoke-all", {});
      setSessionStatus(`Signed Out Of ${Number(r.revoked ?? 0)} Session(s).`);
    } catch (e: unknown) {
      setSessionStatus(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <>
      <h1 className="page-title">Profile</h1>
      <p className="page-sub">Your Employee Profile. Changes Are Saved To Your Account Immediately.</p>
      {loading && <p className="muted">Loading Profile…</p>}
      {!loading && loadError && <p className="muted">{loadError}</p>}
      {!loading && !loadError && !employee && <p className="muted">Signed Out.</p>}
      {!loading && !loadError && employee && (
        <>
          <div className="card">
            <h3>Profile</h3>
            <div className="acct-row">
              <span>
                <ProfileAvatar employee={employee} />
              </span>
              <div>
                <strong>{displayName(employee)}</strong>
                <br />
                <span className="muted">{employee.email}</span>
                <br />
                <span className="muted">
                  {employee.role} · {employee.status}
                </span>
              </div>
            </div>
            <div style={{ margin: "12px 0" }}>
              <label>
                First Name
                <input
                  type="text"
                  value={first}
                  onChange={(e) => setFirst(e.target.value)}
                  style={{ width: 200 }}
                />
              </label>
              <label>
                Last Name
                <input
                  type="text"
                  value={last}
                  onChange={(e) => setLast(e.target.value)}
                  style={{ width: 200 }}
                />
              </label>
            </div>
            <div style={{ margin: "12px 0" }}>
              <label>
                Avatar URL (Optional)
                <input
                  type="text"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="avatar image link or blank"
                  style={{ width: 320 }}
                />
              </label>
              <span className="muted" style={{ fontSize: 12 }}>
                …Or Upload An Image (JPEG/PNG/WebP, Up To 2 MB):
              </span>
              <input
                ref={fileRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                aria-label="Avatar Image File"
              />
            </div>
            <div>
              <button type="button" className="action" onClick={() => void save()}>
                Save Profile
              </button>
              <button type="button" className="action" onClick={() => void removeAvatar()}>
                Remove Avatar
              </button>
              <span className="muted" role="status">
                {status}
              </span>
            </div>
          </div>
          <div className="card">
            <h3>Sessions</h3>
            <div>
              <button type="button" className="action" onClick={() => void revokeAll()}>
                Log Out Everywhere
              </button>
              <span className="muted" role="status">
                {sessionStatus}
              </span>
            </div>
          </div>
        </>
      )}
    </>
  );
}
