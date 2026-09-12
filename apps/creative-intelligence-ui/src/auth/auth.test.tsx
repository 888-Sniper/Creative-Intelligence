import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      expect(screen.getByText("Welcome Back")).toBeDefined();
    });
  });

  it("renders the employee login with exact approved copy", async () => {
    mockMe(base);
    renderGate();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Welcome Back" })).toBeDefined();
    });
    expect(screen.getByText("Sign In To Your Employee Workspace.")).toBeDefined();
    expect(screen.queryByText("Welcome To Creative Intelligence")).toBeNull();
    // No Creative Intelligence product branding on the login screen.
    expect(screen.queryByText("Creative Intelligence")).toBeNull();
    // Foap logo above the card, no text logo recreation.
    const logo = screen.getByAltText("Foap");
    expect(logo.tagName).toBe("IMG");
    expect(logo.getAttribute("src")).toContain("foap-logo");
  });

  it("renders the password-mode form with remember, reset and Sign In", async () => {
    mockMe(base);
    renderGate();
    await waitFor(() => {
      expect(screen.getByLabelText("Work Email")).toBeDefined();
    });
    const email = screen.getByLabelText("Work Email") as HTMLInputElement;
    expect(email.getAttribute("placeholder")).toBe("name@company.com");
    const password = screen.getByLabelText("Password") as HTMLInputElement;
    expect(password.getAttribute("placeholder")).toBe("Enter your password");
    expect(password.getAttribute("type")).toBe("password");
    expect(screen.getByRole("checkbox", { name: "Remember Me" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Forgot Password?" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeDefined();
    // Password visibility toggle keeps secure behaviour by default.
    const toggle = screen.getByRole("button", { name: "Show Password" });
    fireEvent.click(toggle);
    expect(password.getAttribute("type")).toBe("text");
    expect(screen.getByRole("button", { name: "Hide Password" })).toBeDefined();
  });

  it("shows only Google and Microsoft on the employee login", async () => {
    mockMe(base);
    renderGate();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Continue With Google" })).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Continue With Microsoft" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Continue With Apple" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Continue With GitHub" })).toBeNull();
  });

  it("renders the employee-only footer and no signup controls", async () => {
    mockMe(base);
    renderGate();
    await waitFor(() => {
      expect(screen.getByText("For Foap employees only.", { exact: false })).toBeDefined();
    });
    expect(screen.queryByText(/create account/i)).toBeNull();
    expect(screen.queryByText(/sign up/i)).toBeNull();
    expect(screen.queryByText(/new to foap/i)).toBeNull();
  });

  it("keeps the sign-in-code flow behind a secondary control", async () => {
    mockMe(base);
    renderGate();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Use A Sign-In Code Instead" })).toBeDefined();
    });
    // Hidden initially: no code field, no Verify button.
    expect(screen.queryByLabelText("Verification Code")).toBeNull();
    expect(screen.queryByRole("button", { name: /Verify/ })).toBeNull();
    // Opens through the secondary control; password mode hides.
    fireEvent.click(screen.getByRole("button", { name: "Use A Sign-In Code Instead" }));
    expect(screen.getByLabelText("Work Email")).toBeDefined();
    expect(screen.getByRole("button", { name: "Send Sign-In Code" })).toBeDefined();
    expect(screen.queryByLabelText("Password")).toBeNull();
    // Back to password mode.
    fireEvent.click(screen.getByRole("button", { name: "Back To Password Sign In" }));
    expect(screen.getByLabelText("Password")).toBeDefined();
    expect(screen.queryByLabelText("Verification Code")).toBeNull();
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

  it("shows a clean inline error on failed password sign-in", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/email/signin") {
        return new Response(JSON.stringify({ detail: { error: "Incorrect email or password." } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        });
      }
      return Response.json(base);
    }) as unknown as typeof fetch;
    renderGate();
    await waitFor(() => {
      expect(screen.getByLabelText("Work Email")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));
    await waitFor(() => {
      expect(screen.getByText("Incorrect email or password.")).toBeDefined();
    });
    // Still on the login card, still branded.
    expect(screen.getByText("Welcome Back")).toBeDefined();
  });

  it("transitions to the pending gate after sign-in without access", async () => {
    // Boot sees a signed-out session; only the sign-in (and the
    // refresh it triggers) reports the pending gate.
    let meCalls = 0;
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/auth/email/signin") {
        return Response.json({ ...base, authenticated: true, gate: "pending" });
      }
      if (url === "/api/auth/me") {
        meCalls += 1;
        if (meCalls > 1) return Response.json({ ...base, authenticated: true, gate: "pending" });
      }
      return Response.json(base);
    }) as unknown as typeof fetch;
    renderGate();
    await waitFor(() => {
      expect(screen.getByLabelText("Work Email")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));
    await waitFor(() => {
      expect(screen.getByText("Access Pending")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Refresh Access" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Log Out" })).toBeDefined();
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
});

describe("login loading states", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  function deferredFetch(routes: Record<string, () => Promise<Response>>) {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      const handler = routes[url];
      if (handler) return handler();
      return Response.json(base);
    }) as unknown as typeof fetch;
  }

  function defer(): { gate: Promise<Response>; release: (res: Response) => void; reject: (err: unknown) => void } {
    let release!: (res: Response) => void;
    let reject!: (err: unknown) => void;
    const gate = new Promise<Response>((res, rej) => { release = res; reject = rej; });
    return { gate, release, reject };
  }

  async function openCodeMode() {
    renderGate();
    await waitFor(() => {
      expect(screen.getByLabelText("Work Email")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Use A Sign-In Code Instead" }));
  }

  it("shows Sending Code… only on the send button", async () => {
    const d = defer();
    deferredFetch({ "/api/auth/email/code": () => d.gate });
    await openCodeMode();
    fireEvent.click(screen.getByRole("button", { name: "Send Sign-In Code" }));
    await waitFor(() => {
      expect(screen.getByText("Sending Code…")).toBeDefined();
    });
    // Siblings disable but keep idle labels: no spinner leak.
    expect(screen.getByRole("button", { name: "Continue With Google" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Continue With Microsoft" })).toBeDefined();
    d.release(Response.json({}));
    await waitFor(() => {
      expect(screen.getByLabelText("Verification Code")).toBeDefined();
    });
  });

  it("shows Verifying… only on the verify button", async () => {
    const d = defer();
    deferredFetch({
      "/api/auth/email/code": async () => Response.json({}),
      "/api/auth/email/code/signin": () => d.gate,
    });
    await openCodeMode();
    fireEvent.click(screen.getByRole("button", { name: "Send Sign-In Code" }));
    await waitFor(() => {
      expect(screen.getByLabelText("Verification Code")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Verification Code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify & Sign In" }));
    await waitFor(() => {
      expect(screen.getByText("Verifying…")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Continue With Microsoft" })).toBeDefined();
    d.reject(new Error("network down"));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Verify & Sign In" })).toBeDefined();
    });
  });

  it("shows Sending… only on the forgot-password button", async () => {
    const d = defer();
    deferredFetch({ "/api/auth/email/reset": () => d.gate });
    renderGate();
    await waitFor(() => {
      expect(screen.getByLabelText("Work Email")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Forgot Password?" }));
    await waitFor(() => {
      expect(screen.getByText("Sending…")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Sign In" })).toBeDefined();
    d.release(Response.json({}));
    await waitFor(() => {
      expect(screen.getByText("If That Email Exists, A Reset Is On Its Way.")).toBeDefined();
    });
  });

  it("shows Signing In… only on the Sign In button", async () => {
    const d = defer();
    deferredFetch({ "/api/auth/email/signin": () => d.gate });
    renderGate();
    await waitFor(() => {
      expect(screen.getByLabelText("Work Email")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));
    await waitFor(() => {
      expect(screen.getByText("Signing In…")).toBeDefined();
    });
    // OAuth siblings keep idle labels while email auth is in flight.
    expect(screen.getByRole("button", { name: "Continue With Google" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Continue With Microsoft" })).toBeDefined();
    d.release(new Response(JSON.stringify({ detail: { error: "Incorrect email or password." } }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    }));
    await waitFor(() => {
      expect(screen.getByText("Incorrect email or password.")).toBeDefined();
    });
  });

  it("shows Connecting To Google… only on the pressed provider", async () => {
    const d = defer();
    deferredFetch({ "/api/auth/oauth/start": () => d.gate });
    renderGate();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Continue With Google" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue With Google" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Connecting To Google…" })).toBeDefined();
    });
    // Microsoft disables but never shows the spinner/label.
    expect(screen.getByRole("button", { name: "Continue With Microsoft" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Connecting To Microsoft…" })).toBeNull();
    d.release(Response.json({ url: "https://workos.test/authorize" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Connecting To Google…" })).toBeNull();
    });
  });
});

describe("AuthGate screens (account admin)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
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
