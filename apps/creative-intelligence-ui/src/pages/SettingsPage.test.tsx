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

let failGoogleStatus = false;

function mockFetch(opts?: { googleConnected?: boolean; me?: MeResponse; sessions?: number }) {
  const calls: Array<[string, RequestInit | undefined]> = [];
  const googleConnected = opts?.googleConnected ?? false;
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push([url, init]);
    const method = init?.method ?? "GET";
    if (url === "/api/auth/me" && method === "PATCH") {
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, string>;
      return Response.json({ employee: { ...(opts?.me ?? authed).employee, ...body } });
    }
    if (url === "/api/auth/me") return Response.json(opts?.me ?? authed);
    if (url === "/api/auth/me/avatar" && method === "POST") {
      return Response.json({
        employee: { ...(opts?.me ?? authed).employee, avatar_url: "/api/auth/avatar/e1" },
      });
    }
    if (url === "/api/auth/sessions") return Response.json({ count: opts?.sessions ?? 2 });
    if (url === "/api/auth/google/status") {
      if (failGoogleStatus) throw new TypeError("Failed to fetch");
      return Response.json({ connected: googleConnected });
    }
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
    failGoogleStatus = false;
    // This jsdom build exposes no window.localStorage; install a fresh
    // in-memory stand-in so save/load persistence behaves like a browser.
    const store = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
        setItem: (k: string, v: string) => { store.set(k, String(v)); },
        removeItem: (k: string) => { store.delete(k); },
        clear: () => { store.clear(); },
      },
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
    expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value).toBe("Foap Creative Intelligence");
    expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("dark");
    expect((screen.getByLabelText("Accent Color") as HTMLSelectElement).value).toBe("Teal (Default)");
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value).toBe("Comfortable");
    expect(screen.getByText("Notifications")).toBeDefined();
    expect(screen.getByText("Integrations")).toBeDefined();
    expect(screen.getByText("Security")).toBeDefined();
    expect(screen.getByText("Advanced")).toBeDefined();
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDefined();
    // No idle footer text and no reserved status space when clean.
    expect(screen.queryByText("No unsaved changes.")).toBeNull();
    expect(screen.queryByText("Unsaved changes.")).toBeNull();
  });

  it("retires the legacy mock workspace name on load", async () => {
    window.localStorage.setItem("ci-settings-prefs", JSON.stringify({ workspace: "Alex's Workspace" }));
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value)
        .toBe("Foap Creative Intelligence");
    });
  });

  it("preserves an explicitly saved Light preference", async () => {
    window.localStorage.setItem("ci-theme", "light");
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("light");
    });
    // Explicit choice wins over the dark default, before and after save.
    expect(document.documentElement.dataset["theme"] ?? "").toBe("");
    fireEvent.change(screen.getByLabelText("Workspace Name"), { target: { value: "Kept Light" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => {
      expect(screen.getByText("Settings saved.")).toBeDefined();
    });
    expect(window.localStorage.getItem("ci-theme")).toBe("light");
    expect(document.documentElement.dataset["theme"] ?? "").toBe("");
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
      expect(screen.getByText("Settings saved.")).toBeDefined();
    });
    // Preferences persist per signed-in employee (§9).
    expect(window.localStorage.getItem("ci-settings-prefs:e1")).toContain("Night Shift");
    fireEvent.click(screen.getByRole("button", { name: "Reset Defaults" }));
    await waitFor(() => {
      expect(screen.getByText("Defaults restored.")).toBeDefined();
    });
    expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value).toBe("Foap Creative Intelligence");
    // Reset persists defaults under the employee key (never deletes it):
    // a stale legacy global record must not resurface on the next load.
    window.localStorage.setItem(
      "ci-settings-prefs",
      JSON.stringify({ language: "pl", timezone: "Europe/Warsaw", accent: "Violet" }),
    );
    const { loadPrefs } = await import("@/state/prefs");
    expect(loadPrefs("e1").workspace).toBe("Foap Creative Intelligence");
    expect(loadPrefs("e1").language).toBe("en");
  });

  it("stages appearance choices and applies them only on Save", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Theme")).toBeDefined();
    });
    const appliedTeal = document.documentElement.style.getPropertyValue("--shell-teal");
    fireEvent.change(screen.getByLabelText("Accent Color"), { target: { value: "Blue" } });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    // Staged only: live appearance is untouched until Save.
    expect(document.documentElement.style.getPropertyValue("--shell-teal")).toBe(appliedTeal);
    expect(document.documentElement.dataset["theme"] ?? "").toBe("dark");
    const save = screen.getByRole("button", { name: "Save Changes" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => {
      expect(screen.getByText("Settings saved.")).toBeDefined();
    });
    expect(document.documentElement.style.getPropertyValue("--shell-teal")).toBe("#2F6FBE");
    expect(document.documentElement.dataset["theme"] ?? "").toBe("");
  });

  it("sends a password reset email from Security", async () => {
    const calls = mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Change Password" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Change Password" }));
    await waitFor(() => {
      expect(screen.getByText("Password reset email sent.")).toBeDefined();
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
      expect(screen.getByText("All sessions signed out.")).toBeDefined();
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

  it("shows a single Log Out button with one live session", async () => {
    const calls = mockFetch({ sessions: 1 });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Log Out" })).toBeDefined();
    });
    // Exactly one session control: no separate "all sessions" button.
    expect(screen.queryByRole("button", { name: "Log Out All Sessions" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Log Out" }));
    await waitFor(() => {
      expect(calls.some(([url, init]) => url === "/api/auth/logout" && init?.method === "POST")).toBe(true);
    });
    expect(calls.some(([url]) => url === "/api/auth/sessions/revoke-all")).toBe(false);
  });

  it("shows Google Drive as not connected by default", async () => {
    mockFetch({ googleConnected: false });
    renderSettings();
    // The Drive card lives in Connections with a single action area: a
    // Connect button and no Connected badge while disconnected.
    // Scope to the Drive card itself: the Connections panel also holds
    // the always-connected Work Email badge.
    await screen.findByRole("heading", { name: "Connections" });
    const panel = document.getElementById("integration-google") ?? document.body;
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByRole("button", { name: "Connect" })).toBeDefined();
    });
    expect(within(panel as HTMLElement).queryByText("Connected")).toBeNull();
    expect(within(panel as HTMLElement).queryByText(/Status:/)).toBeNull();
  });

  it("shows disconnect when Google Drive is connected", async () => {
    mockFetch({ googleConnected: true });
    renderSettings();
    // Scope to the Drive card itself: the Connections panel also holds
    // the always-connected Work Email badge.
    await screen.findByRole("heading", { name: "Connections" });
    const panel = document.getElementById("integration-google") ?? document.body;
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByRole("button", { name: "Disconnect" })).toBeDefined();
    });
    expect(within(panel as HTMLElement).getByText("Connected")).toBeDefined();
    fireEvent.click(within(panel as HTMLElement).getByRole("button", { name: "Disconnect" }));
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByText("Google Drive Disconnected.")).toBeDefined();
    });
  });

  it("recovers the Drive status check through Retry", async () => {
    failGoogleStatus = true;
    mockFetch({ googleConnected: false });
    renderSettings();
    // Scope to the Drive card itself: the Connections panel also holds
    // the always-connected Work Email badge.
    await screen.findByRole("heading", { name: "Connections" });
    const panel = document.getElementById("integration-google") ?? document.body;
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByRole("button", { name: "Retry" })).toBeDefined();
    });
    expect(within(panel as HTMLElement).getByText("Could not check status.")).toBeDefined();
    failGoogleStatus = false;
    fireEvent.click(within(panel as HTMLElement).getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByRole("button", { name: "Connect" })).toBeDefined();
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

  it("saves first and last name without resending an unchanged avatar", async () => {
    const calls = mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("First Name")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Last Name"), { target: { value: "Lovelace" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));
    await waitFor(() => {
      expect(screen.getByText("Profile saved.")).toBeDefined();
    });
    const patch = calls.find(([url, init]) => url === "/api/auth/me" && init?.method === "PATCH");
    expect(patch).toBeDefined();
    expect(JSON.parse(String(patch?.[1]?.body ?? "{}"))).toEqual({
      first_name: "Ada",
      last_name: "Lovelace",
    });
  });

  it("uploads an avatar file as multipart FormData", async () => {
    const calls = mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Upload Photo")).toBeDefined();
    });
    const file = new File(["bytes"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Upload Photo"), { target: { files: [file] } });
    await waitFor(() => {
      expect(screen.getByText("Profile saved.")).toBeDefined();
    });
    const up = calls.find(([url]) => url === "/api/auth/me/avatar");
    expect(up?.[1]?.method).toBe("POST");
    expect(up?.[1]?.body instanceof FormData).toBe(true);
  });

  it("removes the avatar by clearing it through PATCH", async () => {
    const withAvatar: MeResponse = {
      ...authed,
      employee: { ...employee, avatar_url: "/api/auth/avatar/e1" },
    };
    const calls = mockFetch({ me: withAvatar });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Remove Avatar" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove Avatar" }));
    await waitFor(() => {
      expect(screen.getByText("Avatar removed.")).toBeDefined();
    });
    const patch = calls.find(([url, init]) => url === "/api/auth/me" && init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body ?? "{}"))).toEqual({ avatar_url: "" });
  });

  it("shows the readable employee number instead of the technical id", async () => {
    const numbered: MeResponse = {
      ...authed,
      employee: { ...employee, id: "tech-uuid-9f", employee_no: "EMP-004" },
    };
    mockFetch({ me: numbered });
    renderSettings();
    const heading = await screen.findByRole("heading", { name: "Workspace" });
    const panel = heading.closest("section") ?? document.body;
    await waitFor(() => {
      expect(within(panel as HTMLElement).getByText("EMP-004")).toBeDefined();
    });
    expect(within(panel as HTMLElement).queryByText("tech-uuid-9f")).toBeNull();
    expect(within(panel as HTMLElement).getByRole("button", { name: "Copy employee number" })).toBeDefined();
  });

  it("orders workspace, security, and activity rows per the spec", async () => {
    const dated: MeResponse = {
      ...authed,
      employee: {
        ...employee,
        created_at: "2024-01-02T03:04:05Z",
        approved_at: "2024-01-03T03:04:05Z",
        last_login_at: "2024-02-04T05:06:07Z",
      },
    };
    mockFetch({ me: dated });
    renderSettings();
    const sectionText = async (heading: string) => {
      const h = await screen.findByRole("heading", { name: heading });
      return h.closest("section")?.textContent ?? "";
    };
    for (const [heading, labels] of [
      ["Workspace", ["Employee ID", "Role", "Status", "Work Email", "Last Login", "Account Created"]],
      ["Security", ["Password", "Active Sessions", "Two-Factor Authentication"]],
      ["Recent Activity", ["Account Created", "Access Approved", "Last Signed In"]],
    ] as Array<[string, string[]]>) {
      const text = await sectionText(heading);
      const idx = labels.map((l) => text.indexOf(l));
      expect(idx.every((i) => i >= 0)).toBe(true);
      expect([...idx].sort((a, b) => a - b)).toEqual(idx);
    }
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
