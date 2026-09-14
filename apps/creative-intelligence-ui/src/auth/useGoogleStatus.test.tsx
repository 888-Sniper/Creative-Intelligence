import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthProvider";
import { GOOGLE_STATUS_TIMEOUT_MS, useGoogleStatus } from "@/auth/useGoogleStatus";
import type { MeResponse } from "@/types/auth";

const signedOut: MeResponse = {
  authenticated: false,
  gate: "login",
  employee: null,
  is_admin: false,
  message: "",
  workos_configured: true,
};

let statusImpl: () => Promise<unknown> = async () => ({ connected: false });
let statusCalls = 0;

function mockFetch() {
  statusCalls = 0;
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url === "/api/auth/google/status") {
      statusCalls += 1;
      return Response.json(await statusImpl());
    }
    return Response.json(signedOut);
  }) as unknown as typeof fetch;
}

function Probe() {
  const { connected, error, loading, reload } = useGoogleStatus();
  return (
    <div>
      <span data-testid="state">
        {loading ? "loading" : error ? "error" : `connected:${connected}`}
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

describe("useGoogleStatus", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
    statusImpl = async () => ({ connected: false });
  });

  it("reports the server state and exits loading", async () => {
    statusImpl = async () => ({ connected: true });
    mockFetch();
    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("connected:true");
    });
  });

  it("fails concisely with retry, and retry makes a fresh request", async () => {
    statusImpl = async () => {
      throw new Error("boom");
    };
    mockFetch();
    const { unmount } = renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("error");
    });
    expect(statusCalls).toBe(1);
    statusImpl = async () => ({ connected: false });
    screen.getByRole("button", { name: "reload" }).click();
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("connected:false");
    });
    expect(statusCalls).toBe(2);
    unmount();
  });

  it("bounds loading with a timeout instead of sticking on Checking…", async () => {
    vi.useFakeTimers();
    statusImpl = () => new Promise(() => {});
    mockFetch();
    renderProbe();
    expect(screen.getByTestId("state").textContent).toBe("loading");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(GOOGLE_STATUS_TIMEOUT_MS + 1000);
    });
    expect(screen.getByTestId("state").textContent).toBe("error");
  });

  it("shares one in-flight request across repeated reloads", async () => {
    let release!: (v: unknown) => void;
    statusImpl = () => new Promise((resolve) => {
      release = resolve;
    });
    mockFetch();
    renderProbe();
    const btn = await screen.findByRole("button", { name: "reload" });
    btn.click();
    btn.click();
    release({ connected: true });
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("connected:true");
    });
    expect(statusCalls).toBe(1);
  });
});
