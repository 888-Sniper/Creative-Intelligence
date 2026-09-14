import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { DemoPackPanel } from "./DemoPackPanel";
import { EmployeeAvatar, EmptyState, OverflowMenu, PageHeader, Panel, Skeleton, codeLabel, titleCase } from "@/components/product";
import { useLocale } from "@/i18n";

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

/** Translated confirm copy lives on the locale (see useLocale below):
  *  window.confirm strings are interface chrome, not data. */

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

export function friendlyDate(
  raw: string,
  fmt?: (iso: string, opts?: Intl.DateTimeFormatOptions) => string,
  today = "Today",
  yesterday = "Yesterday",
  daysAgo: (n: number) => string = (n) => `${n}d ago`,
): string {
  if (!raw) return "—";
  const d = new Date(raw.length <= 10 ? `${raw}T00:00:00` : raw);
  if (Number.isNaN(d.getTime())) return "—";
  // Saved preferences drive the rendering (§9): the UI locale and the
  // selected IANA zone when a formatter is passed, en-US otherwise.
  const date = fmt
    ? fmt(raw)
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diffDays < 0) return date;
  if (diffDays === 0) return `${today} · ${date}`;
  if (diffDays === 1) return `${yesterday} · ${date}`;
  if (diffDays < 30) return `${daysAgo(diffDays)} · ${date}`;
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
  const { t, tp, fmtDate } = useLocale();
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
  /* Add-employee dialog behaviour (§2): Escape dismisses, the first
   * field takes focus on open, and focus returns to whatever opened
   * the dialog when it closes. */
  const inviteFirstField = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (!inviteOpen) return;
    const opener = document.activeElement as HTMLElement | null;
    inviteFirstField.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setInviteOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, [inviteOpen]);
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
    if (act === "revoke" && !window.confirm(t("admin.confirms.revoke"))) return;
    if (act === "suspend" && targetRole === "admin" && !window.confirm(t("admin.confirms.suspendAdmin")))
      return;
    if (
      act === "role" &&
      newRole === "employee" &&
      targetRole === "admin" &&
      !window.confirm(t("admin.confirms.demoteAdmin"))
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
    if (!window.confirm(t("admin.confirms.invalidate"))) return;
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
      setNotice(tp("admin.notices.sessionsRevoked", Number(r.revoked) || 0, { count: Number(r.revoked) || 0 }));
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
      setNotice(t("admin.notices.employeeAdded"));
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
    setNotice(t("admin.notices.reportExported"));
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
    setNotice(t("admin.notices.teamSaved", { name }));
  }

  const stats = useMemo(() => {
    const rows = employees ?? [];
    const total = rows.length;
    const pct = (n: number) => (total ? t("admin.stats.pctOf", { pct: Math.round((n / total) * 100) }) : t("admin.stats.noEmployees"));
    const active = rows.filter((e) => e.status === "active").length;
    const pending = rows.filter((e) => e.status === "pending").length;
    const admins = rows.filter((e) => e.role === "admin").length;
    const staff = rows.filter((e) => e.role !== "admin").length;
    return [
      { label: t("admin.stats.total"), value: String(total), icon: "users", tint: "var(--shell-blue-soft)", trend: total ? tp("admin.stats.staffMix", staff, { employees: staff, admins }) : t("admin.stats.noEmployees") },
      { label: t("admin.stats.active"), value: String(active), icon: "check", tint: "var(--shell-green-soft)", trend: pct(active) },
      /* "Pending Approvals", not "Pending Invites": no invitation
       *  email exists — pending rows await an approval decision. */
      { label: t("admin.stats.pending"), value: String(pending), icon: "clock", tint: "var(--shell-amber-soft)", trend: pending ? t("admin.stats.awaitingApproval") : t("admin.stats.inboxZero") },
      { label: t("admin.stats.admins"), value: String(admins), icon: "lock", tint: "var(--shell-violet-soft)", trend: pct(admins) },
    ];
  }, [employees, t, tp]);

  const adminCount = stats[3].value;
  const relDay = {
    today: t("admin.dates.today"),
    yesterday: t("admin.dates.yesterday"),
    daysAgo: (n: number) => t("admin.dates.daysAgo", { count: n }),
  };
  const adminDate = (raw: string) => friendlyDate(raw, fmtDate, relDay.today, relDay.yesterday, relDay.daysAgo);
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
        title={t("admin.title")}
        sub={t("admin.sub")}
        actions={(
          <span className="actions-2-1">
            <button type="button" className="btn-outline" onClick={exportAccessReport}>
              <Icon name="download" size={14} /> {t("admin.exportReport")}
            </button>
            <button type="button" className="btn-outline" onClick={() => setTeamOpen(true)}>
              <Icon name="plus" size={14} /> {t("admin.createTeam")}
            </button>
            <button type="button" className="btn-primary" onClick={() => setInviteOpen(true)}>
              <Icon name="plus" size={14} /> {t("admin.addEmployee")}
            </button>
          </span>
        )}
      />
      {employees === null ? <span className="sr-only" role="status">{t("admin.loadingEmployees")}</span> : null}
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
                {employees === null ? <Skeleton height={14} /> : s.trend}
              </div>
            </div>
          </div>
        ))}
      </div>

      <Panel title={t("admin.access.title")} sub={t("admin.access.sub")}>
        <div className="rep-filters" style={{ marginBottom: 12 }}>
          <span className="rep-search admin-search">
            <Icon name="search" size={15} />
            <input
              type="text"
              id="admin-search"
              placeholder={t("admin.access.searchPlaceholder")}
              aria-label={t("admin.access.searchAria")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </span>
          <select
            id="admin-status-filter"
            aria-label={t("admin.access.statusAria")}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">{t("admin.access.allStatuses")}</option>
            <option value="pending">{codeLabel(t, "statuses", "pending")}</option>
            <option value="active">{codeLabel(t, "statuses", "active")}</option>
            <option value="suspended">{codeLabel(t, "statuses", "suspended")}</option>
            <option value="revoked">{codeLabel(t, "statuses", "revoked")}</option>
          </select>
          <select
            id="admin-role-filter"
            aria-label={t("admin.access.roleAria")}
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">{t("admin.access.allRoles")}</option>
            <option value="admin">{codeLabel(t, "roles", "admin")}</option>
            <option value="employee">{codeLabel(t, "roles", "employee")}</option>
          </select>
          <button type="button" className="btn-outline" disabled={busyKey !== null} onClick={() => void refreshAll()}>
            <Icon name="reset" size={14} /> {t("admin.access.refresh")}
          </button>
          {notice !== "" && (
            <span className="panel-sub" role="status" style={{ margin: 0 }}>
              {notice}
            </span>
          )}
        </div>
        {loading && employees === null && notice === "" ? (
          <>
            <span className="sr-only" role="status">{t("admin.loadingEmployees")}</span>
            <Skeleton height={180} />
          </>
        ) : employees !== null && (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">{t("admin.access.headers.name")}</th>
                  <th scope="col">{t("admin.access.headers.email")}</th>
                  <th scope="col">{t("admin.access.headers.role")}</th>
                  <th scope="col">{t("admin.access.headers.team")}</th>
                  <th scope="col">{t("admin.access.headers.status")}</th>
                  <th scope="col">{t("admin.access.headers.lastActive")}</th>
                  <th scope="col">{t("admin.access.headers.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {employees.length === 0 ? (
                  <tr>
                    <td colSpan={7}>{t("admin.access.noMatch")}</td>
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
                            {codeLabel(t, "roles", e.role)}
                          </span>
                        </td>
                        <td title={t("admin.access.teamUnknown")}>—</td>
                        <td>
                          <span className={
                            e.status === "active" ? "pill pill-ok"
                            : e.status === "pending" ? "pill pill-info"
                            : e.status === "revoked" ? "pill pill-bad" : "chip-static"
                          }>
                            {codeLabel(t, "statuses", e.status)}
                          </span>
                        </td>
                        <td>{e.last_login_at ? adminDate(e.last_login_at) : t("admin.access.neverSignedIn")}</td>
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
                                {t("admin.access.approve")}
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
                                {t("admin.access.suspend")}
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
                                {t("admin.access.reactivate")}
                              </button>
                            )}
                            <OverflowMenu
                              label={t("admin.access.moreActions", { email: e.email })}
                              items={[
                                ...(e.status !== "revoked" ? [{
                                  label: t("admin.access.revoke"),
                                  onSelect: () => { void runAction("revoke", e.id, e.role, ""); },
                                }] : []),
                                {
                                  label: nextRole === "admin" ? t("admin.access.makeAdmin") : t("admin.access.makeEmployee"),
                                  onSelect: () => { void runAction("role", e.id, e.role, nextRole); },
                                },
                                {
                                  label: t("admin.access.invalidateSessions"),
                                  onSelect: () => { void invalidateSessions(e.id); },
                                },
                              ]}
                            />
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
        <Panel title={t("admin.teams.title")} sub={t("admin.teams.sub")}>
          <div>
            <div className="insight">
              <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                <Icon name="lock" size={18} />
              </span>
              <div>
                <h4>{t("admin.stats.admins")}{employees !== null ? ` (${adminCount})` : ""}</h4>
                <p>{t("admin.teams.adminsBody")}</p>
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
                <h4>{t("admin.teams.teamsTitle")}{teams !== null ? ` (${teams.length})` : ""}</h4>
                <p>{teams === null
                  ? <span className="sr-only" role="status">{t("admin.loadingTeams")}</span>
                  : teams.length === 0
                    ? t("admin.teams.teamsEmpty")
                    : tp("admin.teams.teamsNamed", teams.length, { count: teams.length })}</p>
              </div>
            </div>
            <div className="insight">
              <span className="insight-ico" style={{ background: "var(--shell-teal-soft)" }}>
                <Icon name="user" size={18} />
              </span>
              <div>
                <h4>{t("admin.teams.employeesTitle")}{employees !== null ? ` (${employeeCount})` : ""}</h4>
                <p>{t("admin.teams.employeesBody")}</p>
              </div>
            </div>
            {allTeams.map((team) => (
              <div className="insight" key={team.name}>
                <span className="insight-ico" style={{ background: "var(--shell-green-soft)" }}>
                  <Icon name="users" size={18} />
                </span>
                <div style={{ flex: 1 }}>
                  <h4>{team.name}</h4>
                  <p>{team.campaigns === 1 ? t("admin.teams.campaignOne") : t("admin.teams.campaignsOther", { count: team.campaigns })} {t("admin.teams.datasetSuffix")}{team.local ? ` · ${t("admin.teams.localSuffix")}` : ""}.</p>
                </div>
                {team.local ? <span className="badge-demo">{t("admin.teams.local")}</span> : null}
              </div>
            ))}
            {teams === null ? <Skeleton height={60} /> : null}
          </div>
        </Panel>
        <Panel title={t("admin.rules.title")} sub={t("admin.rules.sub")}>
          <ul className="tips-list">
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-green-soft)" }}>
                <Icon name="check" size={18} />
              </span>
              <div>
                <h4>{t("admin.rules.gateTitle")}</h4>
                <p>{t("admin.rules.gateBody")}</p>
              </div>
            </li>
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                <Icon name="clock" size={18} />
              </span>
              <div>
                <h4>{t("admin.rules.effectTitle")}</h4>
                <p>{t("admin.rules.effectBody")}</p>
              </div>
            </li>
            <li>
              <span className="insight-ico" style={{ background: "var(--shell-amber-soft)" }}>
                <Icon name="lock" size={18} />
              </span>
              <div>
                <h4>{t("admin.rules.lastAdminTitle")}</h4>
                <p>{t("admin.rules.lastAdminBody")}</p>
              </div>
            </li>
          </ul>
        </Panel>
      </div>

      <div className="section-gap" />
      <Panel
        title={t("admin.activity.title")}
        sub={t("admin.activity.sub")}
      >
        {events.length === 0 ? (
          <EmptyState text={t("admin.activity.empty")} />
        ) : (
          <div className="tbl-wrap">
            <table className="tbl" aria-label={t("admin.activity.title")}>
              <thead>
                <tr>
                  <th scope="col">{t("admin.activity.when")}</th>
                  <th scope="col">{t("admin.activity.action")}</th>
                  <th scope="col">{t("admin.activity.target")}</th>
                  <th scope="col">{t("admin.activity.admin")}</th>
                  <th scope="col">{t("admin.activity.change")}</th>
                </tr>
              </thead>
              <tbody>
                {events.map((v) => (
                  <tr key={v.id}>
                    <td>{adminDate(v.created_at)}</td>
                    <td className="cell-main">{auditAction(v.action)}</td>
                    <td>{identityCell(v.target_id)}</td>
                    <td>{identityCell(v.admin_id)}</td>
                    <td>
                      {titleCase(v.prev_value)} → {titleCase(v.new_value)}
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
          <span className="adv-title">{t("admin.demoTools")}</span>
          <span className="panel-sub">{t("admin.demoToolsSub")}</span>
        </summary>
        <div style={{ marginTop: 10 }}>
          <DemoPackPanel />
        </div>
      </details>

      {inviteOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("admin.addDialog.title")}
          onClick={() => setInviteOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 80, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
        >
          <div
            className="panel"
            onClick={(e) => e.stopPropagation()}
            style={{ width: "100%", maxWidth: 460, margin: 0 }}
          >
            <div className="panel-head dialog-head">
              <h2 className="panel-title">{t("admin.addDialog.title")}</h2>
              <button
                type="button"
                className="icon-btn"
                aria-label={t("admin.addDialog.close")}
                onClick={() => setInviteOpen(false)}
              >
                <Icon name="x" size={16} />
              </button>
            </div>
            <p className="panel-sub" style={{ marginTop: -8, marginBottom: 12 }}>{t("admin.addDialog.sub")}</p>
            <div className="rep-filters" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <input
                ref={inviteFirstField}
                type="text"
                placeholder={t("admin.addDialog.firstNamePh")}
                aria-label={t("admin.addDialog.firstName")}
                autoComplete="given-name"
                value={addFirst}
                onChange={(e) => setAddFirst(e.target.value)}
              />
              <input
                type="text"
                placeholder={t("admin.addDialog.lastNamePh")}
                aria-label={t("admin.addDialog.lastName")}
                autoComplete="family-name"
                value={addLast}
                onChange={(e) => setAddLast(e.target.value)}
              />
              <input
                type="email"
                placeholder={t("admin.addDialog.emailPh")}
                aria-label={t("admin.addDialog.email")}
                autoComplete="email"
                value={addEmail}
                onChange={(e) => setAddEmail(e.target.value)}
              />
              <select
                aria-label={t("admin.addDialog.role")}
                value={addRole}
                onChange={(e) => setAddRole(e.target.value)}
              >
                <option value="employee">{t("admin.addDialog.roleEmployee")}</option>
                <option value="admin">{t("admin.addDialog.roleAdmin")}</option>
              </select>
              <LoadingButton type="button" className="btn-primary"
                loading={busyKey === "add"} loadingLabel="Adding…"
                disabled={busyKey !== null} onClick={() => void addEmployee()}>
                <Icon name="plus" size={14} /> {t("admin.addDialog.add")}
              </LoadingButton>
            </div>
          </div>
        </div>
      ) : null}

      {teamOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("admin.teamDialog.title")}
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
                <h2 className="panel-title">{t("admin.teamDialog.title")}</h2>
                <p className="panel-sub">{t("admin.teamDialog.sub")}</p>
              </div>
              <button type="button" className="link-teal" onClick={() => setTeamOpen(false)}>
                {t("admin.teamDialog.close")}
              </button>
            </div>
            <div className="field">
              <label htmlFor="new-team-name">{t("admin.teamDialog.nameLabel")}</label>
              <input
                id="new-team-name"
                type="text"
                placeholder={t("admin.teamDialog.namePlaceholder")}
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") createTeam(); }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
              <button type="button" className="btn-outline" onClick={() => setTeamOpen(false)}>
                {t("admin.teamDialog.cancel")}
              </button>
              <button type="button" className="btn-primary" disabled={!teamName.trim()} onClick={createTeam}>
                {t("admin.teamDialog.create")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
