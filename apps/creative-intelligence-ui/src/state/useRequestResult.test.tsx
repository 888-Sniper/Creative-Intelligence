import { StrictMode, type ReactNode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRequestResult } from "./useRequestResult";

afterEach(cleanup);
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function requestHook(key = "scope-A") {
  return renderHook(({ input }) => useRequestResult<string>(input), { initialProps: { input: key } });
}
type Hook = ReturnType<typeof requestHook>;
function start(hook: Hook, pending: ReturnType<typeof deferred<string>>) {
  let completion!: Promise<void>;
  act(() => { completion = hook.result.current.run(() => pending.promise); });
  return completion;
}

describe("request result ownership", () => {
  it("starts idle and requires an explicit request", () => {
    const { result } = requestHook();
    expect(result.current).toMatchObject({ data: null, loading: false, error: "" });
  });

  it("publishes a current successful result and releases loading", async () => {
    const hook = requestHook(), pending = deferred<string>();
    const completion = start(hook, pending);
    expect(hook.result.current).toMatchObject({ data: null, loading: true, error: "" });
    await act(async () => { pending.resolve("A"); await completion; });
    expect(hook.result.current).toMatchObject({ data: "A", loading: false, error: "" });
  });

  it("hides completed old-scope data on the first render of a new scope", async () => {
    const snapshots: Array<{ key: string; data: string | null }> = [];
    const hook = renderHook(({ input }) => {
      const result = useRequestResult<string>(input);
      snapshots.push({ key: input, data: result.data });
      return result;
    }, { initialProps: { input: "scope-A" } });
    await act(async () => hook.result.current.run(async () => "A"));
    hook.rerender({ input: "scope-B" });
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "" });
    expect(snapshots.filter((item) => item.key === "scope-B").every((item) => item.data === null)).toBe(true);
  });

  it("ignores a delayed old-scope success", async () => {
    const hook = requestHook(), pending = deferred<string>();
    const completion = start(hook, pending);
    hook.rerender({ input: "scope-B" });
    await act(async () => { pending.resolve("old A"); await completion; });
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "" });
  });

  it("ignores an old-scope error while a new request is loading", async () => {
    const hook = requestHook(), a = deferred<string>(), b = deferred<string>();
    const old = start(hook, a);
    hook.rerender({ input: "scope-B" });
    const latest = start(hook, b);
    await act(async () => { a.reject(new Error("old error")); await old; });
    expect(hook.result.current).toMatchObject({ data: null, loading: true, error: "" });
    await act(async () => { b.resolve("B"); await latest; });
    expect(hook.result.current.data).toBe("B");
  });

  it("keeps a newer same-key request in charge when an older one resolves", async () => {
    const hook = requestHook(), a = deferred<string>(), b = deferred<string>();
    const old = start(hook, a), latest = start(hook, b);
    await act(async () => { a.resolve("old"); await old; });
    expect(hook.result.current).toMatchObject({ data: null, loading: true, error: "" });
    await act(async () => { b.resolve("new"); await latest; });
    expect(hook.result.current.data).toBe("new");
  });

  it("keeps the latest error when an older request later succeeds", async () => {
    const hook = requestHook(), a = deferred<string>(), b = deferred<string>();
    const old = start(hook, a), latest = start(hook, b);
    await act(async () => { b.reject(new Error("latest failed")); await latest; });
    await act(async () => { a.resolve("old"); await old; });
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "latest failed" });
  });

  it("clears a failure on retry and shows the retry result", async () => {
    const hook = requestHook();
    await act(async () => hook.result.current.run(async () => { throw new Error("failed"); }));
    const pending = deferred<string>(), completion = start(hook, pending);
    expect(hook.result.current).toMatchObject({ data: null, loading: true, error: "" });
    await act(async () => { pending.resolve("retry"); await completion; });
    expect(hook.result.current.data).toBe("retry");
  });

  it("handles a synchronous request throw and non-Error rejection", async () => {
    const hook = requestHook();
    await act(async () => hook.result.current.run(() => { throw new Error("sync"); }));
    expect(hook.result.current.error).toBe("sync");
    await act(async () => hook.result.current.run(async () => { throw "opaque"; }));
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "Request Failed" });
  });

  it("does not revive old work after a key changes away and back", async () => {
    const hook = requestHook(), pending = deferred<string>();
    const completion = start(hook, pending);
    hook.rerender({ input: "scope-B" });
    hook.rerender({ input: "scope-A" });
    await act(async () => { pending.resolve("first A"); await completion; });
    expect(hook.result.current.data).toBeNull();
    await act(async () => hook.result.current.run(async () => "fresh A"));
    expect(hook.result.current.data).toBe("fresh A");
  });

  it("preserves a completed result across unrelated renders of the same key", async () => {
    const hook = requestHook();
    await act(async () => hook.result.current.run(async () => "A"));
    hook.rerender({ input: "scope-A" });
    expect(hook.result.current.data).toBe("A");
  });

  it("invalidates pending work on local validation failure", async () => {
    const hook = requestHook(), pending = deferred<string>();
    const completion = start(hook, pending);
    act(() => hook.result.current.fail("Fill All Four Period Dates."));
    await act(async () => { pending.resolve("obsolete"); await completion; });
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "Fill All Four Period Dates." });
  });

  it("clears stale validation messages when the input key changes", () => {
    const hook = requestHook();
    act(() => hook.result.current.fail("Fill dates"));
    hook.rerender({ input: "scope-B" });
    expect(hook.result.current.error).toBe("");
  });

  it("ignores callbacks retained from an obsolete key", async () => {
    const hook = requestHook(), old = hook.result.current;
    hook.rerender({ input: "scope-B" });
    const request = vi.fn(async () => "old");
    await act(async () => { await old.run(request); old.fail("old validation"); });
    expect(request).not.toHaveBeenCalled();
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "" });
  });

  it("invalidates work on unmount and does not start work through a detached callback", async () => {
    const hook = requestHook(), pending = deferred<string>();
    const completion = start(hook, pending), detached = hook.result.current;
    hook.unmount();
    pending.resolve("late"); await completion;
    const request = vi.fn(async () => "unmounted");
    await detached.run(request); detached.fail("ignored");
    expect(request).not.toHaveBeenCalled();
  });

  it("survives StrictMode setup and cleanup replay", async () => {
    const hook = renderHook(() => useRequestResult<string>("A"), {
      wrapper: ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>,
    });
    await act(async () => hook.result.current.run(async () => "strict"));
    expect(hook.result.current).toMatchObject({ data: "strict", loading: false, error: "" });
  });

  it.each([0, 1, 2, 3])("invalidates an old result when manual date %i changes", async (index) => {
    const dates = ["2026-01-01", "2026-01-07", "2026-01-08", "2026-01-14"];
    const key = (values: string[]) => JSON.stringify(["campaign=A", ...values]);
    const hook = requestHook(key(dates)), pending = deferred<string>();
    const completion = start(hook, pending);
    const changed = [...dates]; changed[index] = "2026-02-01";
    hook.rerender({ input: key(changed) });
    await act(async () => { pending.resolve("old dates"); await completion; });
    expect(hook.result.current).toMatchObject({ data: null, loading: false, error: "" });
  });
});
