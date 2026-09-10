import { useEffect, useState } from "react";
import { api } from "@/api/client";

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
  "Revoke this employee's access? Their sessions stop working immediately.";
const SUSPEND_ADMIN_CONFIRM =
  "Suspend this admin? Their sessions stop working immediately. The server refuses when they are the last active admin.";
const DEMOTE_ADMIN_CONFIRM =
  "Demote this admin to employee? They lose admin access immediately.";
const INVALIDATE_CONFIRM =
  "Invalidate all sessions for this employee? They are signed out everywhere immediately.";

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
      setNotice(`${Number(r.revoked) || 0} session(s) revoked.`);
    } catch (e) {
      setNotice(msg(e));
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
      setNotice("Employee added as active.");
    } catch (e) {
      setNotice(msg(e));
    }
  }

  return (
    <>
      <h1 className="page-title">Admin — Employees</h1>
      <p className="page-sub">
        Access is decided here, on the server. Changes take effect immediately,
        including on live sessions.
      </p>
      <div className="card">
        <div style={{ margin: "12px 0" }}>
          <input
            type="text"
            id="admin-search"
            placeholder="search name or email"
            aria-label="Search name or email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 220 }}
          />
          <select
            id="admin-status-filter"
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">all</option>
            <option value="pending">pending</option>
            <option value="active">active</option>
            <option value="suspended">suspended</option>
            <option value="revoked">revoked</option>
          </select>
          <select
            id="admin-role-filter"
            aria-label="Filter by role"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">all</option>
            <option value="admin">admin</option>
            <option value="employee">employee</option>
          </select>
          <button className="action" onClick={() => void refreshAll()}>
            Refresh
          </button>
          {notice !== "" && (
            <span className="muted" role="status">
              {notice}
            </span>
          )}
        </div>
        {loading && employees === null && notice === "" ? (
          <p className="muted">Loading employees…</p>
        ) : (
          employees !== null && (
            <div style={{ overflow: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Employee</th>
                    <th scope="col">Email</th>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                    <th scope="col">Last login</th>
                    <th scope="col">Approval</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.length === 0 ? (
                    <tr>
                      <td colSpan={7}>No employees match.</td>
                    </tr>
                  ) : (
                    employees.map((e) => {
                      const nextRole =
                        e.role === "admin" ? "employee" : "admin";
                      return (
                        <tr key={e.id}>
                          <td>{displayName(e)}</td>
                          <td>{e.email}</td>
                          <td>{e.role}</td>
                          <td>{e.status}</td>
                          <td>{e.last_login_at || "—"}</td>
                          <td>
                            {e.approved_at || "—"}
                            {e.approved_by
                              ? ` by ${e.approved_by.slice(0, 8)}`
                              : ""}
                          </td>
                          <td>
                            {e.status === "pending" && (
                              <>
                                <button
                                  className="link-btn"
                                  onClick={() =>
                                    void runAction("approve", e.id, e.role, "")
                                  }
                                >
                                  Approve
                                </button>{" "}
                              </>
                            )}
                            {e.status === "active" && (
                              <>
                                <button
                                  className="link-btn"
                                  onClick={() =>
                                    void runAction("suspend", e.id, e.role, "")
                                  }
                                >
                                  Suspend
                                </button>{" "}
                              </>
                            )}
                            {e.status === "suspended" && (
                              <>
                                <button
                                  className="link-btn"
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
                                </button>{" "}
                              </>
                            )}
                            {e.status !== "revoked" && (
                              <>
                                <button
                                  className="link-btn"
                                  onClick={() =>
                                    void runAction("revoke", e.id, e.role, "")
                                  }
                                >
                                  Revoke
                                </button>{" "}
                              </>
                            )}
                            <button
                              className="link-btn"
                              onClick={() =>
                                void runAction("role", e.id, e.role, nextRole)
                              }
                            >
                              Make {nextRole}
                            </button>{" "}
                            <button
                              className="link-btn"
                              onClick={() => void invalidateSessions(e.id)}
                            >
                              Invalidate sessions
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )
        )}
        <h4>Add employee</h4>
        <div>
          <input
            type="text"
            placeholder="email"
            aria-label="New employee email"
            value={addEmail}
            onChange={(e) => setAddEmail(e.target.value)}
            style={{ width: 220 }}
          />
          <input
            type="text"
            placeholder="first name (optional)"
            aria-label="New employee first name"
            value={addFirst}
            onChange={(e) => setAddFirst(e.target.value)}
            style={{ width: 150 }}
          />
          <input
            type="text"
            placeholder="last name (optional)"
            aria-label="New employee last name"
            value={addLast}
            onChange={(e) => setAddLast(e.target.value)}
            style={{ width: 150 }}
          />
          <select
            aria-label="New employee role"
            value={addRole}
            onChange={(e) => setAddRole(e.target.value)}
          >
            <option value="employee">Employee</option>
            <option value="admin">Admin</option>
          </select>
          <button className="action" onClick={() => void addEmployee()}>
            Add (active)
          </button>
        </div>
        <h4>Audit trail</h4>
        <div style={{ overflow: "auto" }}>
          <table>
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
              {events.length === 0 ? (
                <tr>
                  <td colSpan={5}>No events yet.</td>
                </tr>
              ) : (
                events.map((v) => (
                  <tr key={v.id}>
                    <td>{v.created_at}</td>
                    <td>{v.action}</td>
                    <td>{(v.target_id || "").slice(0, 8)}</td>
                    <td>{(v.admin_id || "").slice(0, 8)}</td>
                    <td>
                      {v.prev_value} → {v.new_value}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
