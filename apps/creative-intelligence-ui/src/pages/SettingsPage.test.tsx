import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { FilterProvider } from "@/state/FilterContext";
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

const patternsData = {
  scope: "All data",
  n_creatives: 2,
  n_events: 1,
  patterns: [
    {
      slot: "hook",
      product_demo: true,
      brand_visible: false,
      cta_present: false,
      voiceover: true,
      n_creatives: 2,
      avg_drop_pts: 7.5,
      max_drop_pts: 9.1,
      examples: ["ck1", "ck2"],
    },
  ],
};

const cohortsData = [{ id: 3, name: "Beauty", filters: { platform: ["tiktok"] }, created_at: "" }];

function mockFetch(opts?: { googleConnected?: boolean; me?: MeResponse }) {
  const calls: Array<[string, RequestInit | undefined]> = [];
  const googleConnected = opts?.googleConnected ?? false;
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push([url, init]);
    const method = init?.method ?? "GET";
    if (url === "/api/auth/me") return Response.json(opts?.me ?? authed);
    if (url === "/api/auth/google/status") return Response.json({ connected: googleConnected });
    if (url.startsWith("/api/retention/patterns")) return Response.json(patternsData);
    if (url === "/api/cohorts" && method === "GET") return Response.json(cohortsData);
    if (url.startsWith("/api/cohorts/build")) {
      return Response.json({ name: "Beauty", metric: "cpa", n_ads: 5, status: "ok" });
    }
    if (url === "/api/cohorts" && method === "POST") {
      return Response.json({ id: 3, name: "Beauty", filters: {}, created_at: "" });
    }
    return Response.json({});
  }) as unknown as typeof fetch;
  return calls;
}

function renderSettings() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <FilterProvider>
          <SettingsPage />
        </FilterProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    // This jsdom build exposes no window.localStorage; install a fresh
    // in-memory stand-in so save/load persistence behaves like a browser.
    const store = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
        setItem: (k: string, v: string) => { store.set(k, String(v)); },
        removeItem: (k: string) => { store.delete(k); },
        clear: () => { store.clear(); },
      } satisfies Storage,
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    try {
      window.localStorage.clear();
    } catch {
      /* jsdom without storage */
    }
  });

  it("renders workspace defaults with theme, accent and density controls", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("General Settings")).toBeDefined();
    });
    expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value).toBe("Alex's Workspace");
    expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("light");
    expect((screen.getByLabelText("Accent Color") as HTMLSelectElement).value).toBe("Teal (Default)");
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value).toBe("Comfortable");
    expect(screen.getByText("Notifications")).toBeDefined();
    expect(screen.getByText("Integrations")).toBeDefined();
    expect(screen.getByText("Security")).toBeDefined();
    expect(screen.getByText("Data Tools")).toBeDefined();
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDefined();
    expect(screen.getByText("No unsaved changes.")).toBeDefined();
  });

  it("saves and resets workspace preferences", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Workspace Name"), { target: { value: "Night Shift" } });
    const save = screen.getByRole("button", { name: "Save Changes" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => {
      expect(screen.getByText("Settings Saved.")).toBeDefined();
    });
    expect(window.localStorage.getItem("ci-settings-prefs")).toContain("Night Shift");
    fireEvent.click(screen.getByRole("button", { name: "Reset Defaults" }));
    await waitFor(() => {
      expect(screen.getByText("Defaults Restored.")).toBeDefined();
    });
    expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value).toBe("Alex's Workspace");
  });

  it("sends a password reset email from Security", async () => {
    const calls = mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Change Password" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Change Password" }));
    await waitFor(() => {
      expect(screen.getByText("Password Reset Email Sent.")).toBeDefined();
    });
    expect(calls.some(([url, init]) => url === "/api/auth/email/reset" && init?.method === "POST")).toBe(true);
  });

  it("logs out all sessions after confirmation", async () => {
    const calls = mockFetch();
    window.confirm = vi.fn(() => true);
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Log Out All Sessions" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Log Out All Sessions" }));
    await waitFor(() => {
      expect(screen.getByText("All Sessions Signed Out.")).toBeDefined();
    });
    expect(calls.some(([url, init]) => url === "/api/auth/sessions/revoke-all" && init?.method === "POST")).toBe(true);
  });

  it("does not revoke sessions when confirmation is dismissed", async () => {
    const calls = mockFetch();
    window.confirm = vi.fn(() => false);
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Log Out All Sessions" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Log Out All Sessions" }));
    await new Promise((r) => setTimeout(r, 50));
    expect(calls.some(([url]) => url === "/api/auth/sessions/revoke-all")).toBe(false);
  });

  it("shows Google Drive as not connected by default", async () => {
    mockFetch({ googleConnected: false });
    renderSettings();
    const integrations = await screen.findByText("Connect your data sources to unlock deeper insights.");
    const panel = integrations.closest("section") ?? document.body;
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByRole("button", { name: "Connect" })).toBeDefined();
    });
    expect(within(panel as HTMLElement).getAllByText("Not Connected").length).toBeGreaterThan(0);
  });

  it("shows disconnect when Google Drive is connected", async () => {
    mockFetch({ googleConnected: true });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Disconnect" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() => {
      expect(screen.getByText("Google Drive Disconnected.")).toBeDefined();
    });
  });

  it("renders retention patterns from the backend", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("Retention Patterns")).toBeDefined();
    });
    await waitFor(() => {
      expect(screen.getByText(/Lose ~7\.5 Pts/)).toBeDefined();
    });
    expect(screen.getByText(/2 Creatives,/)).toBeDefined();
  });

  it("creates a cohort copying every active filter plus include/exclude lists", async () => {
    const calls = mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Cohort Name")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Cohort Name"), { target: { value: "Beauty" } });
    fireEvent.change(screen.getByLabelText("Include Projects"), { target: { value: "Glow, Vita" } });
    fireEvent.change(screen.getByLabelText("Exclude Projects"), { target: { value: "Nook" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(screen.getByText(/Cohort: Beauty/)).toBeDefined();
    });
    const post = calls.find(([url, init]) => url === "/api/cohorts" && init?.method === "POST");
    expect(post).toBeDefined();
    const body = JSON.parse(String(post?.[1]?.body ?? "{}")) as {
      name: string;
      filters: Record<string, string[]>;
    };
    expect(body.name).toBe("Beauty");
    expect(body.filters["include_projects"]).toEqual(["Glow", "Vita"]);
    expect(body.filters["exclude_projects"]).toEqual(["Nook"]);
  });
});
