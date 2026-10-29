import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScopedLoad } from "./useScopedLoad";

afterEach(cleanup);
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
type Loader = () => Promise<string>;
function loadHook(load: Loader, refreshKey = 0) {
  return renderHook(({ loader, refresh }) => useScopedLoad(loader, refresh), {
    initialProps: { loader: load, refresh: refreshKey },
  });
}
async function settle(pending: ReturnType<typeof deferred<string>>, value: string) {
  await act(async () => { pending.resolve(value); await pending.promise; });
}
async function fail(pending: ReturnType<typeof deferred<string>>, error: unknown) {
  await act(async () => { pending.reject(error); await pending.promise.catch(() => {}); });
}

describe("scoped automatic loading", () => {
  it("loads once on mount and exposes the completed result", async () => {
    const pending = deferred<string>(), load = vi.fn(() => pending.promise);
    const hook = loadHook(load);
    expect(load).toHaveBeenCalledTimes(1);
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
    await settle(pending, "A");
    expect(hook.result.current).toEqual({ data: "A", loading: false, error: "" });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("hides the previous scope on every render of the next scope, even before effects", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const loadA = () => a.promise, loadB = () => b.promise;
    const snapshots: Array<{ load: Loader; data: string | null; loading: boolean }> = [];
    const hook = renderHook(({ load }) => {
      const state = useScopedLoad(load);
      snapshots.push({ load, data: state.data, loading: state.loading });
      return state;
    }, { initialProps: { load: loadA } });
    await settle(a, "A");
    hook.rerender({ load: loadB });
    const pendingB = snapshots.filter((snapshot) => snapshot.load === loadB);
    expect(pendingB.length).toBeGreaterThan(0);
    expect(pendingB.every((snapshot) => snapshot.data === null && snapshot.loading)).toBe(true);
    await settle(b, "B");
    expect(hook.result.current).toEqual({ data: "B", loading: false, error: "" });
  });

  it("does not keep a successful old-scope result when the next scope fails", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const hook = loadHook(() => a.promise);
    await settle(a, "A");
    hook.rerender({ loader: () => b.promise, refresh: 0 });
    await fail(b, new Error("B unavailable"));
    expect(hook.result.current).toEqual({ data: null, loading: false, error: "B unavailable" });
  });

  it("clears completed data on the first render of an explicit refresh", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const load = vi.fn().mockImplementationOnce(() => a.promise).mockImplementationOnce(() => b.promise);
    const seen: Array<{ refresh: number; data: string | null }> = [];
    const hook = renderHook(({ refresh }) => {
      const state = useScopedLoad<string>(load, refresh);
      seen.push({ refresh, data: state.data });
      return state;
    }, { initialProps: { refresh: 0 } });
    await settle(a, "before refresh");
    hook.rerender({ refresh: 1 });
    expect(seen.filter((item) => item.refresh === 1).every((item) => item.data === null)).toBe(true);
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
    await settle(b, "fresh");
    expect(hook.result.current.data).toBe("fresh");
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("clears failure on refresh and can recover on the same scope", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const load = vi.fn().mockImplementationOnce(() => a.promise).mockImplementationOnce(() => b.promise);
    const hook = loadHook(load);
    await fail(a, new Error("temporary"));
    hook.rerender({ loader: load, refresh: 1 });
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
    await settle(b, "recovered");
    expect(hook.result.current).toEqual({ data: "recovered", loading: false, error: "" });
  });

  it("clears old errors immediately when the loader scope changes", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const hook = loadHook(() => a.promise);
    await fail(a, new Error("old scope"));
    hook.rerender({ loader: () => b.promise, refresh: 0 });
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
  });

  it("ignores old-scope success while the new scope is still pending", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const hook = loadHook(() => a.promise);
    hook.rerender({ loader: () => b.promise, refresh: 0 });
    await settle(a, "old A");
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
    await settle(b, "B");
    expect(hook.result.current.data).toBe("B");
  });

  it("ignores old-scope failures after the latest scope succeeds", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const hook = loadHook(() => a.promise);
    hook.rerender({ loader: () => b.promise, refresh: 0 });
    await settle(b, "B");
    await fail(a, new Error("late A failure"));
    expect(hook.result.current).toEqual({ data: "B", loading: false, error: "" });
  });

  it("does not let old success hide the current failure", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const hook = loadHook(() => a.promise);
    hook.rerender({ loader: () => b.promise, refresh: 0 });
    await fail(b, new Error("B failed"));
    await settle(a, "late A");
    expect(hook.result.current).toEqual({ data: null, loading: false, error: "B failed" });
  });

  it("discards obsolete responses across explicit refreshes of the same loader", async () => {
    const a = deferred<string>(), b = deferred<string>();
    const load = vi.fn().mockImplementationOnce(() => a.promise).mockImplementationOnce(() => b.promise);
    const hook = loadHook(load);
    hook.rerender({ loader: load, refresh: 1 });
    await settle(b, "new");
    await settle(a, "old");
    expect(hook.result.current.data).toBe("new");
  });

  it("does not revive the first request when scope changes away and back", async () => {
    const firstA = deferred<string>(), b = deferred<string>(), nextA = deferred<string>();
    const loadA = vi.fn().mockImplementationOnce(() => firstA.promise).mockImplementationOnce(() => nextA.promise);
    const hook = loadHook(loadA);
    hook.rerender({ loader: () => b.promise, refresh: 0 });
    hook.rerender({ loader: loadA, refresh: 0 });
    await settle(firstA, "obsolete A");
    await settle(b, "obsolete B");
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
    await settle(nextA, "current A");
    expect(hook.result.current.data).toBe("current A");
  });

  it("preserves results and does not reload on unrelated renders", async () => {
    const pending = deferred<string>(), load = vi.fn(() => pending.promise);
    const hook = loadHook(load);
    await settle(pending, "A");
    hook.rerender({ loader: load, refresh: 0 });
    expect(load).toHaveBeenCalledTimes(1);
    expect(hook.result.current.data).toBe("A");
  });

  it("keeps a stable NaN refresh key consistent with React dependency equality", async () => {
    const load = vi.fn(async () => "A"), hook = loadHook(load, NaN);
    await act(async () => {});
    hook.rerender({ loader: load, refresh: NaN });
    expect(hook.result.current).toEqual({ data: "A", loading: false, error: "" });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("catches a synchronous loader throw and releases loading", () => {
    const hook = loadHook(() => { throw new Error("synchronous failure"); });
    expect(hook.result.current).toEqual({ data: null, loading: false, error: "synchronous failure" });
  });

  it.each([
    { reason: "plain rejection", expected: "plain rejection" },
    { reason: new Error(""), expected: "Request Failed" },
    { reason: "", expected: "Request Failed" },
  ])("uses a visible message for $expected", async ({ reason, expected }) => {
    const pending = deferred<string>(), hook = loadHook(() => pending.promise);
    await fail(pending, reason);
    expect(hook.result.current).toEqual({ data: null, loading: false, error: expected });
  });

  it("does not publish a response after unmount", async () => {
    const pending = deferred<string>(), hook = loadHook(() => pending.promise);
    const before = hook.result.current;
    hook.unmount();
    await settle(pending, "late response");
    expect(hook.result.current).toBe(before);
  });

  it("handles StrictMode effect replay without accepting the first response", async () => {
    const first = deferred<string>(), current = deferred<string>();
    const load = vi.fn().mockImplementationOnce(() => first.promise).mockImplementationOnce(() => current.promise);
    const hook = renderHook(() => useScopedLoad<string>(load), {
      reactStrictMode: true,
    });
    expect(load).toHaveBeenCalledTimes(2);
    await settle(first, "discarded replay");
    expect(hook.result.current).toEqual({ data: null, loading: true, error: "" });
    await settle(current, "current");
    expect(hook.result.current.data).toBe("current");
  });
});
