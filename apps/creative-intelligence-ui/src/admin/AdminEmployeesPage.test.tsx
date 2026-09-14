import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AdminEmployeesPage, friendlyDate } from "@/admin/AdminEmployeesPage";

interface Call {
  url: string;
  method: string;
  body: unknown;
}

const empPending = {
  id: "e1",
  email: "pip@foap.test",
  first_name: "Pip",
  last_name: "Pending",
  avatar_url: "",
  provider: "google",
  role: "employee",
  status: "pending",
  created_at: "2026-01-01",
  approved_at: "",
  approved_by: "",
  last_login_at: "",
  updated_at: "2026-01-02",
};

const empAdmin = {
  id: "e2",
  email: "ada@foap.test",
  first_name: "Ada",
  last_name: "Admin",
  avatar_url: "",
  provider: "google",
  role: "admin",
  status: "active",
  created_at: "2026-01-01",
  approved_at: "2026-01-02",
  approved_by: "rootadmin0",
  last_login_at: "2026-09-01",
  updated_at: "2026-09-02",
};

const empSuspended = {
  id: "e3",
  email: "sam@foap.test",
  first_name: "Sam",
  last_name: "Suspended",
  avatar_url: "",
  provider: "google",
  role: "employee",
  status: "suspended",
  created_at: "2026-01-01",
  approved_at: "2026-01-03",
  approved_by: "rootadmin0",
  last_login_at: "2026-08-01",
  updated_at: "2026-08-02",
};

const empRevoked = {
  id: "e4",
  email: "rex@foap.test",
  first_name: "Rex",
  last_name: "Revoked",
  avatar_url: "",
  provider: "google",
  role: "employee",
  status: "revoked",
  created_at: "2026-01-01",
  approved_at: "2026-01-04",
  approved_by: "rootadmin0",
  last_login_at: "2026-07-01",
  updated_at: "2026-07-02",
};

const auditEvents = [
  {
    id: "a1",
    target_id: "e1target99",
    admin_id: "adminalice00",
    action: "EMPLOYEE_APPROVED",
    prev_value: "pending",
    new_value: "active",
    created_at: "2026-09-03",
  },
];

function setupFetch(opts?: { error?: string; revoked?: number }): Call[] {
  const calls: Call[] = [];
  window.fetch = vi.fn(
    async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      let body: unknown;
      try {
        body = init?.body ? JSON.parse(String(init.body)) : undefined;
      } catch {
        body = undefined;
      }
      calls.push({ url, method, body });
      if (opts?.error) {
        return Response.json({ error: opts.error }, { status: 409 });
      }
      if (method === "GET" && url.startsWith("/api/admin/employees")) {
        return Response.json({
          employees: [empPending, empAdmin, empSuspended, empRevoked],
        });
      }
      if (method === "GET" && url.startsWith("/api/admin/audit")) {
        return Response.json({ events: auditEvents });
      }
      if (method === "GET" && url.startsWith("/api/campaigns/meta")) {
        return Response.json({
          campaigns: [
            { name: "Alpha", client: "Acme", team: "Growth" },
            { name: "Beta", client: "Acme", team: "Brand" },
          ],
        });
      }
      if (method === "POST" && url.endsWith("/sessions/revoke")) {
        return Response.json({ ok: true, revoked: opts?.revoked ?? 2 });
      }
      if (method === "POST" && url === "/api/admin/employees") {
        const b = (body ?? {}) as { email?: string };
        return Response.json({
          employee: { ...empPending, id: "e9", email: b.email ?? "" },
        });
      }
      if (method === "POST") {
        return Response.json({ employee: empAdmin });
      }
      return Response.json({});
    },
  ) as unknown as typeof fetch;
  return calls;
}

const realConfirm = window.confirm;

function stubConfirm(value: boolean) {
  window.confirm = vi.fn(() => value) as unknown as typeof window.confirm;
}

describe("AdminEmployeesPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.confirm = realConfirm;
  });

  it("renders the employee list with mocked data", async () => {
    setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("pip@foap.test")).toBeDefined();
    });
    expect(screen.getByText("Pip Pending")).toBeDefined();
    expect(screen.getByText("Ada Admin")).toBeDefined();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Suspend" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeDefined();
    // Row actions live behind one accessible More Actions menu per row.
    const toggles = screen.getAllByRole("button", { name: /More Actions For/ });
    expect(toggles).toHaveLength(4);
    fireEvent.click(toggles[0]);
    expect(screen.getByRole("menuitem", { name: "Revoke" })).toBeDefined();
    expect(screen.getByRole("menuitem", { name: "Make Admin" })).toBeDefined();
    expect(screen.getByRole("menuitem", { name: "Invalidate Sessions" })).toBeDefined();
    fireEvent.keyDown(document, { key: "Escape" });
    // Revoked rows offer no Revoke action.
    fireEvent.click(toggles[3]);
    expect(screen.queryByRole("menuitem", { name: "Revoke" })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Make Admin" })).toBeDefined();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByText("Last Active")).toBeDefined();
    expect(screen.getByText("Team")).toBeDefined();
    // No Approval column: access state lives in Status only.
    expect(screen.queryByText("Approval")).toBeNull();
    // Friendly dates, never raw ISO.
    expect(screen.getByText(/Sep 1, 2026/)).toBeDefined();
    expect(screen.queryByText("2026-09-01")).toBeNull();
    expect(screen.getByText("Never Signed In")).toBeDefined();
    expect(screen.getByRole("table", { name: "Workspace Activity" })).toBeDefined();
    expect(screen.getByText("Employee Approved")).toBeDefined();
    expect(screen.getByText("Pending → Active")).toBeDefined();
  });

  it("shows a loading state before data arrives", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    render(<AdminEmployeesPage />);
    expect(screen.getByText("Loading Employees…")).toBeDefined();
  });

  it("renders list errors", async () => {
    setupFetch({ error: "db is locked" });
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("db is locked")).toBeDefined();
    });
  });

  it("renders each employee's own photo, falling back to initials", async () => {
    setupFetch();
    const photoAdmin = { ...empAdmin, avatar_url: "https://pics.test/ada.jpg" };
    const base = window.fetch;
    window.fetch = (async (url: unknown, init?: RequestInit) => {
      if (String(url).startsWith("/api/admin/employees")) {
        return Response.json({ employees: [photoAdmin, empPending] });
      }
      return (base as typeof fetch)(url as string, init);
    }) as unknown as typeof fetch;
    const { container } = render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("Ada Admin")).toBeDefined();
    });
    // THAT employee's photo renders in their row…
    expect(
      container.querySelector('img.avatar[src="https://pics.test/ada.jpg"]'),
    ).not.toBeNull();
    // …while a photo-less row falls back to initials, never a broken image.
    expect(screen.getByText("PP")).toBeDefined();
  });

  it("asks for confirmation before revoke, and posts only on accept", async () => {
    const calls = setupFetch();
    stubConfirm(false);
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    const toggle = screen.getByRole("button", { name: "More Actions For pip@foap.test" });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("menuitem", { name: "Revoke" }));
    expect(window.confirm).toHaveBeenCalledWith(
      "Revoke This Employee's Access? Their Sessions Stop Working Immediately.",
    );
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    stubConfirm(true);
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("menuitem", { name: "Revoke" }));
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.method === "POST" && c.url === "/api/admin/employees/e1/revoke",
        ),
      ).toBe(true);
    });
  });

  it("confirms before suspending an admin or demoting one", async () => {
    const calls = setupFetch();
    stubConfirm(true);
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Suspend" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));
    expect(window.confirm).toHaveBeenCalledWith(
      "Suspend This Admin? Their Sessions Stop Working Immediately. The Server Refuses When They Are The Last Active Admin.",
    );
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.method === "POST" && c.url === "/api/admin/employees/e2/suspend",
        ),
      ).toBe(true);
    });
    stubConfirm(false);
    fireEvent.click(screen.getByRole("button", { name: "More Actions For ada@foap.test" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Make Employee" }));
    expect(window.confirm).toHaveBeenCalledWith(
      "Demote This Admin To Employee? They Lose Admin Access Immediately.",
    );
    expect(
      calls.some(
        (c) =>
          c.method === "POST" && c.url === "/api/admin/employees/e2/role",
      ),
    ).toBe(false);
  });

  it("adds an employee through the add-employee dialog and reports success", async () => {
    const calls = setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    // The permanent Add Employee panel is gone: inviting happens in a modal.
    expect(screen.queryByPlaceholderText("Email Address")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add Employee" }));
    const dialog = screen.getByRole("dialog", { name: "Add Employee" });
    // Field order: First Name, Last Name, Email Address, Role.
    const fields = within(dialog).getAllByRole("textbox");
    expect(fields.map((f) => f.getAttribute("placeholder"))).toEqual([
      "First Name",
      "Last Name",
      "Email Address",
    ]);
    // X close control shares the title row.
    expect(
      within(dialog).getByRole("button", { name: "Close Add Employee dialog" }),
    ).toBeDefined();
    fireEvent.change(screen.getByPlaceholderText("Email Address"), {
      target: { value: "new@foap.test" },
    });
    fireEvent.change(screen.getByLabelText("New Employee Role"), {
      target: { value: "employee" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add Employee" }));
    await waitFor(() => {
      expect(screen.getByText("Employee Added As Active.")).toBeDefined();
    });
    const post = calls.find(
      (c) => c.method === "POST" && c.url === "/api/admin/employees",
    );
    expect(post?.body).toMatchObject({
      email: "new@foap.test",
      role: "employee",
    });
  });

  it("groups Admin actions two-above-one in DOM order (§1)", async () => {
    setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    const wrap = document.querySelector(".actions-2-1");
    expect(wrap).not.toBeNull();
    const labels = [...wrap!.querySelectorAll(":scope > button")].map((b) =>
      b.textContent?.trim(),
    );
    expect(labels).toEqual(["Export Access Report", "Create Team", "Add Employee"]);
  });

  it("confirms before invalidating sessions and reports the count", async () => {
    const calls = setupFetch({ revoked: 2 });
    stubConfirm(true);
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Suspend" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "More Actions For ada@foap.test" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Invalidate Sessions" }));
    expect(window.confirm).toHaveBeenCalledWith(
      "Invalidate All Sessions For This Employee? They Are Signed Out Everywhere Immediately.",
    );
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.method === "POST" &&
            c.url === "/api/admin/employees/e2/sessions/revoke",
        ),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByText("2 Session(s) Revoked.")).toBeDefined();
    });
  });

  it("sends search, status, and role filters to the employees endpoint", async () => {
    const calls = setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    fireEvent.change(screen.getByPlaceholderText("Search name or email"), {
      target: { value: "ada" },
    });
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.method === "GET" &&
            c.url.includes("/api/admin/employees?") &&
            c.url.includes("search=ada"),
        ),
      ).toBe(true);
    });
    fireEvent.change(screen.getByLabelText("Filter By Status"), {
      target: { value: "active" },
    });
    await waitFor(() => {
      expect(
        calls.some(
          (c) => c.method === "GET" && c.url.includes("filter=active"),
        ),
      ).toBe(true);
    });
    fireEvent.change(screen.getByLabelText("Filter By Status"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("Filter By Role"), {
      target: { value: "admin" },
    });
    await waitFor(() => {
      expect(
        calls.some(
          (c) => c.method === "GET" && c.url.includes("filter=admin"),
        ),
      ).toBe(true);
    });
  });

  it("shows the four KPI cards with honest sub-lines", async () => {
    setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("Total Employees")).toBeDefined();
    });
    expect(screen.getByText("Active Users")).toBeDefined();
    expect(screen.getByText("Pending Approvals")).toBeDefined();
    expect(screen.getByText("Admins")).toBeDefined();
  });

  it("orders Admins, Teams and Employees rows with real counts", async () => {
    setupFetch();
    const { container } = render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("Teams (2)")).toBeDefined();
    });
    const heads = Array.from(container.querySelectorAll(".insight h4"))
      .map((h) => h.textContent);
    expect(heads.indexOf("Admins (1)")).toBeGreaterThanOrEqual(0);
    expect(heads.indexOf("Teams (2)")).toBeGreaterThan(heads.indexOf("Admins (1)"));
    expect(heads.indexOf("Employees (3)")).toBeGreaterThan(heads.indexOf("Teams (2)"));
  });

  it("lists multiple real teams from campaign metadata", async () => {
    setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("Growth")).toBeDefined();
    });
    expect(screen.getByText("Brand")).toBeDefined();
  });

  it("exports an access report from real employee and audit data", async () => {
    setupFetch();
    const createSpy = vi.fn(() => "blob:mock");
    window.URL.createObjectURL = createSpy;
    window.URL.revokeObjectURL = vi.fn();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Export Access Report" }));
    await waitFor(() => {
      expect(screen.getByText("Access Report Exported.")).toBeDefined();
    });
    expect(createSpy).toHaveBeenCalled();
  });

  it("formats friendly dates without raw ISO", () => {
    expect(friendlyDate("")).toBe("—");
    expect(friendlyDate("not-a-date")).toBe("—");
    expect(friendlyDate("2026-09-01")).toContain("Sep 1, 2026");
    expect(friendlyDate("2026-09-01")).not.toContain("2026-09-01");
  });
});
