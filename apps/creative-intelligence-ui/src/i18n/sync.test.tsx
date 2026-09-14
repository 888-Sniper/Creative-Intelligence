import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { LocalePrefsSync, LocaleProvider, useLocale } from "@/i18n";
import type { MeResponse } from "@/types/auth";

const employee = {
  id: "e9", email: "jan@foap.test", first_name: "Jan", last_name: "K",
  avatar_url: "", provider: "email", role: "employee", status: "active",
  created_at: "", approved_at: "", approved_by: "", last_login_at: "", updated_at: "",
};

function meFor(id: string): MeResponse {
  return {
    authenticated: true, gate: "app", is_admin: false, message: "",
    workos_configured: true, employee: { ...employee, id },
  };
}

function Probe() {
  const { t, timezone } = useLocale();
  return (
    <div>
      <span data-testid="nav-settings">{t("nav.settings")}</span>
      <span data-testid="tz">{timezone}</span>
    </div>
  );
}

function renderSync() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LocaleProvider>
          <LocalePrefsSync />
          <Probe />
        </LocaleProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LocalePrefsSync", () => {
  beforeEach(() => {
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

  it("applies the signed-in employee's saved language and timezone on startup", async () => {
    window.localStorage.setItem(
      "ci-settings-prefs:e9",
      JSON.stringify({ language: "pl", timezone: "Europe/Warsaw" }),
    );
    window.fetch = vi.fn(async () => Response.json(meFor("e9"))) as unknown as typeof fetch;
    renderSync();
    await waitFor(() => {
      expect(screen.getByTestId("nav-settings").textContent).toBe("Ustawienia");
    });
    expect(screen.getByTestId("tz").textContent).toBe("Europe/Warsaw");
  });

  it("falls back to English defaults when the employee saved nothing", async () => {
    window.fetch = vi.fn(async () => Response.json(meFor("e9"))) as unknown as typeof fetch;
    renderSync();
    await waitFor(() => {
      expect(screen.getByTestId("nav-settings").textContent).toBe("Settings");
    });
  });
});
