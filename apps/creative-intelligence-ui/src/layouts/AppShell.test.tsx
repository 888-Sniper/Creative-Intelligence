import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { FilterProvider } from "@/state/FilterContext";
import { AppShell } from "@/layouts/AppShell";

const employee = {
  id: "e1", email: "ada@foap.test", first_name: "Ada", last_name: "L",
  avatar_url: "", provider: "email", role: "employee", status: "active",
  created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "",
};

function mockFetch() {
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url === "/api/auth/me") {
      return Response.json({
        authenticated: true, gate: "app", employee, is_admin: false,
        message: "", workos_configured: true,
      });
    }
    if (url === "/api/auth/sessions") return Response.json({ count: 1 });
    return Response.json({});
  }) as unknown as typeof fetch;
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <FilterProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<p>Page body</p>} />
            </Route>
          </Routes>
        </FilterProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("AppShell desktop collapse", () => {
  beforeEach(() => {
    mockFetch();
    // This jsdom build exposes no window.localStorage; install a
    // fresh in-memory stand-in (same approach as SettingsPage.test).
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
  });

  it("collapses and expands with an accessible toggle", () => {
    renderShell();
    const toggle = screen.getByRole("button", { name: "Collapse Sidebar" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const aside = screen.getByLabelText("Primary");
    expect(aside.className).not.toContain("collapsed");
    fireEvent.click(toggle);
    expect(aside.className).toContain("collapsed");
    expect(screen.getByRole("button", { name: "Expand Sidebar" }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Expand Sidebar" }));
    expect(aside.className).not.toContain("collapsed");
  });

  it("renders the wordmark plus a collapsed-rail mark", () => {
    renderShell();
    const brand = screen.getByRole("link", { name: "Foap Creative Intelligence Dashboard" });
    const full = within(brand).getByAltText("Foap") as HTMLImageElement;
    expect(full.getAttribute("src")).toBe("/foap-logo.png");
    // The icon-only mark rides along for the collapsed rail (CSS picks
    // the visible one); it stays out of the accessible name.
    const mark = brand.querySelector("img.brand-mark") as HTMLImageElement;
    expect(mark.getAttribute("src")).toBe("/foap-mark.png");
    expect(mark.getAttribute("aria-hidden")).toBe("true");
  });

  it("keeps every nav link usable while collapsed", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Collapse Sidebar" }));
    const aside = screen.getByLabelText("Primary");
    for (const name of ["Dashboard", "Campaigns", "AI Analyst", "Settings"]) {
      const link = within(aside).getByRole("link", { name });
      expect(link.getAttribute("href")).toBeTruthy();
    }
    // Content column still renders beside the rail.
    expect(screen.getByText("Page body")).toBeDefined();
    expect(document.querySelector(".shell")?.className).toContain("shell-collapsed");
  });

  it("persists collapse across remounts", () => {
    const first = renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Collapse Sidebar" }));
    expect(window.localStorage.getItem("ci-shell-collapsed")).toBe("1");
    first.unmount();
    renderShell();
    expect(screen.getByLabelText("Primary").className).toContain("collapsed");
    expect(screen.getByRole("button", { name: "Expand Sidebar" })).toBeDefined();
  });

  it("leaves the mobile drawer independent", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Collapse Sidebar" }));
    const aside = screen.getByLabelText("Primary");
    // Drawer opens on top of the collapsed rail …
    fireEvent.click(screen.getByRole("button", { name: "Open Menu" }));
    expect(aside.className).toContain("open");
    expect(aside.className).toContain("collapsed");
    // … and closes without expanding the rail.
    fireEvent.click(screen.getByRole("button", { name: "Close Menu" }));
    expect(aside.className).not.toContain("open");
    expect(aside.className).toContain("collapsed");
  });
});
