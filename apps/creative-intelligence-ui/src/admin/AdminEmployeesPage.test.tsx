import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AdminEmployeesPage } from "@/admin/AdminEmployeesPage";

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
    // Revoked rows offer no Revoke action; every other row does.
    expect(screen.getAllByRole("button", { name: "Revoke" })).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Make employee" })).toBeDefined();
    expect(screen.getAllByRole("button", { name: "Make admin" })).toHaveLength(3);
    expect(screen.getByText("Last login")).toBeDefined();
    expect(screen.getByText("Approval")).toBeDefined();
    expect(screen.getByText("2026-09-01")).toBeDefined();
    expect(screen.getByText("Audit trail")).toBeDefined();
    expect(screen.getByText("EMPLOYEE_APPROVED")).toBeDefined();
    expect(screen.getByText("pending → active")).toBeDefined();
  });

  it("shows a loading state before data arrives", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    render(<AdminEmployeesPage />);
    expect(screen.getByText("Loading employees…")).toBeDefined();
  });

  it("renders list errors", async () => {
    setupFetch({ error: "db is locked" });
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByText("db is locked")).toBeDefined();
    });
  });

  it("asks for confirmation before revoke, and posts only on accept", async () => {
    const calls = setupFetch();
    stubConfirm(false);
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    const revoke = screen.getAllByRole("button", { name: "Revoke" })[0];
    fireEvent.click(revoke);
    expect(window.confirm).toHaveBeenCalledWith(
      "Revoke this employee's access? Their sessions stop working immediately.",
    );
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    stubConfirm(true);
    fireEvent.click(revoke);
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
      "Suspend this admin? Their sessions stop working immediately. The server refuses when they are the last active admin.",
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
    fireEvent.click(screen.getByRole("button", { name: "Make employee" }));
    expect(window.confirm).toHaveBeenCalledWith(
      "Demote this admin to employee? They lose admin access immediately.",
    );
    expect(
      calls.some(
        (c) =>
          c.method === "POST" && c.url === "/api/admin/employees/e2/role",
      ),
    ).toBe(false);
  });

  it("adds an employee and reports success", async () => {
    const calls = setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    fireEvent.change(screen.getByPlaceholderText("email"), {
      target: { value: "new@foap.test" },
    });
    fireEvent.change(screen.getByLabelText("New employee role"), {
      target: { value: "employee" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add (active)" }));
    await waitFor(() => {
      expect(screen.getByText("Employee added as active.")).toBeDefined();
    });
    const post = calls.find(
      (c) => c.method === "POST" && c.url === "/api/admin/employees",
    );
    expect(post?.body).toMatchObject({
      email: "new@foap.test",
      role: "employee",
    });
  });

  it("confirms before invalidating sessions and reports the count", async () => {
    const calls = setupFetch({ revoked: 2 });
    stubConfirm(true);
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Suspend" })).toBeDefined();
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: "Invalidate sessions" })[1],
    );
    expect(window.confirm).toHaveBeenCalledWith(
      "Invalidate all sessions for this employee? They are signed out everywhere immediately.",
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
      expect(screen.getByText("2 session(s) revoked.")).toBeDefined();
    });
  });

  it("sends search, status, and role filters to the employees endpoint", async () => {
    const calls = setupFetch();
    render(<AdminEmployeesPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
    });
    fireEvent.change(screen.getByPlaceholderText("search name or email"), {
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
    fireEvent.change(screen.getByLabelText("Filter by status"), {
      target: { value: "active" },
    });
    await waitFor(() => {
      expect(
        calls.some(
          (c) => c.method === "GET" && c.url.includes("filter=active"),
        ),
      ).toBe(true);
    });
    fireEvent.change(screen.getByLabelText("Filter by status"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("Filter by role"), {
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
});
