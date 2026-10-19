import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { FilterProvider } from "@/state/FilterContext";
import { useTheme } from "@/app/useTheme";
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

const adminMe: MeResponse = {
  authenticated: true, gate: "app",
  employee: { ...employee, role: "admin" },
  is_admin: true, message: "", workos_configured: true,
};

let failGoogleStatus = false;

function mockFetch(opts?: { googleConnected?: boolean; me?: MeResponse; sessions?: number; cohorts?: typeof cohortsData; deleteFails?: number; rejectEmail?: boolean; rejectProfile?: boolean; serverPrefs?: Record<string, unknown>; conflictPrefs?: Record<string, unknown>; prefsPut?: "conflict-once" | "fail"; prefsGet?: "fail"; holdFirstPut?: { release: () => void }; holdPrefsGet?: { release: () => void }; employeeId?: string; prefsPutGate?: { fail: boolean } }) {
  const meBase: MeResponse = opts?.me ?? authed;
  const me: MeResponse = opts?.employeeId && meBase.employee
    ? { ...meBase, employee: { ...meBase.employee, id: opts.employeeId } }
    : meBase;
  const calls: Array<[string, RequestInit | undefined]> = [];
  const googleConnected = opts?.googleConnected ?? false;
  // Stateful cohort list: DELETE removes the row so a re-fetched
  // list proves the deletion sticks (refresh persistence).
  const deleted = new Set<number>();
  let prefsPuts = 0;
  // Stateful server prefs: PUTs merge-apply like the real endpoint
  // so snapshot/delta behavior across sequential saves is real.
  let storedPrefs: Record<string, unknown> = { ...(opts?.serverPrefs ?? {}) };
  let getWaiters: Array<() => void> = [];
  let getsReleased = !opts?.holdPrefsGet;
  if (opts?.holdPrefsGet) {
    opts.holdPrefsGet.release = () => {
      getsReleased = true;
      const waiters = getWaiters;
      getWaiters = [];
      waiters.forEach((f) => f());
    };
  }
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push([url, init]);
    const method = init?.method ?? "GET";
    if (url === "/api/auth/me" && method === "PATCH") {
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, string>;
      if (opts?.rejectEmail && typeof body.email === "string") {
        return Response.json(
          { detail: { error: "That email is already registered." } },
          { status: 409 },
        );
      }
      if (opts?.rejectProfile) {
        return Response.json({ error: "Could not save profile." }, { status: 500 });
      }
      return Response.json({ employee: { ...me.employee, ...body } });
    }
    if (url === "/api/auth/me") return Response.json(me);
    if (url === "/api/auth/me/avatar" && method === "POST") {
      return Response.json({
        employee: { ...me.employee, avatar_url: "/api/auth/avatar/e1" },
      });
    }
    if (url === "/api/auth/sessions") return Response.json({ count: opts?.sessions ?? 2 });
    if (url === "/api/auth/2fa/status") return Response.json({ enabled: false });
    if (url === "/api/auth/2fa/setup" && method === "POST") {
      return Response.json({ secret: "TESTSECRETKEY", otpauth_uri: "otpauth://totp/x" });
    }
    if (url === "/api/auth/integrations/meta/start" && method === "POST") {
      return Response.json({ error: "Meta Ads is not configured." }, { status: 409 });
    }
    if (/\/api\/auth\/integrations\/(meta|tiktok|ga4)\/status$/.test(url)) {
      return Response.json({ connected: false });
    }
    if (url === "/api/auth/google/status") {
      if (failGoogleStatus) throw new TypeError("Failed to fetch");
      return Response.json({ connected: googleConnected });
    }
    if (url.startsWith("/api/retention/patterns")) return Response.json(patternsData);
    if (url === "/api/cohorts" && method === "GET") {
      return Response.json((opts?.cohorts ?? cohortsData).filter((c) => !deleted.has(c.id)));
    }
    if (url.startsWith("/api/cohorts/") && method === "DELETE") {
      if (opts?.deleteFails) return Response.json({ error: "forbidden" }, { status: opts.deleteFails });
      deleted.add(Number(url.split("/").pop()));
      return Response.json({ ok: true, deleted: "Beauty" });
    }
    if (url.startsWith("/api/cohorts/build")) {
      return Response.json({ name: "Beauty", metric: "cpa", n_ads: 5, status: "ok" });
    }
    if (url === "/api/cohorts" && method === "POST") {
      return Response.json({ id: 3, name: "Beauty", filters: {}, created_at: "" });
    }
    if (url === "/api/preferences" && method === "GET") {
      if (opts?.prefsGet === "fail") {
        return Response.json({ error: "down" }, { status: 500 });
      }
      if (!getsReleased) {
        return new Promise<Response>((resolve) => {
          getWaiters.push(() => resolve(Response.json({ prefs: storedPrefs })));
        });
      }
      return Response.json({ prefs: storedPrefs });
    }
    if (url === "/api/preferences" && method === "PUT") {
      prefsPuts += 1;
      const applyPut = (): Response => {
        if (opts?.prefsPut === "fail" || opts?.prefsPutGate?.fail) {
          return Response.json({ error: "down" }, { status: 500 });
        }
        if (opts?.prefsPut === "conflict-once" && prefsPuts === 1) {
          storedPrefs = { ...(opts?.conflictPrefs ?? {}) };
          return Response.json(
            { error: "preferences changed since they were loaded",
              prefs: storedPrefs },
            { status: 409 });
        }
        const sent = (JSON.parse(String(init?.body ?? "{}")) as {
          prefs?: Record<string, unknown>;
        }).prefs ?? {};
        storedPrefs = {
          ...storedPrefs, ...sent,
          _rev: (typeof storedPrefs["_rev"] === "number"
            ? (storedPrefs["_rev"] as number) : 0) + 1,
        };
        return Response.json({ prefs: storedPrefs });
      };
      if (opts?.holdFirstPut && prefsPuts === 1) {
        return new Promise<Response>((resolve) => {
          opts.holdFirstPut!.release = () => resolve(applyPut());
        });
      }
      return applyPut();
    }
    return Response.json({});
  }) as unknown as typeof fetch;
  return calls;
}

function HeaderThemeToggle() {
  const { toggle } = useTheme();
  return (
    <button type="button" aria-label="Toggle Light And Dark Mode" onClick={toggle}>
      Light/Dark
    </button>
  );
}

function renderSettings(withToggle = false) {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <FilterProvider>
          {withToggle ? <HeaderThemeToggle /> : null}
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
    vi.useRealTimers();
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
    expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("light");
    expect((screen.getByLabelText("Accent Color") as HTMLSelectElement).value).toBe("Teal (Default)");
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value).toBe("Comfortable");
    expect(screen.getByText("Notifications")).toBeDefined();
    expect(screen.getByText("Integrations")).toBeDefined();
    expect(screen.getByText("Security")).toBeDefined();
    expect(screen.getByText("Advanced")).toBeDefined();
    // Autosave: no page-level Save button anywhere.
    expect(screen.queryByRole("button", { name: "Save Changes" })).toBeNull();
    // Reset Defaults lives in the header as a secondary button.
    expect(screen.getByRole("button", { name: "Reset Defaults" })).toBeDefined();
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
    // Explicit choice wins over the light default.
    expect(document.documentElement.dataset["theme"] ?? "").toBe("");
    // Typing a name autosaves (debounced) without any Save click.
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"), { target: { value: "Kept Light" } });
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    await waitFor(() => {
      expect(window.localStorage.getItem("ci-settings-prefs:e1")).toContain("Kept Light");
    });
    expect(window.localStorage.getItem("ci-theme")).toBe("light");
    expect(document.documentElement.dataset["theme"] ?? "").toBe("");
  });

  it("autosaves the workspace name debounced, without a Save button", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"), { target: { value: "Night" } });
    fireEvent.change(screen.getByLabelText("Workspace Name"), { target: { value: "Night Shift" } });
    // Debounce pending: header save status shows, nothing persisted yet.
    // (role=status scopes past LoadingButtons' hidden loading faces.)
    expect(screen.getByRole("status").textContent).toBe("Saving…");
    expect(window.localStorage.getItem("ci-settings-prefs:e1")).toBeNull();
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    // Last write wins: only the final text persisted.
    await waitFor(() => {
      expect(window.localStorage.getItem("ci-settings-prefs:e1")).toContain("Night Shift");
    });
    expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
  });

  it("autosaves toggles and selects immediately with feedback", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Interface Density")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Interface Density"), { target: { value: "Compact" } });
    await waitFor(() => {
      expect(window.localStorage.getItem("ci-settings-prefs:e1")).toContain("Compact");
    });
    expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    expect(document.body.dataset["density"]).toBe("compact");
  });

  it("shows failure with retry when storage throws, keeping the attempted values", async () => {
    const calls = mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Interface Density")).toBeDefined();
    });
    const store = new Map<string, string>();
    const working = {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => { store.set(k, String(v)); },
      removeItem: (k: string) => { store.delete(k); },
      clear: () => { store.clear(); },
    };
    Object.defineProperty(window, "localStorage", {
      value: { ...working, setItem: () => { throw new Error("quota"); } },
      configurable: true, writable: true,
    });
    fireEvent.change(screen.getByLabelText("Interface Density"), { target: { value: "Compact" } });
    // Optimistic UI keeps the attempt visible with an error + Retry.
    expect(await screen.findByText("Could not save settings in this browser.")).toBeDefined();
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value).toBe("Compact");
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    Object.defineProperty(window, "localStorage", {
      value: working, configurable: true, writable: true,
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(store.get("ci-settings-prefs:e1")).toContain("Compact");
    });
    // Local persistence is synchronous; the "saved" status now
    // waits for the async server write — poll for it instead of
    // asserting in the same tick (the old flake's timing gap).
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    // The edit must actually REACH the server on Retry: it was
    // queued before the storage attempt, so Retry's flush sends
    // it even though the re-commit itself diffs to nothing.
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.some((p) => p.prefs["density"] === "Compact")).toBe(true);
  });

  it("validates the workspace name instead of saving blanks", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"), { target: { value: "   " } });
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty.")).toBeDefined();
    expect(window.localStorage.getItem("ci-settings-prefs:e1")).toBeNull();
  });

  it("resets live values from the header button", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Interface Density")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Interface Density"), { target: { value: "Compact" } });
    await waitFor(() => {
      expect(window.localStorage.getItem("ci-settings-prefs:e1")).toContain("Compact");
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset Defaults" }));
    await waitFor(() => {
      expect(screen.getByText("Defaults Restored.")).toBeDefined();
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

  it("applies appearance choices immediately, with no staged state", async () => {
    mockFetch({ employeeId: "e-appear" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Theme")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Accent Color"), { target: { value: "Blue" } });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    // Autosaved at once: live appearance tracks the selects.
    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue("--shell-teal")).toBe("#2F6FBE");
    });
    expect(document.documentElement.dataset["theme"] ?? "").toBe("");
    expect(window.localStorage.getItem("ci-settings-prefs:e-appear")).toContain("Blue");
  });

  it("shows the painted dark theme and returns to light in one step", async () => {
    window.localStorage.setItem("ci-theme", "dark");
    window.localStorage.setItem(
      "ci-settings-prefs:e1",
      JSON.stringify({ theme: "light" }),
    );
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("dark");
    });
    expect(document.documentElement.dataset["theme"]).toBe("dark");
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    await waitFor(() => {
      expect(document.documentElement.dataset["theme"] ?? "").toBe("");
    });
    expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("light");
    expect(window.localStorage.getItem("ci-theme")).toBe("light");
    expect(window.localStorage.getItem("ci-settings-prefs:e1")).toContain('"theme":"light"');
  });

  it("follows a header toggle and still accepts Light", async () => {
    mockFetch();
    renderSettings(true);
    await waitFor(() => {
      expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("light");
    });
    fireEvent.click(screen.getByRole("button", { name: "Toggle Light And Dark Mode" }));
    await waitFor(() => {
      expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("dark");
    });
    expect(document.documentElement.dataset["theme"]).toBe("dark");
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    await waitFor(() => {
      expect(document.documentElement.dataset["theme"] ?? "").toBe("");
    });
    expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("light");
    expect(window.localStorage.getItem("ci-theme")).toBe("light");
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

  it("keeps a failed profile save visible after the button stops", async () => {
    mockFetch({ rejectProfile: true });
    renderSettings();
    await screen.findByRole("button", { name: "Save Profile" });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));
    await waitFor(() => {
      expect(screen.getByText("Could not save profile.")).toBeDefined();
    });
    expect((screen.getByRole("button", { name: "Save Profile" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("does not paint a failed Google check as Connected", async () => {
    failGoogleStatus = true;
    mockFetch({ googleConnected: false });
    renderSettings();
    await screen.findByRole("heading", { name: "Google SSO" });
    const row = screen.getByRole("heading", { name: "Google SSO" }).closest(".insight") as HTMLElement;
    await waitFor(() => {
      expect(within(row).getByText("Could not check status.")).toBeDefined();
    });
    expect(within(row).queryByText("Connected")).toBeNull();
    expect(within(row).queryByText("Not Connected")).toBeNull();
  });

  it("paints Google SSO Not Connected when Drive is disconnected", async () => {
    mockFetch({ googleConnected: false });
    renderSettings();
    await screen.findByRole("heading", { name: "Google SSO" });
    const row = screen.getByRole("heading", { name: "Google SSO" }).closest(".insight") as HTMLElement;
    await waitFor(() => {
      expect(within(row).getByText("Not Connected")).toBeDefined();
    });
    expect(within(row).getByText("Not Connected").className).toContain("pill-bad");
    expect(within(row).queryByText("Connected")).toBeNull();
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
      expect(screen.getByText("Profile Saved.")).toBeDefined();
    });
    const patch = calls.find(([url, init]) => url === "/api/auth/me" && init?.method === "PATCH");
    expect(patch).toBeDefined();
    expect(JSON.parse(String(patch?.[1]?.body ?? "{}"))).toEqual({
      first_name: "Ada",
      last_name: "Lovelace",
    });
  });

  it("edits the email only inside the current domain", async () => {
    const calls = mockFetch();
    renderSettings();
    await screen.findByRole("button", { name: "Edit Email" });
    expect(screen.queryByRole("button", { name: "Edit Profile" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Email Address" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit Email" }));
    const field = screen.getByRole("textbox", { name: "Email Address" });
    expect((field as HTMLInputElement).value).toBe("ada@foap.test");
    expect(screen.getByText("You can change this to another foap.test address.")).toBeDefined();
    fireEvent.change(field, { target: { value: "ada@gmail.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Email" }));
    expect(screen.getByRole("alert").textContent).toBe("Use another foap.test address.");
    expect(calls.some(([url, init]) => url === "/api/auth/me" && init?.method === "PATCH" && String(init.body).includes("email"))).toBe(false);
    fireEvent.change(screen.getByRole("textbox", { name: "Email Address" }), { target: { value: "ada" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Email" }));
    expect(screen.getByRole("alert").textContent).toBe("Enter a valid email address.");
    fireEvent.change(screen.getByRole("textbox", { name: "Email Address" }), { target: { value: "Ada.Desk@Foap.Test" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Email" }));
    await waitFor(() => {
      expect(screen.getByText("Email Saved.")).toBeDefined();
    });
    const patch = calls.find(([url, init]) => url === "/api/auth/me" && init?.method === "PATCH" && String(init.body).includes("email"));
    expect(JSON.parse(String(patch?.[1]?.body ?? "{}"))).toEqual({ email: "ada.desk@foap.test" });
    expect(screen.getAllByText("ada.desk@foap.test")).toHaveLength(3);
    expect(screen.queryByRole("textbox", { name: "Email Address" })).toBeNull();
  });

  it("keeps the current email when the edit is cancelled or unchanged", async () => {
    const calls = mockFetch();
    renderSettings();
    await screen.findByRole("button", { name: "Edit Email" });
    fireEvent.click(screen.getByRole("button", { name: "Edit Email" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Email Address" }), { target: { value: "other@foap.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox", { name: "Email Address" })).toBeNull();
    expect(screen.getAllByText("ada@foap.test")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Edit Email" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Email" }));
    expect(screen.queryByRole("textbox", { name: "Email Address" })).toBeNull();
    expect(calls.some(([url, init]) => url === "/api/auth/me" && init?.method === "PATCH")).toBe(false);
  });

  it("shows a server rejection for an email that is already registered", async () => {
    mockFetch({ rejectEmail: true });
    renderSettings();
    await screen.findByRole("button", { name: "Edit Email" });
    fireEvent.click(screen.getByRole("button", { name: "Edit Email" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Email Address" }), { target: { value: "taken@foap.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Email" }));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("That email is already registered.");
    });
    expect(screen.getAllByText("ada@foap.test")).toHaveLength(2);
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
      expect(screen.getByText("Profile Saved.")).toBeDefined();
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
      expect(screen.getByText("Avatar Removed.")).toBeDefined();
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
    // No copy control: the ID stays visible and aligned, without a button.
    expect(within(panel as HTMLElement).queryByRole("button", { name: "Copy employee number" })).toBeNull();
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

  it("offers two-factor setup and integration connect", async () => {
    mockFetch();
    renderSettings();
    const securityHeading = await screen.findByRole("heading", { name: "Security" });
    const security = securityHeading.closest("section") as HTMLElement;
    expect(await within(security).findByRole("button", { name: "Set Up" })).toBeDefined();
    expect(within(security).queryByText("Unavailable")).toBeNull();
    fireEvent.click(within(security).getByRole("button", { name: "Set Up" }));
    expect((await screen.findByTestId("totp-secret")).textContent).toBe("TESTSECRETKEY");
    const integrations = (await screen.findByRole("heading", { name: "Integrations" })).closest("section") as HTMLElement;
    expect(within(integrations).queryByText("Unavailable")).toBeNull();
    fireEvent.click(within(integrations).getByRole("button", { name: "Connect Meta Ads" }));
    expect(await within(integrations).findByText("Meta Ads is not configured.")).toBeDefined();
    expect(within(integrations).getByRole("button", { name: "Connect TikTok Ads" })).toBeDefined();
    expect(within(integrations).getByRole("button", { name: "Connect Google Analytics 4" })).toBeDefined();
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

  it("deletes a cohort as admin and clears its displayed result", async () => {
    const calls = mockFetch({ me: adminMe });
    window.confirm = vi.fn(() => true);
    renderSettings();
    // Build first so a result is displayed for this cohort …
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Build" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Build" }));
    await waitFor(() => {
      expect(screen.getByText(/Cohort: Beauty/)).toBeDefined();
    });
    // … then delete it.
    fireEvent.click(screen.getByRole("button", { name: "Delete cohort Beauty" }));
    await waitFor(() => {
      expect(screen.getByText("Cohort Beauty deleted.")).toBeDefined();
    });
    expect(calls.some(([url, init]) => url === "/api/cohorts/3" && init?.method === "DELETE")).toBe(true);
    // List and displayed result update together …
    expect(screen.queryByText(/Cohort: Beauty/)).toBeNull();
    expect(screen.getByText("No Saved Cohorts Yet.")).toBeDefined();
  });

  it("keeps a cohort when the delete confirmation is dismissed", async () => {
    const calls = mockFetch({ me: adminMe });
    window.confirm = vi.fn(() => false);
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete cohort Beauty" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete cohort Beauty" }));
    await new Promise((r) => setTimeout(r, 50));
    expect(calls.some(([url]) => url === "/api/cohorts/3")).toBe(false);
    expect(screen.getByText("Beauty")).toBeDefined();
  });

  it("hides cohort delete for non-admins", async () => {
    mockFetch();
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Build" })).toBeDefined();
    });
    expect(screen.queryByRole("button", { name: "Delete cohort Beauty" })).toBeNull();
  });

  it("surfaces delete permission failures visibly", async () => {
    mockFetch({ me: adminMe, deleteFails: 403 });
    window.confirm = vi.fn(() => true);
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete cohort Beauty" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete cohort Beauty" }));
    await waitFor(() => {
      expect(screen.getByText("Only administrators can delete cohorts.")).toBeDefined();
    });
    // Failed delete keeps the row.
    expect(screen.getByText("Beauty")).toBeDefined();
  });

  const fullServerPrefs = {
    workspace: "Foap Creative Intelligence", default_view: "Dashboard",
    default_currency: "USD – US Dollar", default_date_range: "Last 30 Days",
    default_campaign_view: "All Campaigns", theme: "light",
    accent: "Teal (Default)", density: "Compact", language: "en",
    timezone: "Europe/London", email_reports: true, campaign_updates: true,
    ai_insights: true, product_updates: false, data_usage: true,
    share_analytics: true, retention: "24 Months", _rev: 3,
  };

  it("reconciles a cross-tab conflict, retrying only its changed keys", async () => {
    // Another tab moved density to Comfortable at _rev 9 after
    // this tab loaded _rev 3 (density Compact).
    const conflictPrefs = { ...fullServerPrefs, density: "Comfortable", _rev: 9 };
    const calls = mockFetch({
      serverPrefs: fullServerPrefs, prefsPut: "conflict-once", conflictPrefs,
      employeeId: "e-conflict",
    });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Compact");
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>; base_revision: number;
      });
    expect(puts).toHaveLength(2);
    expect(puts[0]!.base_revision).toBe(3);
    expect(puts[0]!.prefs).toEqual({ theme: "dark" });
    expect(puts[1]!.base_revision).toBe(9);
    // Density is never re-sent: the other tab's newer value survives.
    expect(puts[1]!.prefs).toEqual({ theme: "dark" });
    // The form RECONCILES with the confirmed server state: the
    // other tab's density now shows here too…
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Comfortable");
    });
    // …and the NEXT unrelated edit still cannot resurrect the
    // stale density: it sends only its own changed key.
    fireEvent.change(screen.getByLabelText("Accent Color"),
                     { target: { value: "Blue" } });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts2 = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts2[puts2.length - 1]!.prefs).toEqual({ accent: "Blue" });
  });

  it("editing before preferences hydrate sends only the changed key", async () => {
    // Server holds saved prefs, but every GET fails: the tab has
    // no snapshot when the user edits. The write must still be
    // the single changed key, never the whole local document.
    const calls = mockFetch({ serverPrefs: fullServerPrefs, prefsGet: "fail", employeeId: "e-hydrate" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Theme")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.length).toBeGreaterThanOrEqual(1);
    expect(puts[puts.length - 1]!.prefs).toEqual({ theme: "dark" });
  });

  it("Reset Defaults resets keys another tab changed too", async () => {
    const mine = { ...fullServerPrefs, theme: "dark", density: "Comfortable" };
    const conflictPrefs = { ...mine, density: "Compact", _rev: 9 };
    const calls = mockFetch({
      serverPrefs: mine, prefsPut: "conflict-once", conflictPrefs,
      employeeId: "e-resetx",
    });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Theme") as HTMLSelectElement).value).toBe("dark");
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset Defaults" }));
    // Reset also raises a toast with role=status; match any.
    await waitFor(() => {
      expect(screen.getAllByRole("status")
        .some((el) => el.textContent === "All Changes Saved.")).toBe(true);
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    const last = puts[puts.length - 1]!.prefs;
    // Full-document replace: density returns to the default even
    // though this tab's snapshot already showed it as default.
    expect(last["density"]).toBe("Comfortable");
    expect(last["theme"]).toBe("light");
  });

  it("a revert queued behind an in-flight save still lands", async () => {
    const hold = { release: () => {} };
    const calls = mockFetch({ serverPrefs: fullServerPrefs, holdFirstPut: hold, employeeId: "e-qrev" });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Compact");
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    await waitFor(() => {
      expect(calls.some(([u, i]) =>
        u === "/api/preferences" && (i?.method ?? "GET") === "PUT")).toBe(true);
    });
    // First PUT still held: queue the revert behind it.
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    hold.release();
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.map((p) => p.prefs)).toEqual([{ theme: "dark" }, { theme: "light" }]);
  });

  it("a newer edit returning to the in-flight value is still sent", async () => {
    const hold = { release: () => {} };
    const calls = mockFetch({ serverPrefs: fullServerPrefs, holdFirstPut: hold, employeeId: "e-repeat" });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Compact");
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    await waitFor(() => {
      expect(calls.some(([u, i]) =>
        u === "/api/preferences" && (i?.method ?? "GET") === "PUT")).toBe(true);
    });
    // While Dark is in flight: Light, then Dark again. The
    // delayed Dark response must not "confirm" the re-selection.
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    hold.release();
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.map((p) => p.prefs)).toEqual([{ theme: "dark" }, { theme: "dark" }]);
  });

  it("edits combined into one flush still reconcile the form", async () => {
    // Fresh tab: server density Compact, form shows the local
    // Comfortable default while every preferences GET is held.
    const holdGet = { release: () => {} };
    mockFetch({ serverPrefs: fullServerPrefs, holdPrefsGet: holdGet, employeeId: "e-combined" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Theme")).toBeDefined();
    });
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
      .toBe("Comfortable");
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    fireEvent.change(screen.getByLabelText("Accent Color"),
                     { target: { value: "Blue" } });
    holdGet.release();
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    // Both edits rode one flush; the second commit's (empty)
    // flush must still reconcile: the form adopts Compact.
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Compact");
    });
  });

  it("an edit followed by a revert lands as the reverted value", async () => {
    const calls = mockFetch({ serverPrefs: fullServerPrefs, employeeId: "e-erev" });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Compact");
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "light" } });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.length).toBeGreaterThanOrEqual(2);
    // The revert is a real delta against the post-edit snapshot,
    // not an empty write that would leave "dark" on the server.
    expect(puts[puts.length - 1]!.prefs).toEqual({ theme: "light" });
  });

  it("typing a workspace name survives an unrelated control change", async () => {
    const calls = mockFetch({ employeeId: "e-name" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "Night Shift" } });
    // Unrelated commit inside the 450ms debounce window: it must
    // neither reset the input nor invalidate the name timer.
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value)
      .toBe("Night Shift");
    // The density write completes inside the window, but the
    // status must NOT claim saved while the name is still an
    // uncommitted draft.
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.getByRole("status").textContent).toBe("Saving…");
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    expect(window.localStorage.getItem("ci-settings-prefs:e-name"))
      .toContain("Night Shift");
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.some((p) => p.prefs["workspace"] === "Night Shift")).toBe(true);
    expect(puts.some((p) => p.prefs["density"] === "Compact")).toBe(true);
  });

  it("Reset Defaults cancels a pending workspace-name edit", async () => {
    const calls = mockFetch({ employeeId: "e-resetname" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    // Saved name already IS the default: only the timer can
    // resurrect the typed draft after Reset — it must be dead.
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "Typed Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset Defaults" }));
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    await waitFor(() => {
      expect(screen.getAllByRole("status")
        .some((el) => el.textContent === "All Changes Saved.")).toBe(true);
    });
    expect((screen.getByLabelText("Workspace Name") as HTMLInputElement).value)
      .toBe("Foap Creative Intelligence");
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.some((p) => p.prefs["workspace"] === "Typed Name")).toBe(false);
    expect(puts.some((p) => p.prefs["workspace"] === "Foap Creative Intelligence"))
      .toBe(true);
  });

  it("reopening Settings during a save does not undo the saved value", async () => {
    const mine = { ...fullServerPrefs, density: "Comfortable", _rev: 1000 };
    const hold = { release: () => {} };
    const calls = mockFetch({ serverPrefs: mine, holdFirstPut: hold, employeeId: "e-remount" });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Comfortable");
    });
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    await waitFor(() => {
      expect(calls.some(([u, i]) =>
        u === "/api/preferences" && (i?.method ?? "GET") === "PUT")).toBe(true);
    });
    cleanup(); // navigate away while the PUT is in flight
    renderSettings(); // reopen: its GET still reads Comfortable
    await waitFor(() => {
      expect(calls.filter(([u, i]) =>
        u === "/api/preferences" && (i?.method ?? "GET") === "GET").length)
        .toBeGreaterThanOrEqual(2);
    });
    // The reopened page must not let that GET undo the edit.
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
      .toBe("Compact");
    hold.release();
    fireEvent.change(screen.getByLabelText("Accent Color"),
                     { target: { value: "Blue" } });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
      .toBe("Compact");
  });

  it("blank-name validation does not hide another save's failure", async () => {
    mockFetch({ prefsPut: "fail", employeeId: "e-blankfail" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    // The density PUT fails inside the debounce window.
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    // The blank-name validation fires: it owns the name error
    // only and must not clear the persistence failure / Retry.
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty."))
      .toBeDefined();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    expect(screen.getByRole("status").textContent)
      .toBe("Could not save settings in this browser.");
  });

  it("a successful save after blank-name validation does not stick on Saving", async () => {
    const hold = { release: () => {} };
    mockFetch({ holdFirstPut: hold, employeeId: "e-blankok" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    // Validation fires while the density PUT is still held.
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty."))
      .toBeDefined();
    hold.release();
    // The committed change IS saved (the blank draft is invalid
    // input owned by its own message, not an unsaved change).
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    expect(screen.getByText("Workspace name cannot be empty.")).toBeDefined();
  });

  it("clearing the name during a save does not hide its failure", async () => {
    const hold = { release: () => {} };
    const calls = mockFetch({
      prefsPut: "fail", holdFirstPut: hold, employeeId: "e-blankrev",
    });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    // Density first: its PUT is in flight (held)…
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    await vi.advanceTimersByTimeAsync(0);
    expect(calls.some(([u, i]) =>
      u === "/api/preferences" && (i?.method ?? "GET") === "PUT")).toBe(true);
    // …then the name is cleared (a keystroke, not a commit)…
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "   " } });
    // …then the PUT fails, and the validation timer fires.
    hold.release();
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty."))
      .toBeDefined();
    // The failure was RECORDED despite the intervening keystroke:
    // validation restores the error instead of stranding Saving.
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    expect(screen.getByRole("status").textContent)
      .toBe("Could not save settings in this browser.");
  });

  it("a save succeeding after blank-name validation settles the status", async () => {
    const hold = { release: () => {} };
    mockFetch({ holdFirstPut: hold, employeeId: "e-blanklate" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "   " } });
    // Validation fires while the PUT is still held…
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty."))
      .toBeDefined();
    // …then the PUT succeeds: its settle must still land even
    // though a keystroke intervened after the commit.
    hold.release();
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    expect(screen.getByText("Workspace name cannot be empty.")).toBeDefined();
  });

  it("an older success cannot erase a newer storage failure", async () => {
    const hold = { release: () => {} };
    const calls = mockFetch({ holdFirstPut: hold, employeeId: "e-oldwin" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Workspace Name")).toBeDefined();
    });
    vi.useFakeTimers();
    // 1) Density save starts; its PUT is held in flight.
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    await vi.advanceTimersByTimeAsync(0);
    expect(calls.some(([u, i]) =>
      u === "/api/preferences" && (i?.method ?? "GET") === "PUT")).toBe(true);
    // 2) Accent commit while local storage is failing: the
    //    synchronous failure shows Error + Retry immediately.
    const store = new Map<string, string>();
    const working = {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => { store.set(k, String(v)); },
      removeItem: (k: string) => { store.delete(k); },
      clear: () => { store.clear(); },
    };
    Object.defineProperty(window, "localStorage", {
      value: { ...working, setItem: () => { throw new Error("quota"); } },
      configurable: true, writable: true,
    });
    fireEvent.change(screen.getByLabelText("Accent Color"),
                     { target: { value: "Blue" } });
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    Object.defineProperty(window, "localStorage", {
      value: working, configurable: true, writable: true,
    });
    // 3) The OLDER density PUT now succeeds — it must not erase
    //    the newer failure on record.
    hold.release();
    await vi.advanceTimersByTimeAsync(0);
    // 4) Clearing the name + validation must still show Retry.
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "   " } });
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty."))
      .toBeDefined();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    expect(screen.getByRole("status").textContent)
      .toBe("Could not save settings in this browser.");
    // And Retry really does flush the stranded accent change.
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts.some((p) => p.prefs["accent"] === "Blue")).toBe(true);
  });

  it("reopening Settings after a failed save restores recovery", async () => {
    const gate = { fail: true };
    const calls = mockFetch({ prefsPutGate: gate, employeeId: "e-reopen" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Interface Density")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Interface Density"),
                     { target: { value: "Compact" } });
    expect(await screen.findByRole("button", { name: "Retry" })).toBeDefined();
    cleanup(); // navigate away with the edit still unsent
    renderSettings(); // reopen: recovery retries, still fails
    expect(await screen.findByRole("button", { name: "Retry" })).toBeDefined();
    expect(screen.getByRole("status").textContent)
      .toBe("Could not save settings in this browser.");
    // Clearing the name must not strand the status either.
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Workspace Name"),
                     { target: { value: "   " } });
    await vi.advanceTimersByTimeAsync(600);
    vi.useRealTimers();
    expect(await screen.findByText("Workspace name cannot be empty."))
      .toBeDefined();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
    // Server recovers: Retry flushes the stranded density edit.
    gate.fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("All Changes Saved.");
    });
    const puts = calls
      .filter(([u, i]) => u === "/api/preferences" && (i?.method ?? "GET") === "PUT")
      .map(([, i]) => JSON.parse(String(i?.body ?? "{}")) as {
        prefs: Record<string, unknown>;
      });
    expect(puts[puts.length - 1]!.prefs).toEqual({ density: "Compact" });
  });

  it("a delayed previous-account response cannot repaint the new account", async () => {
    const holdGet = { release: () => {} };
    // Account A: Blue accent + Compact; its GET is held.
    mockFetch({
      serverPrefs: {
        ...fullServerPrefs, accent: "Blue", density: "Compact", _rev: 50,
      },
      holdPrefsGet: holdGet, employeeId: "e-acc-a",
    });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Interface Density")).toBeDefined();
    });
    cleanup(); // leave A (its GET still in flight)
    // Account B loads normally with its own prefs.
    mockFetch({
      serverPrefs: {
        ...fullServerPrefs, accent: "Teal (Default)",
        density: "Comfortable", _rev: 50,
      },
      employeeId: "e-acc-b",
    });
    renderSettings();
    await waitFor(() => {
      expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
        .toBe("Comfortable");
    });
    // A's delayed response finally arrives: it must not apply
    // A's live appearance (accent/density) over B's session.
    await act(async () => { holdGet.release(); });
    expect((screen.getByLabelText("Interface Density") as HTMLSelectElement).value)
      .toBe("Comfortable");
    expect(document.body.dataset["density"]).not.toBe("compact");
    expect(document.documentElement.style.getPropertyValue("--shell-teal"))
      .not.toBe("#2F6FBE");
  });

  it("does not claim saved when the server rejects the write", async () => {
    mockFetch({ prefsPut: "fail" });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByLabelText("Theme")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });
    expect(await screen.findByText("Could not save settings in this browser."))
      .toBeDefined();
    expect(screen.getByRole("status").textContent).not.toBe("All Changes Saved.");
  });
});
