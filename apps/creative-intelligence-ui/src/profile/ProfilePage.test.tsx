import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProfilePage } from "@/profile/ProfilePage";
import type { MeResponse } from "@/types/auth";

const employee = {
  id: "e1",
  email: "ada@foap.test",
  first_name: "Ada",
  last_name: "Lovelace",
  avatar_url: "",
  role: "employee",
  status: "active",
  created_at: "",
  approved_at: "",
  approved_by: "",
  last_login_at: "",
  updated_at: "",
};

const me: MeResponse = {
  authenticated: true,
  gate: "app",
  employee,
  is_admin: false,
  message: "",
  workos_configured: true,
};

function mockMeFetch() {
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    if (String(input) === "/api/auth/me") return Response.json(me);
    return Response.json({});
  }) as unknown as typeof fetch;
}

describe("ProfilePage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders with mocked data", async () => {
    mockMeFetch();
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("Ada Lovelace")).toBeDefined();
    });
    expect(screen.getByText("ada@foap.test")).toBeDefined();
    expect(screen.getByText("employee · active")).toBeDefined();
    expect((screen.getByLabelText("First name") as HTMLInputElement).value).toBe("Ada");
    expect((screen.getByLabelText("Last name") as HTMLInputElement).value).toBe("Lovelace");
    expect(
      (screen.getByLabelText("Avatar URL (optional)") as HTMLInputElement).value,
    ).toBe("");
    expect(screen.getByRole("button", { name: "Save profile" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Remove avatar" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Log out everywhere" })).toBeDefined();
    // No avatar URL set: initials fallback.
    expect(screen.getByText("AL")).toBeDefined();
  });

  it("shows the provider avatar image when set", async () => {
    window.fetch = vi.fn(async () =>
      Response.json({
        ...me,
        employee: { ...employee, avatar_url: "https://cdn.test/a.png" },
      }),
    ) as unknown as typeof fetch;
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("Ada Lovelace")).toBeDefined();
    });
    const img = document.querySelector("img.avatar") as HTMLImageElement | null;
    expect(img?.src).toBe("https://cdn.test/a.png");
    expect(
      (screen.getByLabelText("Avatar URL (optional)") as HTMLInputElement).value,
    ).toBe("https://cdn.test/a.png");
  });

  it("shows a loading state before data arrives", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    render(<ProfilePage />);
    expect(screen.getByText("Loading profile…")).toBeDefined();
  });

  it("renders load errors", async () => {
    window.fetch = vi.fn(async () =>
      Response.json({ error: "db is locked" }, { status: 409 }),
    ) as unknown as typeof fetch;
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("db is locked")).toBeDefined();
    });
  });

  it("saves first/last name with the legacy payload shape", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/auth/me" && method === "GET") return Response.json(me);
      if (url === "/api/auth/me" && method === "PATCH") {
        const body = JSON.parse(String(init?.body)) as Record<string, string>;
        return Response.json({ ok: true, employee: { ...employee, ...body } });
      }
      return Response.json({});
    }) as unknown as typeof fetch;
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("Ada Lovelace")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("First name"), { target: { value: "Grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => {
      expect(screen.getByText("Saved.")).toBeDefined();
    });
    const calls = (window.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls as Array<
      [unknown, RequestInit | undefined]
    >;
    const patch = calls.find(([u, i]) => String(u) === "/api/auth/me" && i?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      first_name: "Grace",
      last_name: "Lovelace",
      avatar_url: "",
    });
    expect(screen.getByText("Grace Lovelace")).toBeDefined();
  });

  it("uploads a manual avatar as multipart FormData, not JSON", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/auth/me" && method === "GET") return Response.json(me);
      if (url === "/api/auth/me/avatar" && method === "POST") {
        return Response.json({
          ok: true,
          employee: { ...employee, avatar_url: "/api/auth/avatar/e1" },
        });
      }
      if (url === "/api/auth/me" && method === "PATCH") {
        return Response.json({
          ok: true,
          employee: { ...employee, avatar_url: "/api/auth/avatar/e1" },
        });
      }
      return Response.json({});
    }) as unknown as typeof fetch;
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("Ada Lovelace")).toBeDefined();
    });
    const fileInput = screen.getByLabelText("Avatar image file") as HTMLInputElement;
    Object.defineProperty(fileInput, "files", {
      value: [new File(["png-bytes"], "me.png", { type: "image/png" })],
      configurable: true,
    });
    fireEvent.change(fileInput);
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => {
      expect(screen.getByText("Saved.")).toBeDefined();
    });
    const calls = (window.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls as Array<
      [unknown, RequestInit | undefined]
    >;
    const upload = calls.find(([u]) => String(u) === "/api/auth/me/avatar");
    expect(upload?.[1]?.method).toBe("POST");
    const body = upload?.[1]?.body as unknown as FormData;
    expect(typeof body.get).toBe("function");
    expect((body.get("avatar") as File).name).toBe("me.png");
    // Uploaded avatars blank the URL field (legacy load_profile parity).
    expect((screen.getByLabelText("Avatar URL (optional)") as HTMLInputElement).value).toBe(
      "",
    );
  });

  it("removes the avatar via PATCH {avatar_url: ''}", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/auth/me" && method === "GET") {
        return Response.json({ ...me, employee: { ...employee, avatar_url: "https://x/y.png" } });
      }
      if (url === "/api/auth/me" && method === "PATCH") {
        const body = JSON.parse(String(init?.body)) as Record<string, string>;
        expect(body).toEqual({ avatar_url: "" });
        return Response.json({ ok: true, employee: { ...employee, avatar_url: "" } });
      }
      return Response.json({});
    }) as unknown as typeof fetch;
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Remove avatar" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove avatar" }));
    await waitFor(() => {
      expect(screen.getByText("Avatar removed.")).toBeDefined();
    });
  });

  it("logs out everywhere via POST /api/auth/sessions/revoke-all", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/auth/me" && method === "GET") return Response.json(me);
      if (url === "/api/auth/sessions/revoke-all" && method === "POST") {
        return Response.json({ ok: true, revoked: 2 });
      }
      return Response.json({});
    }) as unknown as typeof fetch;
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Log out everywhere" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Log out everywhere" }));
    await waitFor(() => {
      expect(screen.getByText("Signed out of 2 session(s).")).toBeDefined();
    });
  });
});
