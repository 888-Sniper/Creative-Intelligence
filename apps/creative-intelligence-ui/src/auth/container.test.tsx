import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { installationContainer } from "@/auth/container";
import type { MeResponse } from "@/types/auth";

const authed: MeResponse = {
  authenticated: true,
  gate: "app",
  employee: { id: "e1", email: "a@b.c", first_name: "A", last_name: "B", avatar_url: "", provider: "google", role: "employee", status: "active", created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "" },
  is_admin: false,
  message: "",
  workos_configured: true,
};

function Probe() {
  const { emailSignIn } = useAuth();
  return (
    <button type="button" onClick={() => void emailSignIn("a@b.c", "pw")}>
      go
    </button>
  );
}

describe("installation container (item 18)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try {
      window.localStorage.clear();
    } catch {
      /* jsdom without origin: in-memory fallback holds the id */
    }
  });

  afterEach(() => {
    cleanup();
  });

  it("issues a stable, well-formed container id", () => {
    const first = installationContainer();
    expect(first).toMatch(/^[\w-]{1,64}$/);
    expect(installationContainer()).toBe(first);
  });

  it("binds the session on authenticated boot", async () => {
    const calls: Array<{ url: string; body: string }> = [];
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      calls.push({ url: String(input), body: String(init?.body ?? "") });
      if (String(input) === "/api/auth/accounts") return Response.json({ accounts: [] });
      return Response.json(authed);
    }) as unknown as typeof fetch;
    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      const bind = calls.find((c) => c.url === "/api/auth/container");
      expect(bind).toBeDefined();
      expect(JSON.parse(bind?.body ?? "{}").container_id).toBe(installationContainer());
    });
  });

  it("sends the container id with email sign-in", async () => {
    const bodies: string[] = [];
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      if (String(input) === "/api/auth/email/signin") {
        bodies.push(String(init?.body ?? ""));
        return Response.json(authed);
      }
      if (String(input) === "/api/auth/accounts") return Response.json({ accounts: [] });
      return Response.json({ authenticated: false, gate: "login", employee: null, is_admin: false, message: "", workos_configured: true });
    }) as unknown as typeof fetch;
    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "go" })).toBeDefined();
    });
    screen.getByRole("button", { name: "go" }).click();
    await waitFor(() => {
      expect(bodies.length).toBe(1);
    });
    expect(JSON.parse(bodies[0]).container_id).toBe(installationContainer());
  });
});
