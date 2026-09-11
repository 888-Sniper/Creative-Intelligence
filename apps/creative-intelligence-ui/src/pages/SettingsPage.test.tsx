import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { SettingsPage } from "@/pages/SettingsPage";
import type { MeResponse } from "@/types/auth";

const employee = {
  id: "e1", email: "ada@foap.test", first_name: "Ada", last_name: "L",
  avatar_url: "", provider: "google", role: "employee", status: "active",
  created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "",
};

const authed: MeResponse = {
  authenticated: true, gate: "app", employee, is_admin: false,
  message: "", workos_configured: true,
};

describe("SettingsPage (item 21)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  function renderSettings(googleConnected = false) {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/accounts") return Response.json({ accounts: [] });
      if (url === "/api/auth/container") return Response.json({ container_id: "c1" });
      if (url === "/api/auth/google/status") {
        return Response.json({ connected: googleConnected });
      }
      return Response.json(authed);
    }) as unknown as typeof fetch;
    return render(
      <MemoryRouter>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </MemoryRouter>,
    );
  }

  it("shows account details with provider and role", async () => {
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Settings" })).toBeDefined();
    });
    expect(screen.getByText("ada@foap.test (Verified, Read-Only)")).toBeDefined();
    expect(screen.getByText("Google")).toBeDefined();
    expect(screen.getByText("employee")).toBeDefined();
  });

  it("offers light, dark and system appearance modes", async () => {
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /Light/ })).toBeDefined();
    });
    expect(screen.getByRole("radio", { name: /Dark/ })).toBeDefined();
    const system = screen.getByRole("radio", { name: /System/ }) as HTMLInputElement;
    expect(system).toBeDefined();
    system.click();
    expect((screen.getByRole("radio", { name: /System/ }) as HTMLInputElement).checked).toBe(true);
  });

  it("logs out all sessions after confirmation", async () => {
    const posted: string[] = [];
    const asked: string[] = [];
    window.confirm = vi.fn((message?: string) => {
      asked.push(message ?? "");
      return true;
    });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Log Out All Sessions" })).toBeDefined();
    });
    // Install the recording mock after boot (renderSettings sets its own).
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/sessions/revoke-all") {
        posted.push(url);
        return Response.json({ ok: true });
      }
      if (url === "/api/auth/accounts") return Response.json({ accounts: [] });
      if (url === "/api/auth/container") return Response.json({ container_id: "c1" });
      return Response.json(authed);
    }) as unknown as typeof fetch;
    fireEvent.click(screen.getByRole("button", { name: "Log Out All Sessions" }));
    await waitFor(() => {
      expect(posted).toEqual(["/api/auth/sessions/revoke-all"]);
    });
    expect(asked.length).toBe(1);
    expect(asked[0]).toMatch(/every device/i);
  });

  it("shows Google Drive as not connected by default (item 31)", async () => {
    renderSettings();
    // The connect button renders (disabled) before status loads, so wait
    // for the loaded status text rather than the button.
    await waitFor(() => {
      expect(screen.getByText("Not Connected")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Connect Google Drive" })).toBeDefined();
  });

  it("shows disconnect when Google Drive is connected (item 31)", async () => {
    renderSettings(true);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Disconnect Google Drive" })).toBeDefined();
    });
    expect(screen.getByText("Connected")).toBeDefined();
  });

  it("disconnects Google Drive and updates status (item 31)", async () => {
    const posted: string[] = [];
    renderSettings(true);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Disconnect Google Drive" })).toBeDefined();
    });
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/google/disconnect") {
        posted.push(url);
        return Response.json({ ok: true });
      }
      if (url === "/api/auth/accounts") return Response.json({ accounts: [] });
      if (url === "/api/auth/container") return Response.json({ container_id: "c1" });
      if (url === "/api/auth/google/status") return Response.json({ connected: true });
      return Response.json(authed);
    }) as unknown as typeof fetch;
    fireEvent.click(screen.getByRole("button", { name: "Disconnect Google Drive" }));
    await waitFor(() => {
      expect(posted).toEqual(["/api/auth/google/disconnect"]);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Connect Google Drive" })).toBeDefined();
    });
  });
});
