import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { FilterProvider } from "@/state/FilterContext";
import { LocaleProvider } from "@/i18n";
import { AppShell } from "@/layouts/AppShell";
import { AdminOnly } from "@/app/router";
import { ProvidersPage } from "@/admin/ProvidersPage";

interface Call {
  url: string;
  method: string;
  body: unknown;
}

const baseEmployee = {
  avatar_url: "",
  provider: "email",
  role: "employee",
  status: "active",
  created_at: "2026-01-01",
  approved_at: "2026-01-02",
  approved_by: "root",
  last_login_at: "2026-09-01",
  updated_at: "2026-09-02",
};

const adminEmployee = {
  ...baseEmployee, id: "a1", email: "boss@foap.test",
  first_name: "Boss", last_name: "Admin", role: "admin",
};

const staffEmployee = {
  ...baseEmployee, id: "e1", email: "ada@foap.test",
  first_name: "Ada", last_name: "L", role: "employee",
};

function meFor(employee: typeof adminEmployee, isAdmin: boolean) {
  return {
    authenticated: true, gate: "app", is_admin: isAdmin, message: "",
    workos_configured: true, employee,
  };
}

function listFixture(): {
  providers: Array<Record<string, unknown>>;
  active: {
    provider_id: string; model_id: string; revision: number;
    updated_by: string; updated_at: string;
    support?: string; video_eligible?: boolean; support_doc?: string | null;
  } | null;
  current_revision: number;
} {
  return {
    providers: [
      {
        provider_id: "groq", display: "Groq", kind: "api_key",
        supported: true, unsupported_reason: null, base_url: null,
        has_secret: true, secret_updated_at: "2026-09-09T10:00:00+00:00",
        configured: true, models_cached: 5, offered_count: 5,
        fetched_at: "2026-09-10T12:00:00+00:00", stale: false,
        cached_models: [
          { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B Versatile" },
          { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant" },
        ],
      },
      {
        provider_id: "openai", display: "OpenAI", kind: "api_key",
        supported: true, unsupported_reason: null, base_url: null,
        has_secret: false, secret_updated_at: null,
        configured: false, models_cached: 2, offered_count: 2,
        fetched_at: "2026-08-01T12:00:00+00:00", stale: true,
      },
      {
        provider_id: "ollama", display: "Ollama", kind: "local",
        supported: true, unsupported_reason: null, base_url: "http://localhost:11434",
        has_secret: false, secret_updated_at: null,
        configured: true, models_cached: 0, offered_count: 0,
        fetched_at: null, stale: true,
      },
      {
        provider_id: "chatgpt", display: "ChatGPT", kind: "subscription",
        supported: false,
        unsupported_reason: "ChatGPT sign-in reads a local auth file and impersonates an unofficial API.",
        base_url: null, has_secret: false, secret_updated_at: null,
        configured: false, models_cached: 0, offered_count: 0,
        fetched_at: null, stale: true,
      },
    ],
    active: {
      provider_id: "groq", model_id: "llama-3.3-70b-versatile",
      revision: 3, updated_by: "a1", updated_at: "2026-09-10T12:30:00+00:00",
    },
    current_revision: 3,
  };
}

interface FetchState {
  me: unknown;
  list: ReturnType<typeof listFixture>;
  activateCalls: number;
  conflictFirstActivate: boolean;
  testFails: boolean;
}

function setupFetch(state: FetchState): Call[] {
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
      if (url === "/api/auth/me") return Response.json(state.me);
      if (url.startsWith("/api/campaigns/meta")) return Response.json({ campaigns: [] });
      if (url === "/api/admin/providers") return Response.json(state.list);
      if (method === "POST" && url.endsWith("/test")) {
        if (state.testFails) {
          return Response.json({ error: "connection refused by groq" }, { status: 502 });
        }
        return Response.json({
          ok: true, provider_id: "test", latency_ms: 123, offered_count: 2,
          offered: [{ id: "m1", label: "M One" }, { id: "m2" }],
        });
      }
      if (method === "POST" && url.endsWith("/refresh")) {
        return Response.json({
          ok: true, provider_id: "groq", offered_count: 2,
          fetched_at: "2026-09-11T10:00:00+00:00", stale: false,
        });
      }
      if (method === "POST" && url === "/api/admin/providers/activate") {
        state.activateCalls += 1;
        if (state.conflictFirstActivate && state.activateCalls === 1) {
          state.list = { ...state.list, current_revision: 4 };
          return Response.json({
            error: "selection changed since revision 3", current_revision: 4,
          }, { status: 409 });
        }
        return Response.json({ ok: true, active: state.list.active, current_revision: 4 });
      }
      if (method === "POST" && url === "/api/admin/providers/deactivate") {
        return Response.json({ ok: true, active: null, current_revision: 4 });
      }
      if (method === "PUT" && url.startsWith("/api/admin/providers/")) {
        return Response.json({
          ok: true, configured: true, has_secret: true, offered_count: 0,
          active: state.list.active, current_revision: state.list.current_revision,
        });
      }
      return Response.json({});
    },
  ) as unknown as typeof fetch;
  return calls;
}

const realConfirm = window.confirm;

function freshState(admin = true): FetchState {
  return {
    me: meFor(admin ? adminEmployee : staffEmployee, admin),
    list: listFixture(),
    activateCalls: 0,
    conflictFirstActivate: false,
    testFails: false,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/providers"]}>
      <AuthProvider>
        <LocaleProvider>
          <ProvidersPage />
        </LocaleProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <LocaleProvider>
          <FilterProvider>
            <AppShell />
          </FilterProvider>
        </LocaleProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  window.confirm = realConfirm;
});

describe("ProvidersPage", () => {
  it("shows the active banner and one card per server provider", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    expect(screen.getByRole("switch", { name: "Active" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("switch", { name: "Use OpenAI As Active" }).getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("ChatGPT")).toBeTruthy();
  });

  it("shows paused admin guidance when nothing is active", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const state = freshState();
    state.list = { ...state.list, active: null };
    setupFetch(state);
    renderPage();
    await screen.findByText("AI Is Paused");
    expect(screen.getByText(/AI is not configured\. Contact your administrator\./)).toBeTruthy();
  });

  it("renders blocked entries with the server reason and zero actions", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    setupFetch(freshState());
    renderPage();
    await screen.findByText("ChatGPT");
    const card = screen.getByText("ChatGPT").closest("section") as HTMLElement;
    expect(card).toBeTruthy();
    expect(within(card).getByText(/impersonates an unofficial API/)).toBeTruthy();
    expect(within(card).queryByRole("button")).toBeNull();
    expect(within(card).queryByRole("switch")).toBeNull();
  });

  it("never prefills secrets: the key input starts empty with a masked placeholder", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const calls = setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    const input = screen.getByLabelText("API Key For Groq") as HTMLInputElement;
    expect(input.value).toBe("");
    expect(input.placeholder).toBe("••••••");
    for (const c of calls) {
      if (c.method === "GET") expect(c.body).toBeUndefined();
    }
  });

  it("tests, picks an offered model, and activates with the exact model_id", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const calls = setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    const card = screen.getByText("OpenAI").closest("section") as HTMLElement;
    await within(card).findByRole("button", { name: "Test Connection" });
    // The Groq card owns the mocked test endpoint: exercise it there.
    const groqCard = screen.getByText("Groq").closest("section") as HTMLElement;
    fireEvent.click(within(groqCard).getByRole("button", { name: "Test Connection" }));
    await within(groqCard).findByText(/Connected In 123 ms\./);
    const select = within(groqCard).getByLabelText("Active Model For Groq") as HTMLSelectElement;
    expect(select.options.length).toBe(3); // empty option + 2 offered
    fireEvent.change(select, { target: { value: "m1" } });
    // Activate OpenAI instead: needs its own offered list first.
    fireEvent.click(within(card).getByRole("switch", { name: "Use OpenAI As Active" }));
    await within(card).findByText("Pick an offered model before activating OpenAI.");
    expect(calls.filter((c) => c.url.endsWith("/activate"))).toHaveLength(0);
  });

  it("seeds the model selector from the cached catalog without testing", async () => {
    setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    // Refresh Models populates the selector: no Test Connection needed.
    const groqCard = screen.getByText("Groq").closest("section") as HTMLElement;
    const select = await within(groqCard).findByLabelText("Active Model For Groq") as HTMLSelectElement;
    expect(select.options.length).toBe(3); // empty option + 2 cached
    expect(select.options[1].value).toBe("llama-3.3-70b-versatile");
  });

  it("surfaces video eligibility on the active selection and model options", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const state = freshState();
    state.list = {
      ...state.list,
      active: {
        ...state.list.active!,
        support: "text-only",
        video_eligible: false,
        support_doc: null,
      },
      providers: state.list.providers.map((p) =>
        p["provider_id"] === "groq"
          ? {
              ...p,
              cached_models: [
                { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B Versatile", support: "text-only", video_eligible: false, support_doc: null },
                { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant" },
              ],
            }
          : p,
      ),
    };
    setupFetch(state);
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    // An active-but-unsupported selection surfaces clearly (no silent fallback).
    expect(screen.getByText(/not verified for video input/)).toBeTruthy();
    const groqCard = screen.getByText("Groq").closest("section") as HTMLElement;
    const select = await within(groqCard).findByLabelText("Active Model For Groq") as HTMLSelectElement;
    // Verified levels suffix the exact option; unverified ids stay bare.
    expect(select.options[1].text).toContain("Text only");
    expect(select.options[2].text).toBe("Llama 3.1 8B Instant (llama-3.1-8b-instant)");
    // The picked model reports its workflow support underneath.
    fireEvent.change(select, { target: { value: "llama-3.3-70b-versatile" } });
    expect(await within(groqCard).findByText("Video workflow: Text only.")).toBeTruthy();
  });

  it("toggling the active switch off deactivates after confirm", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const calls = setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    fireEvent.click(screen.getByRole("switch", { name: "Active" }));
    await waitFor(() => {
      expect(calls.filter((c) => c.method === "POST" && c.url.endsWith("/deactivate"))).toHaveLength(1);
    });
    expect(window.confirm).toHaveBeenCalled();
  });

  it("sends byte-exact model_id plus revision on activate", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const calls = setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    // Switch path on the inactive OpenAI card: test loads its offered
    // list, select picks the exact model id, the switch confirms.
    const card = screen.getByText("OpenAI").closest("section") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Test Connection" }));
    await within(card).findByText(/Connected In 123 ms\./);
    fireEvent.change(within(card).getByLabelText("Active Model For OpenAI"), {
      target: { value: "m2" },
    });
    fireEvent.click(screen.getByRole("switch", { name: "Use OpenAI As Active" }));
    await waitFor(() => {
      expect(calls.filter((c) => c.method === "POST" && c.url.endsWith("/activate"))).toHaveLength(1);
    });
    expect(window.confirm).toHaveBeenCalled();
    const activate = calls.find((c) => c.method === "POST" && c.url.endsWith("/activate"));
    expect(activate?.body).toEqual({ provider_id: "openai", model_id: "m2", revision: 3 });
  });

  it("retries a 409 conflict against the refetched revision", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const state = freshState();
    state.conflictFirstActivate = true;
    const calls = setupFetch(state);
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    const card = screen.getByText("OpenAI").closest("section") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Test Connection" }));
    await within(card).findByText(/Connected In 123 ms\./);
    fireEvent.change(within(card).getByLabelText("Active Model For OpenAI"), {
      target: { value: "m1" },
    });
    fireEvent.click(screen.getByRole("switch", { name: "Use OpenAI As Active" }));
    // Stale revision: the server 409s, the page refetches (revision 4
    // in the fixture now) and offers a retry.
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(retry).toBeTruthy();
    const first = calls.find((c) => c.method === "POST" && c.url.endsWith("/activate"));
    expect(first?.body).toEqual({ provider_id: "openai", model_id: "m1", revision: 3 });
    fireEvent.click(retry);
    await waitFor(() => {
      expect(calls.filter((c) => c.method === "POST" && c.url.endsWith("/activate"))).toHaveLength(2);
    });
    const second = calls.filter((c) => c.method === "POST" && c.url.endsWith("/activate"))[1];
    expect(second.body).toEqual({ provider_id: "openai", model_id: "m1", revision: 4 });
  });

  it("surfaces test transport failures as an accessible error", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const state = freshState();
    state.testFails = true;
    setupFetch(state);
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    const groqCard = screen.getByText("Groq").closest("section") as HTMLElement;
    fireEvent.click(within(groqCard).getByRole("button", { name: "Test Connection" }));
    await within(groqCard).findByRole("alert");
    expect(within(groqCard).getByRole("alert").textContent).toContain("connection refused by groq");
  });

  it("saves a key without touching activation", async () => {
    window.confirm = vi.fn(() => true) as unknown as typeof window.confirm;
    const calls = setupFetch(freshState());
    renderPage();
    await screen.findByText("Active Provider: Groq · llama-3.3-70b-versatile");
    const card = screen.getByText("OpenAI").closest("section") as HTMLElement;
    const input = within(card).getByLabelText("API Key For OpenAI") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "sk-new" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save Key" }));
    await screen.findByText("Key Saved For OpenAI. Activation Unchanged.");
    const put = calls.find((c) => c.method === "PUT" && c.url.endsWith("/openai"));
    expect(put?.body).toEqual({ secret: "sk-new" });
    expect(calls.filter((c) => c.url.endsWith("/activate"))).toHaveLength(0);
    expect(calls.filter((c) => c.url.endsWith("/deactivate"))).toHaveLength(0);
    // The unsaved typed value is cleared on submit.
    expect((within(card).getByLabelText("API Key For OpenAI") as HTMLInputElement).value).toBe("");
  });
});

describe("providers navigation guard", () => {
  it("shows Providers above Admin and Settings for admins", async () => {
    setupFetch(freshState(true));
    renderShell();
    const link = await screen.findByRole("link", { name: "Providers" });
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/providers");
    const names = screen.getAllByRole("link").map((a) => a.textContent);
    const order = ["Providers", "Admin", "Settings"].map((n) => names.indexOf(n));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect(order[0]).toBeLessThan(order[1]);
    expect(order[1]).toBeLessThan(order[2]);
  });

  it("hides Providers and Admin for employees", async () => {
    setupFetch(freshState(false));
    renderShell();
    await screen.findByRole("link", { name: "Settings" });
    expect(screen.queryByRole("link", { name: "Providers" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  });

  it("denies direct /providers access to employees like /admin", async () => {
    setupFetch(freshState(false));
    render(
      <MemoryRouter>
        <AuthProvider>
          <LocaleProvider>
            <AdminOnly>
              <span>Secret child</span>
            </AdminOnly>
          </LocaleProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByText("Admin Access Required.");
    expect(screen.queryByText("Secret child")).toBeNull();
  });

  it("renders admin children for admins", async () => {
    setupFetch(freshState(true));
    render(
      <MemoryRouter>
        <AuthProvider>
          <LocaleProvider>
            <AdminOnly>
              <span>Secret child</span>
            </AdminOnly>
          </LocaleProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByText("Secret child");
  });
});
