import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { DemoPackPanel } from "./DemoPackPanel";
import { EmployeeAvatar, EmptyState, PageHeader, Panel, Skeleton, plural, titleCase } from "@/components/product";

/** Admin employee management (port of legacy Web/Index.html v-admin).
 *
 * Same endpoints, params, and user-visible copy as the legacy view:
 * GET /api/admin/employees?search=&filter=, POST /api/admin/employees,
 * POST /api/admin/employees/{id}/{approve|suspend|reactivate|revoke|role},
 * POST /api/admin/employees/{id}/sessions/revoke,
 * GET /api/admin/audit?limit=20.
 *
 * Teams are read from GET /api/campaigns/meta (distinct campaign team
 * names with campaign counts). The backend stores no per-employee team
 * and exposes no team-mutation endpoint, so the Team column honestly
 * shows "—" and browser-local custom teams are labelled "Local".
 */

interface AdminEmployee {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url: string;
  role: string;
  status: string;
  approved_at: string;
  approved_by: string;
  last_login_at: string;
}

interface AdminAuditEvent {
  id: string;
  target_id: string;
  admin_id: string;
  action: string;
  prev_value: string;
  new_value: string;
  created_at: string;
}

interface CampaignMeta {
  name: string;
  client: string;
  team: string;
}

const REVOKE_CONFIRM =
  "Revoke This Employee's Access? Their Sessions Stop Working Immediately.";
const SUSPEND_ADMIN_CONFIRM =
  "Suspend This Admin? Their Sessions Stop Working Immediately. The Server Refuses When They Are The Last Active Admin.";
const DEMOTE_ADMIN_CONFIRM =
  "Demote This Admin To Employee? They Lose Admin Access Immediately.";
const INVALIDATE_CONFIRM =
  "Invalidate All Sessions For This Employee? They Are Signed Out Everywhere Immediately.";

const LOCAL_TEAMS_KEY = "ci-local-teams";

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function displayName(e: AdminEmployee): string {
  const nm = `${e.first_name || ""} ${e.last_name || ""}`.trim();
  return nm || e.email;
}

/** Friendly date for admin surfaces: never a raw ISO string. Empty or
 *  unparseable input renders as "—", never invented. */
/** Audit action codes (EMPLOYEE_CREATED) render Title Cased for
 *  readability. Unknown codes render as-is — never hidden. */
export function auditAction(code: string): string {
  if (!code) return "—";
  return code.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(" ");
}

export function friendlyDate(raw: string): string {
  if (!raw) return "—";
  const d = new Date(raw.length <= 10 ? `${raw}T00:00:00` : raw);
  if (Number.isNaN(d.getTime())) return "—";
  const date = d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diffDays < 0) return date;
  if (diffDays === 0) return `Today · ${date}`;
  if (diffDays === 1) return `Yesterday · ${date}`;
  if (diffDays < 30) return `${diffDays}d ago · ${date}`;
  return date;
}

function loadLocalTeams(): string[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_TEAMS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((t): t is string => typeof t === "string") : [];
  } catch {
    return [];
  }
}

function applyLocalFilters(
  rows: AdminEmployee[],
  statusFilter: string,
  roleFilter: string,
): AdminEmployee[] {
  return rows.filter(
    (e) =>
      (!statusFilter || e.status === statusFilter) &&
      (!roleFilter || e.role === roleFilter),
  );
}

async function queryEmployees(
  searchText: string,
  filter: string,
): Promise<AdminEmployee[]> {
  const q = new URLSearchParams({
    search: searchText.trim(),
    filter,
  }).toString();
  const r = await api<{ employees?: AdminEmployee[] }>(
    "GET",
    `/api/admin/employees?${q}`,
  );
  return Array.isArray(r.employees) ? r.employees : [];
}

async function queryAudit(): Promise<AdminAuditEvent[]> {
  const r = await api<{ events?: AdminAuditEvent[] }>(
    "GET",
    "/api/admin/audit?limit=20",
  );
  return Array.isArray(r.events) ? r.events : [];
}

function toCsv(rows: Array<Record<string, string>>): string {
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  return rows.map((r) => Object.values(r).map(esc).join(",")).join("\n");
}

export function AdminEmployeesPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [employees, setEmployees] = useState<AdminEmployee[] | null>(null);
  const [events, setEvents] = useState<AdminAuditEvent[]>([]);
  const [teams, setTeams] = useState<Array<{ name: string; campaigns: number }> | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [addEmail, setAddEmail] = useState("");
  const [addFirst, setAddFirst] = useState("");
  const [addLast, setAddLast] = useState("");
  const [addRole, setAddRole] = useState("employee");
  const [teamOpen, setTeamOpen] = useState(false);
  const [teamName, setTeamName] = useState("");
  const [localTeams, setLocalTeams] = useState<string[]>(loadLocalTeams);
  /* One in-flight admin mutation at a time: every async action sets
   * its key so repeated clicks cannot double-submit while slow. */
  const [busyKey, setBusyKey] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [rows, evs, meta] = await Promise.all([
          queryEmployees(search, statusFilter || roleFilter || ""),
          queryAudit(),
          api<{ campaigns?: CampaignMeta[] } | null>("GET", "/api/campaigns/meta").catch(() => null),
        ]);
        if (!live) return;
        setEmployees(applyLocalFilters(rows, statusFilter, roleFilter));
        setEvents(evs);
        /* A failed team lookup stays null (no verified count), never a
         * silent zero: Teams (0) renders only for a resolved empty set. */
        if (meta === null) {
          setTeams(null);
        } else {
          const counts = new Map<string, number>();
          for (const c of meta.campaigns ?? []) {
            if (c.team) counts.set(c.team, (counts.get(c.team) ?? 0) + 1);
          }
          setTeams([...counts.entries()].map(([name, campaigns]) => ({ name, campaigns })).sort((a, b) => a.name.localeCompare(b.name)));
        }
        setNotice("");
      } catch (e) {
        if (!live) return;
        setNotice(msg(e));
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => {
      live = false;
    };
  }, [search, statusFilter, roleFilter]);

  async function reloadLists(): Promise<void> {
    const [rows, evs] = await Promise.all([
      queryEmployees(search, statusFilter || roleFilter || ""),
      queryAudit(),
    ]);
    setEmployees(applyLocalFilters(rows, statusFilter, roleFilter));
    setEvents(evs);
  }

  async function refreshAll(): Promise<void> {
    if (busyKey) return;
    setBusyKey("refresh");
    try {
      await reloadLists();
      setNotice("");
    } catch (e) {
      setNotice(msg(e));
    } finally {
      setBusyKey((cur) => (cur === "refresh" ? null : cur));
    }
  }

  async function runAction(
    act: string,
    id: string,
    targetRole: string,
    newRole: string,
  ): Promise<void> {
    if (act === "revoke" && !window.confirm(REVOKE_CONFIRM)) return;
    if (act === "suspend" && targetRole === "admin" && !window.confirm(SUSPEND_ADMIN_CONFIRM))
      return;
    if (
      act === "role" &&
      newRole === "employee" &&
      targetRole === "admin" &&
      !window.confirm(DEMOTE_ADMIN_CONFIRM)
    )
      return;
    const key = `${act}:${id}`;
    if (busyKey) return;
    setBusyKey(key);
    try {
      if (act === "role") {
        await api(
          "POST",
          `/api/admin/employees/${encodeURIComponent(id)}/role`,
          { role: newRole },
        );
      } else {
        await api(
          "POST",
          `/api/admin/employees/${encodeURIComponent(id)}/${act}`,
          {},
        );
      }
      await reloadLists();
      setNotice("");
    } catch (e) {
      setNotice(msg(e));
    } finally {
      setBusyKey((cur) => (cur === key ? null : cur));
    }
  }

  async function invalidateSessions(id: string): Promise<void> {
    if (!window.confirm(INVALIDATE_CONFIRM)) return;
    const key = `invalidate:${id}`;
    if (busyKey) return;
    setBusyKey(key);
    try {
      const r = await api<{ revoked: number }>(
        "POST",
        `/api/admin/employees/${encodeURIComponent(id)}/sessions/revoke`,
        {},
      );
      await reloadLists();
      setNotice(`${Number(r.revoked) || 0} Session(s) Revoked.`);
    } catch (e) {
      setNotice(msg(e));
    } finally {
      setBusyKey((cur) => (cur === key ? null : cur));
    }
  }

  /* Direct creation, honestly named: the backend pre-adds staff as
   *  Active (admin_create) — no invitation email exists. The dialog
   *  says "Add Employee", never "Invite". */
  async function addEmployee(): Promise<void> {
    if (busyKey) return;
    setBusyKey("add");
    try {
      await api("POST", "/api/admin/employees", {
        email: addEmail.trim(),
        first_name: addFirst.trim(),
        last_name: addLast.trim(),
        role: addRole,
      });
      setAddEmail("");
      setAddFirst("");
      setAddLast("");
      setInviteOpen(false);
      await reloadLists();
      setNotice("Employee Added As Active.");
    } catch (e) {
      setNotice(msg(e));
    } finally {
      setBusyKey((cur) => (cur === "add" ? null : cur));
    }
  }

  function exportAccessReport(): void {
    const rows = employees ?? [];
    const stamp = new Date().toISOString().slice(0, 10);
    const empCsv = toCsv([
      { Employee: "Employee", Email: "Email", Role: "Role", Status: "Status", LastActive: "Last Active" },
      ...rows.map((e) => ({
        Employee: displayName(e),
        Email: e.email,
        Role: e.role,
        Status: e.status,
        LastActive: e.last_login_at || "",
      })),
    ]);
    const auditCsv = toCsv([
      { When: "When", Action: "Action", Target: "Target", Admin: "Admin", Change: "Change" },
      ...events.map((v) => ({
        When: v.created_at,
        Action: v.action,
        Target: v.target_id,
        Admin: v.admin_id,
        Change: `${v.prev_value} → ${v.new_value}`,
      })),
    ]);
    const blob = new Blob(
      [`Employees (${stamp})\n${empCsv}\n\nAudit Trail (${stamp})\n${auditCsv}\n`],
      { type: "text/csv" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `access-report-${stamp}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    setNotice("Access Report Exported.");
  }

  function createTeam(): void {
    const name = teamName.trim();
    if (!name) return;
    const next = [...localTeams.filter((t) => t.toLowerCase() !== name.toLowerCase()), name];
    setLocalTeams(next);
    try {
      window.localStorage.setItem(LOCAL_TEAMS_KEY, JSON.stringify(next));
    } catch {
      /* private mode: browser-local teams are best-effort only */
    }
    setTeamName("");
    setTeamOpen(false);
    setNotice(`Team “${name}” Saved In This Browser.`);
  }

  const stats = useMemo(() => {
    const rows = employees ?? [];
    const total = rows.length;
    const pct = (n: number) => (total ? `${Math.round((n / total) * 100)}% of Employees` : "No Employees Yet");
    const active = rows.filter((e) => e.status === "active").length;
    const pending = rows.filter((e) => e.status === "pending").length;
    const admins = rows.filter((e) => e.role === "admin").length;
    return [
      { label: "Total Employees", value: String(total), icon: "users", tint: "#E7F1FB", trend: total ? `${plural(rows.filter((e) => e.role !== "admin").length, "Employee")} · ${plural(admins, "Admin")}` : "No Employees Yet" },
      { label: "Active Users", value: String(active), icon: "check", tint: "#E5F5EC", trend: pct(active) },
      /* "Pending Approvals", not "Pending Invites": no invitation
       *  email exists — pending rows await an approval decision. */
      { label: "Pending Approvals", value: String(pending), icon: "clock", tint: "#FBF3E2", trend: pending ? "Awaiting Approval" : "Inbox Zero" },
      { label: "Admins", value: String(admins), icon: "lock", tint: "#EFEAFB", trend: pct(admins) },
    ];
  }, [employees]);

  const adminCount = stats[3].value;
  const employeeCount = String((employees ?? []).filter((e) => e.role !== "admin").length);
  /* Audit-trail identity cells: a target/admin id that matches a loaded
   * employee renders THAT employee's avatar + name (authorised data
   * already fetched); unknown ids keep the honest truncated-id form. */
  const employeeById = useMemo(() => {
    const map = new Map<string, AdminEmployee>();
    for (const e of employees ?? []) map.set(e.id, e);
    return map;
  }, [employees]);
  const identityCell = (id: string) => {
    const match = employeeById.get(id || "");
    if (!match) return <>{(id || "").slice(0, 8)}</>;
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
        <EmployeeAvatar
          url={match.avatar_url || ""}
          name={displayName(match)}
          email={match.email || ""}
          size={24}
        />
        <span className="cell-main">{displayName(match)}</span>
      </span>
    );
  };
  const allTeams = useMemo(() => {
    const real = (teams ?? []).map((t) => ({ ...t, local: false }));
    const have = new Set(real.map((t) => t.name.toLowerCase()));
    const local = localTeams.filter((t) => !have.has(t.toLowerCase()))
      .map((name) => ({ name, campaigns: 0, local: true }));
    return [...real, ...local];
  }, [teams, localTeams]);

  return (
    <>
      <PageHeader
        title="Admin"
        sub="Access is decided here, on the server. Changes take effect immediately, including on live sessions."
        actions={(
          <>
            <button type="button" className="btn-outline" onClick={exportAccessReport}>
              <Icon name="download" size={14} /> Export Access Report
            </button>
            <button type="button" className="btn-outline" onClick={() => setTeamOpen(true)}>
              <Icon name="plus" size={14} /> Create Team
            </button>
            <button type="button" className="btn-primary" onClick={() => setInviteOpen(true)}>
              <Icon name="plus" size={14} /> Add Employee
            </button>
          </>
        )}
      />
      <div className="kpi-grid" style={{ marginTop: 0 }}>
        {stats.map((s) => (
          <div className="kpi-card" key={s.label}>
            <span className="kpi-ico" style={{ background: s.tint }}>
              <Icon name={s.icon} size={20} />
            </span>
            <div className="kpi-body">
              <div className="kpi-label">{s.label}</div>
              <div className="kpi-value">{employees === null ? "—" : s.value}</div>
              <div className="kpi-label" style={{ textTransform: "none", letterSpacing: 0 }}>
                {employees === null ? "Loading…" : s.trend}
              </div>
            </div>
          </div>
        ))}
      </div>

      <Panel title="Employee Access" sub="Search, approve, suspend, revoke, and change roles.">
        <div className="rep-filters" style={{ marginBottom: 12 }}>
          <span className="rep-search admin-search">
            <Icon name="search" size={15} />
            <input
              type="text"
              id="admin-search"
              placeholder="Search name or email"
              aria-label="Search Name Or Email"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </span>
          <select
            id="admin-status-filter"
            aria-label="Filter By Status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="revoked">Revoked</option>
          </select>
          <select
            id="admin-role-filter"
            aria-label="Filter By Role"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">All Roles</option>
            <option value="admin">Admin</option>
            <option value="employee">Employee</option>
          </select>
          <button type="button" className="btn-outline" disabled={busyKey !== null} onClick={() => void refreshAll()}>
            <Icon name="reset" size={14} /> Refresh
          </button>
          {notice !== "" && (
            <span className="panel-sub" role="status" style={{ margin: 0 }}>
              {notice}
            </span>
          )}
        </div>
        {loading && employees === null && notice === "" ? (
          <>
            <p className="muted">Loading Employees…</p>
            <Skeleton height={180} />
          </>
        ) : employees !== null && (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Team</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last Active</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {employees.length === 0 ? (
                  <tr>
                    <td colSpan={7}>No Employees Match.</td>
                  </tr>
                ) : (
                  employees.map((e) => {
                    const nextRole =
                      e.role === "admin" ? "employee" : "admin";
                    return (
                      <tr key={e.id}>
                        <td>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
                            <EmployeeAvatar
                              url={e.avatar_url || ""}
                              name={displayName(e)}
                              email={e.email || ""}
                            />
                            <span className="cell-main">{displayName(e)}</span>
                          </span>
                        </td>
                        <td>{e.email}</td>
                        <td>
                          <span className={e.role === "admin" ? "pill pill-info" : "chip-static"}>
                            {titleCase(e.role)}
                          </span>
                        </td>
                        <td title="The backend stores no per-employee team">—</td>
                        <td>
                          <span className={
                            e.status === "active" ? "pill pill-ok"
                            : e.status === "pending" ? "pill pill-info"
                            : e.status === "revoked" ? "pill pill-bad" : "chip-static"
                          }>
                            {titleCase(e.status)}
                          </span>
                        </td>
                        <td>{e.last_login_at ? friendlyDate(e.last_login_at) : "Never Signed In"}</td>
                        <td>
                          <span className="row-actions">
                            {e.status === "pending" && (
                              <button
                                type="button"
                                className="link-teal"
                                disabled={busyKey !== null}
                                onClick={() =>
                                  void runAction("approve", e.id, e.role, "")
                                }
                              >
                                Approve
                              </button>
                            )}
                            {e.status === "active" && (
                              <button
                                type="button"
                                className="link-teal"
                                disabled={busyKey !== null}
                                onClick={() =>
                                  void runAction("suspend", e.id, e.role, "")
                                }
                              >
                                Suspend
                              </button>
                            )}
                            {e.status === "suspended" && (
                              <button
                                type="button"
                                className="link-teal"
                                disabled={busyKey !== null}
                                onClick={() =>
                                  void runAction(
                                    "reactivate",
                                    e.id,
                                    e.role,
                                    "",
                                  )
                                }
                              >
                                Reactivate
                              </button>
                            )}
                            <details className="row-menu">
                              {/* role=button: some AT/summary mappings omit the
                                  disclosure role, and tests drive this control. */}
                              <summary role="button" aria-label={`More Actions For ${e.email}`} title="More Actions">
                                <Icon name="dots" size={16} />
                              </summary>
                              <div className="row-menu-pop" role="menu">
                                {e.status !== "revoked" && (
                                  <button
                                    type="button"
                                    disabled={busyKey !== null}
                                    onClick={(ev) => {
                                      ev.currentTarget.closest("details")?.removeAttribute("open");
                                      void runAction("revoke", e.id, e.role, "");
                                    }}
                                  >
                                    Revoke
                                  </button>
                                )}
                                <button
                                  type="button"
                                  disabled={busyKey !== null}
                                  onClick={(ev) => {
                                    ev.currentTarget.closest("details")?.removeAttribute("open");
                                    void runAction("role", e.id, e.role, nextRole);
                                  }}
                                >
                                  Make {nextRole === "admin" ? "Admin" : "Employee"}
                                </button>
                                <button
                                  type="button"
                                  disabled={busyKey !== null}
                                  onClick={(ev) => {
                                    ev.currentTarget.closest("details")?.removeAttribute("open");
                                    void invalidateSessions(e.id);
                                  }}
                                >
                                  Invalidate Sessions
                                </button>
                              </div>
                            </details>
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="section-gap" />
      <div className="cols-2">
        <Panel title="Teams & Permissions" sub="Who can do what in this workspace.">
          <div>
            <div className="insight">
              <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                <Icon name="lock" size={18} />
              </span>
              <div>
                <h4>Admins{employees !== null ? ` (${adminCount})` : ""}</h4>
                <p>Approve, suspend, revoke, and re-activate employees; change roles; invalidate sessions; read the audit trail.</p>
              </div>
            </div>
            {/* Teams count row (§8): server-authoritative team names
              only — browser-local labels are details below, never the
              shared count. Zero shows Teams (0); an unresolved lookup
              shows no count rather than a fabricated zero. */}
            <div className="insight">
              <span className="insight-ico" style={{ background: "var(--shell-green-soft)" }}>
                <Icon name="users" size={18} />
              </span>
              <div>
                <h4>Teams{teams !== null ? ` (${teams.length})` : ""}</h4>
                <p>{teams === null
                  ? "Loading teams…"
                  : teams.length === 0
                    ? "None yet — teams appear when campaigns carry a team name."
                    : `${plural(teams.length, "Team")} named in the current dataset.`}</p>
              </div>
            </div>
            <div className="insight">
              <span className="insight-ico" style={{ background: "var(--shell-teal-soft)" }}>
                <Icon name="user" size={18} />
              </span>
              <div>
                <h4>Employees{employees !== null ? ` (${employeeCount})` : ""}</h4>
                <p>Full product access — dashboards, campaigns, creatives, reports, Ask The Data, and AI Analyst — without admin controls.</p>
              </div>
            </div>
            {allTeams.map((t) => (
              <div className="insight" key={t.name}>
                <span className="insight-ico" style={{ background: "var(--shell-green-soft)" }}>
                  <Icon name="users" size={18} />
                </span>
                <div style={{ flex: 1 }}>
                  <h4>{t.name}</h4>
                  <p>{t.campaigns === 1 ? "1 campaign" : `${t.campaigns} campaigns`} in the current dataset{t.local ? " · saved in this browser only" : ""}.</p>
                </div>
                {t.local ? <span className="badge-demo">Local</span> : null}
              </div>
            ))}
            {teams === null ? <Skeleton height={60} /> : null}
          </div>
        </Panel>
        <Panel title="Access Rules" sub="Rules the server enforces on every change.">
          <ul className="tips-list">
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-green-soft)" }}>
                <Icon name="check" size={18} />
              </span>
              <div>
                <h4>Admin Gate</h4>
                <p>Only admins can open this page, and every admin API call is re-authorized on the server.</p>
              </div>
            </li>
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                <Icon name="clock" size={18} />
              </span>
              <div>
                <h4>Immediate Effect</h4>
                <p>Approve, suspend, revoke, and session invalidation apply instantly — including on live sessions.</p>
              </div>
            </li>
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-amber-soft)" }}>
                <Icon name="lock" size={18} />
              </span>
              <div>
                <h4>Last-Admin Protection</h4>
                <p>Suspending the last active admin is refused by the server, so the workspace can never lock itself out.</p>
              </div>
            </li>
          </ul>
        </Panel>
      </div>

      <div className="section-gap" />
      <Panel
        title="Workspace Activity"
        sub="Every access decision, newest first."
      >
        <h3 style={{ margin: "0 0 10px", fontSize: 13.5, fontWeight: 700 }}>Audit Trail</h3>
        {events.length === 0 ? (
          <EmptyState text="No Events Yet." />
        ) : (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Action</th>
                  <th scope="col">Target</th>
                  <th scope="col">Admin</th>
                  <th scope="col">Change</th>
                </tr>
              </thead>
              <tbody>
                {events.map((v) => (
                  <tr key={v.id}>
                    <td>{friendlyDate(v.created_at)}</td>
                    <td className="cell-main">{auditAction(v.action)}</td>
                    <td>{identityCell(v.target_id)}</td>
                    <td>{identityCell(v.admin_id)}</td>
                    <td>
                      {v.prev_value} → {v.new_value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Advanced Demo Tools (§8): directly below Workspace Activity in
        normal flow — same column, same width, disclosure unchanged. */}
      <div className="section-gap" />
      <details className="adv-disclosure">
        <summary>
          <span className="adv-title">Advanced · Demo Tools</span>
          <span className="panel-sub">Synthetic dataset controls for demo environments — not production access management.</span>
        </summary>
        <div style={{ marginTop: 10 }}>
          <DemoPackPanel />
        </div>
      </details>

      {inviteOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add Employee"
          onClick={() => setInviteOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 80, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
        >
          <div
            className="panel"
            onClick={(e) => e.stopPropagation()}
            style={{ width: "100%", maxWidth: 460, margin: 0 }}
          >
            <div className="panel-head">
              <div>
                <h2 className="panel-title">Add Employee</h2>
                <p className="panel-sub">New employees join as Active immediately — no invitation email is sent.</p>
              </div>
              <button type="button" className="link-teal" onClick={() => setInviteOpen(false)}>
                Close
              </button>
            </div>
            <div className="rep-filters" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <input
                type="text"
                placeholder="email"
                aria-label="New Employee Email"
                value={addEmail}
                onChange={(e) => setAddEmail(e.target.value)}
              />
              <input
                type="text"
                placeholder="First Name (Optional)"
                aria-label="New Employee First Name"
                value={addFirst}
                onChange={(e) => setAddFirst(e.target.value)}
              />
              <input
                type="text"
                placeholder="last name (optional)"
                aria-label="New Employee Last Name"
                value={addLast}
                onChange={(e) => setAddLast(e.target.value)}
              />
              <select
                aria-label="New Employee Role"
                value={addRole}
                onChange={(e) => setAddRole(e.target.value)}
              >
                <option value="employee">Employee</option>
                <option value="admin">Admin</option>
              </select>
              <LoadingButton type="button" className="btn-primary"
                loading={busyKey === "add"} loadingLabel="Adding…"
                disabled={busyKey !== null} onClick={() => void addEmployee()}>
                <Icon name="plus" size={14} /> Add (Active)
              </LoadingButton>
            </div>
          </div>
        </div>
      ) : null}

      {teamOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Create Team"
          onClick={() => setTeamOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 80, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
        >
          <div
            className="panel"
            onClick={(e) => e.stopPropagation()}
            style={{ width: "100%", maxWidth: 420, margin: 0 }}
          >
            <div className="panel-head">
              <div>
                <h2 className="panel-title">Create Team</h2>
                <p className="panel-sub">Saved in this browser only — workspace teams come from campaign data.</p>
              </div>
              <button type="button" className="link-teal" onClick={() => setTeamOpen(false)}>
                Close
              </button>
            </div>
            <div className="field">
              <label htmlFor="new-team-name">Team Name</label>
              <input
                id="new-team-name"
                type="text"
                placeholder="e.g. Growth"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") createTeam(); }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
              <button type="button" className="btn-outline" onClick={() => setTeamOpen(false)}>
                Cancel
              </button>
              <button type="button" className="btn-primary" disabled={!teamName.trim()} onClick={createTeam}>
                Create Team
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
