import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { EmptyState, PageHeader, Panel, Skeleton } from "@/components/product";

/** Admin employee management (port of legacy Web/Index.html v-admin).
 *
 * Same endpoints, params, and user-visible copy as the legacy view:
 * GET /api/admin/employees?search=&filter=, POST /api/admin/employees,
 * POST /api/admin/employees/{id}/{approve|suspend|reactivate|revoke|role},
 * POST /api/admin/employees/{id}/sessions/revoke,
 * GET /api/admin/audit?limit=20.
 */

interface AdminEmployee {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
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

const REVOKE_CONFIRM =
  "Revoke This Employee's Access? Their Sessions Stop Working Immediately.";
const SUSPEND_ADMIN_CONFIRM =
  "Suspend This Admin? Their Sessions Stop Working Immediately. The Server Refuses When They Are The Last Active Admin.";
const DEMOTE_ADMIN_CONFIRM =
  "Demote This Admin To Employee? They Lose Admin Access Immediately.";
const INVALIDATE_CONFIRM =
  "Invalidate All Sessions For This Employee? They Are Signed Out Everywhere Immediately.";

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function displayName(e: AdminEmployee): string {
  const nm = `${e.first_name || ""} ${e.last_name || ""}`.trim();
  return nm || e.email;
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

export function AdminEmployeesPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [employees, setEmployees] = useState<AdminEmployee[] | null>(null);
  const [events, setEvents] = useState<AdminAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [addEmail, setAddEmail] = useState("");
  const [addFirst, setAddFirst] = useState("");
  const [addLast, setAddLast] = useState("");
  const [addRole, setAddRole] = useState("employee");
  const [seedBusy, setSeedBusy] = useState(false);
  const [seedResult, setSeedResult] = useState("");

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [rows, evs] = await Promise.all([
          queryEmployees(search, statusFilter || roleFilter || ""),
          queryAudit(),
        ]);
        if (!live) return;
        setEmployees(applyLocalFilters(rows, statusFilter, roleFilter));
        setEvents(evs);
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
    try {
      await reloadLists();
      setNotice("");
    } catch (e) {
      setNotice(msg(e));
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
    }
  }

  async function invalidateSessions(id: string): Promise<void> {
    if (!window.confirm(INVALIDATE_CONFIRM)) return;
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
    }
  }

  async function seedDemo(): Promise<void> {
    setSeedBusy(true);
    setSeedResult("");
    try {
      const r = await api<{ ok: boolean; inserted: number; campaigns: number; creatives: number }>(
        "POST", "/api/admin/demo/seed", {});
      setSeedResult(
        r.inserted > 0
          ? `Seeded ${r.inserted} Row(s): ${r.campaigns} Campaign(s), ${r.creatives} Creative(s).`
          : `Already Populated: ${r.campaigns} Campaign(s), ${r.creatives} Creative(s). Nothing Duplicated.`);
    } catch (e) {
      setSeedResult(msg(e));
    } finally {
      setSeedBusy(false);
    }
  }

  async function addEmployee(): Promise<void> {
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
      await reloadLists();
      setNotice("Employee Added As Active.");
    } catch (e) {
      setNotice(msg(e));
    }
  }

  const stats = useMemo(() => {
    const rows = employees ?? [];
    return [
      { label: "Total Employees", value: String(rows.length), icon: "users", tint: "#E7F1FB" },
      { label: "Active", value: String(rows.filter((e) => e.status === "active").length), icon: "check", tint: "#E5F5EC" },
      { label: "Pending Approval", value: String(rows.filter((e) => e.status === "pending").length), icon: "clock", tint: "#FBF3E2" },
      { label: "Admins", value: String(rows.filter((e) => e.role === "admin").length), icon: "lock", tint: "#EFEAFB" },
    ];
  }, [employees]);

  const adminCount = stats[3].value;
  const employeeCount = String((employees ?? []).filter((e) => e.role !== "admin").length);

  return (
    <>
      <PageHeader
        title="Admin"
        sub="Access is decided here, on the server. Changes take effect immediately, including on live sessions."
      />
      <div className="kpi-grid" style={{ marginTop: 0 }}>
        {stats.map((s) => (
          <div className="kpi-card" key={s.label}>
            <span className="kpi-ico" style={{ background: s.tint }}>
              <Icon name={s.icon} size={22} />
            </span>
            <div className="kpi-body">
              <div className="kpi-label">{s.label}</div>
              <div className="kpi-value">{employees === null ? "—" : s.value}</div>
            </div>
          </div>
        ))}
      </div>

      <Panel title="Employee Access" sub="Search, approve, suspend, revoke, and change roles.">
        <div className="rep-filters" style={{ marginBottom: 12 }}>
          <span className="rep-search">
            <Icon name="search" size={15} />
            <input
              type="text"
              id="admin-search"
              placeholder="search name or email"
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
          <button type="button" className="btn-outline" onClick={() => void refreshAll()}>
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
                  <th scope="col">Employee</th>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last Login</th>
                  <th scope="col">Approval</th>
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
                    const initials = displayName(e).split(/\s+/)
                      .map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "•";
                    return (
                      <tr key={e.id}>
                        <td>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
                            <span className="avatar" aria-hidden="true">{initials}</span>
                            <span className="cell-main">{displayName(e)}</span>
                          </span>
                        </td>
                        <td>{e.email}</td>
                        <td>
                          <span className={e.role === "admin" ? "pill pill-info" : "chip-static"}>
                            {e.role}
                          </span>
                        </td>
                        <td>
                          <span className={
                            e.status === "active" ? "pill pill-ok"
                            : e.status === "pending" ? "pill pill-info"
                            : e.status === "revoked" ? "pill pill-bad" : "chip-static"
                          }>
                            {e.status}
                          </span>
                        </td>
                        <td>{e.last_login_at || "—"}</td>
                        <td>
                          {e.approved_at || "—"}
                          {e.approved_by
                            ? ` by ${e.approved_by.slice(0, 8)}`
                            : ""}
                        </td>
                        <td>
                          <span className="row-actions" style={{ flexWrap: "wrap", gap: 4, rowGap: 8, columnGap: 12 }}>
                            {e.status === "pending" && (
                              <button
                                type="button"
                                className="link-teal"
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
                            {e.status !== "revoked" && (
                              <button
                                type="button"
                                className="link-teal"
                                onClick={() =>
                                  void runAction("revoke", e.id, e.role, "")
                                }
                              >
                                Revoke
                              </button>
                            )}
                            <button
                              type="button"
                              className="link-teal"
                              onClick={() =>
                                void runAction("role", e.id, e.role, nextRole)
                              }
                            >
                              Make {nextRole === "admin" ? "Admin" : "Employee"}
                            </button>
                            <button
                              type="button"
                              className="link-teal"
                              onClick={() => void invalidateSessions(e.id)}
                            >
                              Invalidate Sessions
                            </button>
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
      <Panel title="Add Employee" sub="New employees join as Active immediately.">
        <div className="rep-filters">
          <input
            type="text"
            placeholder="email"
            aria-label="New Employee Email"
            value={addEmail}
            onChange={(e) => setAddEmail(e.target.value)}
            style={{ minWidth: 200 }}
          />
          <input
            type="text"
            placeholder="first name (optional)"
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
          <button type="button" className="btn-primary" onClick={() => void addEmployee()}>
            <Icon name="plus" size={14} /> Add (Active)
          </button>
        </div>
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
            <div className="insight">
              <span className="insight-ico" style={{ background: "var(--shell-teal-soft)" }}>
                <Icon name="user" size={18} />
              </span>
              <div>
                <h4>Employees{employees !== null ? ` (${employeeCount})` : ""}</h4>
                <p>Full product access — dashboards, campaigns, creatives, reports, Ask The Data, and AI Analyst — without admin controls.</p>
              </div>
            </div>
          </div>
        </Panel>
        <Panel title="Access Rules & Permission Groups" sub="Rules the server enforces on every change.">
          <ul className="tips-list">
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-green-soft)" }}>
                <Icon name="check" size={18} />
              </span>
              <div>
                <h4>Admin gate</h4>
                <p>Only admins can open this page, and every admin API call is re-authorized on the server.</p>
              </div>
            </li>
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-amber-soft)" }}>
                <Icon name="lock" size={18} />
              </span>
              <div>
                <h4>Last-admin protection</h4>
                <p>Suspending the last active admin is refused by the server, so the workspace can never lock itself out.</p>
              </div>
            </li>
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                <Icon name="clock" size={18} />
              </span>
              <div>
                <h4>Immediate effect</h4>
                <p>Approve, suspend, revoke, and session invalidation apply instantly — including on live sessions.</p>
              </div>
            </li>
          </ul>
        </Panel>
      </div>

      <div className="section-gap" />
      <Panel
        title="Demo Dataset"
        sub="Populate the ten synthetic campaigns and creatives. Upserts only: existing rows are never duplicated or deleted."
      >
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <LoadingButton type="button" className="btn-outline" loading={seedBusy}
            loadingLabel="Seeding…" spinnerClass="spinner dark" disabled={seedBusy}
            onClick={() => void seedDemo()}>
            <Icon name="download" size={15} /> Seed Demo Data
          </LoadingButton>
          {seedResult ? <span className="panel-sub" role="status" style={{ margin: 0 }}>{seedResult}</span> : null}
        </div>
      </Panel>

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
                    <td>{v.created_at}</td>
                    <td className="cell-main">{v.action}</td>
                    <td>{(v.target_id || "").slice(0, 8)}</td>
                    <td>{(v.admin_id || "").slice(0, 8)}</td>
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
    </>
  );
}
