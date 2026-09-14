import { afterEach, describe, expect, it, vi } from "vitest";
import { api, scopedPath } from "@/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
});

function okJson(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

describe("scopedPath", () => {
  it("appends scope to the KPI compare endpoint", () => {
    const scope = new URLSearchParams({
      platform: "tiktok",
      date_from: "2024-01-01",
      date_to: "2024-01-07",
    });
    const url = scopedPath("/api/kpis/compare", scope);
    const params = new URLSearchParams(url.split("?")[1] ?? "");
    expect(params.get("platform")).toBe("tiktok");
    expect(params.get("date_from")).toBe("2024-01-01");
    expect(params.get("date_to")).toBe("2024-01-07");
  });

  it("leaves unscoped paths untouched", () => {
    const scope = new URLSearchParams({ platform: "tiktok" });
    expect(scopedPath("/api/sync/status", scope)).toBe("/api/sync/status");
  });
});

describe("api timeout lifecycle", () => {
  it("completes a normal JSON response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => okJson({ ok: true })));
    await expect(api("GET", "/api/x", undefined, { timeoutMs: 500 })).resolves.toEqual({ ok: true });
  });

  it("times out when the request stalls before headers", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    await expect(api("GET", "/api/stalled", undefined, { timeoutMs: 10 })).rejects.toThrow(
      "Request timed out (/api/stalled)",
    );
  });

  it("times out when headers arrive but the JSON body never finishes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: () => new Promise(() => {}) }) as Response),
    );
    await expect(api("GET", "/api/hung-body", undefined, { timeoutMs: 10 })).rejects.toThrow(
      "Request timed out (/api/hung-body)",
    );
  });

  it("rejects immediately on an already-aborted caller signal without fetching", async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    const spy = vi.fn(async () => okJson({}));
    vi.stubGlobal("fetch", spy);
    const err = await api("GET", "/api/y", undefined, { signal: ctrl.signal }).catch((e) => e);
    expect(err).toBeInstanceOf(DOMException);
    expect((err as DOMException).name).toBe("AbortError");
    expect(spy).not.toHaveBeenCalled();
  });
});
