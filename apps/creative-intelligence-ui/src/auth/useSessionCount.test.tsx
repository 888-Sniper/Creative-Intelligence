import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { SESSION_CHECK_TIMEOUT_MS, useSessionCount } from "@/auth/useSessionCount";
import type { MeResponse } from "@/types/auth";

const signedOut: MeResponse = {
  authenticated: false,
  gate: "login",
  employee: null,
  is_admin: false,
  message: "",
  workos_configured: true,
};

let sessionsImpl: () => Promise<unknown> = async () => ({ count: 2 });
let sessionsCalls = 0;

function mockFetch() {
  sessionsCalls = 0;
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url === "/api/auth/sessions") {
      sessionsCalls += 1;
      return Response.json(await sessionsImpl());
    }
    return Response.json(signedOut);
  }) as unknown as typeof fetch;
}

function Probe() {
  const { count, error, loading, reload } = useSessionCount();
  return (
    <div>
      <span data-testid="state">
        {loading ? "loading" : error ? "error" : `count:${count}`}
      </span>
      <button type="button" onClick={() => reload()}>
        reload
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("useSessionCount", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
    sessionsImpl = async () => ({ count: 2 });
  });

  it("reports the server count and exits loading", async () => {
    mockFetch();
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("count:2");
    });
  });

  it("fails concisely with retry, and retry makes a fresh request", async () => {
    sessionsImpl = async () => {
      throw new Error("boom");
    };
    mockFetch();
    const { unmount } = renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("error");
    });
    expect(sessionsCalls).toBe(1);
    // Heal the endpoint: the same control recovers on retry.
    sessionsImpl = async () => ({ count: 1 });
    screen.getByRole("button", { name: "reload" }).click();
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("count:1");
    });
    expect(sessionsCalls).toBe(2);
    unmount();
  });

  it("bounds loading with a timeout instead of hanging", async () => {
    vi.useFakeTimers();
    sessionsImpl = () => new Promise(() => {});
    mockFetch();
    renderProbe();
    expect(screen.getByTestId("state").textContent).toBe("loading");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SESSION_CHECK_TIMEOUT_MS + 1000);
    });
    expect(screen.getByTestId("state").textContent).toBe("error");
  });

  it("shares one in-flight request across repeated reloads", async () => {
    let release!: (v: unknown) => void;
    sessionsImpl = () => new Promise((resolve) => {
      release = resolve;
    });
    mockFetch();
    renderProbe();
    const btn = await screen.findByRole("button", { name: "reload" });
    btn.click();
    btn.click();
    release({ count: 3 });
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("count:3");
    });
    // Mount load + shared reloads collapse into a single request.
    expect(sessionsCalls).toBe(1);
  });
});
