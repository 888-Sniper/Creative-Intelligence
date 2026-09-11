import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { AuthGate } from "@/auth/AuthGate";
import { AppLayout } from "@/layouts/AppLayout";
import { statusForMe } from "@/types/auth";
import type { MeResponse } from "@/types/auth";

const base: MeResponse = {
  authenticated: false,
  gate: "login",
  employee: null,
  is_admin: false,
  message: "",
  workos_configured: true,
};

function mockMe(me: MeResponse) {
  window.fetch = vi.fn(async () =>
    Response.json(me),
  ) as unknown as typeof fetch;
}

function renderGate() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <AuthGate>
          <AppLayout />
        </AuthGate>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("auth state model", () => {
  it("maps backend gates to centralized states", () => {
    expect(statusForMe(null)).toBe("INITIALISING");
    expect(statusForMe({ ...base })).toBe("SIGNED_OUT");
    expect(statusForMe({ ...base, gate: "pending", authenticated: true })).toBe("PENDING");
    expect(statusForMe({ ...base, gate: "suspended", authenticated: true })).toBe("SUSPENDED");
    expect(statusForMe({ ...base, gate: "revoked", authenticated: true })).toBe("REVOKED");
    expect(
      statusForMe({
        ...base,
        authenticated: true,
        gate: "app",
        employee: { id: "e1", email: "a@b.c", first_name: "A", last_name: "B", avatar_url: "", provider: "google", role: "employee", status: "active", created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "" },
      }),
    ).toBe("AUTHENTICATED");
  });
});

describe("AuthGate screens", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows the initial loading state, then the login screen", async () => {
    mockMe(base);
    renderGate();
    expect(screen.getByText("Checking Your Session…")).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText("Welcome To Creative Intelligence")).toBeDefined();
    });
  });

  it("renders all four provider buttons on login", async () => {
    mockMe(base);
    renderGate();
    for (const name of ["Continue With Google", "Continue With Microsoft", "Continue With Apple", "Continue With GitHub"]) {
      await waitFor(() => {
        expect(screen.getByRole("button", { name })).toBeDefined();
      });
    }
  });

  it("shows pending / suspended / revoked gates without the dashboard", async () => {
    for (const [gate, title] of [
      ["pending", "Access Pending"],
      ["suspended", "Access Suspended"],
      ["revoked", "Access Revoked"],
    ] as const) {
      window.fetch = vi.fn(async () => Response.json({ ...base, authenticated: true, gate })) as unknown as typeof fetch;
      const view = renderGate();
      await waitFor(() => {
        expect(screen.getByText(title)).toBeDefined();
      });
      expect(screen.queryByText("Overview")).toBeNull();
      view.unmount();
    }
  });

  it("renders the dashboard and account menu when authenticated", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/accounts") return Response.json({ accounts: [] });
      return Response.json({
        ...base,
        authenticated: true,
        gate: "app",
        employee: { id: "e1", email: "ada@foap.test", first_name: "Ada", last_name: "L", avatar_url: "", provider: "google", role: "employee", status: "active", created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "" },
      });
    }) as unknown as typeof fetch;
    renderGate();
    await waitFor(() => {
      expect(screen.getByText("Overview")).toBeDefined();
    });
    expect(screen.getByText("Ada L")).toBeDefined();
  });

  it("hides the Admin tab from non-admins", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/accounts") return Response.json({ accounts: [] });
      return Response.json({
        ...base,
        authenticated: true,
        gate: "app",
        employee: { id: "e1", email: "e@foap.test", first_name: "E", last_name: "M", avatar_url: "", provider: "google", role: "employee", status: "active", created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "" },
      });
    }) as unknown as typeof fetch;
    renderGate();
    await waitFor(() => {
      expect(screen.getByText("Overview")).toBeDefined();
    });
    expect(screen.queryByText("Admin")).toBeNull();
  });
});
