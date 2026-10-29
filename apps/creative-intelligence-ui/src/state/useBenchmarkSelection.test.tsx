import { useMemo } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useBenchmarkSelection } from "./useBenchmarkSelection";
import { useScopedLoad } from "./useScopedLoad";

afterEach(cleanup);
type Rows = Array<{ key: string }> | null;
const groups = (...names: string[]) => names.map((key) => ({ key }));
function selectionHook(axis = "platform", rows: Rows = null) {
  return renderHook(({ axis, rows }: { axis: string; rows: Rows }) => useBenchmarkSelection(axis, rows), {
    initialProps: { axis, rows },
  });
}

describe("current benchmark selection", () => {
  it("waits for a settled response before selecting groups", () => {
    const hook = selectionHook();
    expect([...hook.result.current.selected]).toEqual([]);
    hook.rerender({ axis: "platform", rows: groups("Meta", "TikTok", "YouTube") });
    expect([...hook.result.current.selected]).toEqual(["Meta", "TikTok"]);
  });

  it("waits for two distinct groups and uses response order", () => {
    const hook = selectionHook("hook_type", groups("question", "question"));
    expect(hook.result.current.selected.size).toBe(0);
    hook.rerender({ axis: "hook_type", rows: groups("testimonial", "question", "demo") });
    expect([...hook.result.current.selected]).toEqual(["testimonial", "question"]);
  });

  it("preserves an intentional one-group choice when more rows arrive", () => {
    const hook = selectionHook("platform", groups("Meta"));
    act(() => hook.result.current.setSelected(new Set(["Meta"])));
    hook.rerender({ axis: "platform", rows: groups("TikTok", "YouTube", "Meta") });
    expect([...hook.result.current.selected]).toEqual(["Meta"]);
  });

  it("keeps an explicit clear across refreshed or reordered rows", () => {
    const hook = selectionHook("platform", groups("Meta", "TikTok"));
    act(() => hook.result.current.setSelected(new Set()));
    hook.rerender({ axis: "platform", rows: null });
    hook.rerender({ axis: "platform", rows: groups("TikTok", "Meta", "YouTube") });
    expect(hook.result.current.selected.size).toBe(0);
  });

  it("allows functional toggles without mutating the previous selected set", () => {
    const hook = selectionHook("platform", groups("Meta", "TikTok", "YouTube"));
    const old = hook.result.current.selected;
    act(() => hook.result.current.setSelected((keys) => {
      keys.delete("TikTok"); keys.add("YouTube"); return keys;
    }));
    expect([...old]).toEqual(["Meta", "TikTok"]);
    expect([...hook.result.current.selected]).toEqual(["Meta", "YouTube"]);
  });

  it("limits new selections to three current groups and discards invisible keys", () => {
    const hook = selectionHook("hook_type", groups("a", "b", "c", "d"));
    act(() => hook.result.current.setSelected(new Set(["old platform", "d", "c", "b", "a"])));
    expect([...hook.result.current.selected]).toEqual(["d", "c", "b"]);
  });

  it("prunes removed groups on the first current-response render", () => {
    const snapshots: string[][] = [];
    const hook = renderHook(({ rows }: { rows: NonNullable<Rows> }) => {
      const state = useBenchmarkSelection("platform", rows);
      if (rows[0]?.key === "TikTok") snapshots.push([...state.selected]);
      return state;
    }, { initialProps: { rows: groups("Meta", "TikTok", "YouTube") } });
    hook.rerender({ rows: groups("TikTok", "YouTube") });
    expect(snapshots.length).toBeGreaterThan(0);
    expect(snapshots.every((keys) => keys.length === 1 && keys[0] === "TikTok")).toBe(true);
    act(() => hook.result.current.setSelected((keys) => new Set([...keys, "YouTube"])));
    expect([...hook.result.current.selected]).toEqual(["TikTok", "YouTube"]);
  });

  it("does not silently replace deliberate choices when all chosen groups disappear", () => {
    const hook = selectionHook("platform", groups("Meta", "TikTok"));
    hook.rerender({ axis: "platform", rows: groups("YouTube", "Other") });
    expect(hook.result.current.selected.size).toBe(0);
    act(() => hook.result.current.setSelected(new Set(["YouTube", "Other"])));
    expect([...hook.result.current.selected]).toEqual(["YouTube", "Other"]);
  });

  it("hides pending selection but preserves still-valid choices after refresh", () => {
    const hook = selectionHook("platform", groups("Meta", "TikTok", "YouTube"));
    act(() => hook.result.current.setSelected(new Set(["Meta", "YouTube"])));
    hook.rerender({ axis: "platform", rows: null });
    expect(hook.result.current.selected.size).toBe(0);
    act(() => hook.result.current.setSelected(new Set(["outdated"])));
    hook.rerender({ axis: "platform", rows: groups("YouTube", "Meta", "TikTok") });
    expect([...hook.result.current.selected]).toEqual(["Meta", "YouTube"]);
  });

  it("resets old-axis selection and waits for the new-axis response", () => {
    const hook = selectionHook("platform", groups("Meta", "TikTok"));
    hook.rerender({ axis: "hook_type", rows: null });
    expect(hook.result.current.selected.size).toBe(0);
    hook.rerender({ axis: "hook_type", rows: groups("question", "testimonial") });
    expect([...hook.result.current.selected]).toEqual(["question", "testimonial"]);
  });

  it("resets even when two different axes happen to share a group name", () => {
    const hook = selectionHook("format", groups("video", "other"));
    act(() => hook.result.current.setSelected(new Set(["other"])));
    hook.rerender({ axis: "hook_type", rows: groups("other", "question", "testimonial") });
    expect([...hook.result.current.selected]).toEqual(["other", "question"]);
  });

  it("an empty initial response can initialize when groups later become available", () => {
    const hook = selectionHook("platform", []);
    hook.rerender({ axis: "platform", rows: groups("Meta", "TikTok") });
    expect([...hook.result.current.selected]).toEqual(["Meta", "TikTok"]);
  });

  it("discards removed keys permanently after a settled empty response", () => {
    const hook = selectionHook("platform", groups("Meta", "TikTok"));
    hook.rerender({ axis: "platform", rows: [] });
    hook.rerender({ axis: "platform", rows: groups("Meta", "TikTok") });
    expect(hook.result.current.selected.size).toBe(0);
  });

  it("keeps explicit choices through root StrictMode effect replay", () => {
    const rows = groups("Meta", "TikTok", "YouTube");
    const hook = renderHook(() => useBenchmarkSelection("platform", rows), { reactStrictMode: true });
    expect([...hook.result.current.selected]).toEqual(["Meta", "TikTok"]);
    act(() => hook.result.current.setSelected(new Set(["YouTube"])));
    expect([...hook.result.current.selected]).toEqual(["YouTube"]);
  });
});

type Response = Record<string, { spend: number }>;
function deferred() {
  let resolve!: (value: Response) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<Response>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const response = (...keys: string[]): Response => Object.fromEntries(keys.map((key, i) => [key, { spend: 100 - i }]));
function requestAndSelection(axis: string, load: () => Promise<Response>) {
  return renderHook(({ axis, load }) => {
    const request = useScopedLoad(load);
    const rows = useMemo(() => request.data === null ? null : Object.keys(request.data).map((key) => ({ key })), [request.data]);
    const selection = useBenchmarkSelection(axis, rows);
    return { ...request, ...selection };
  }, { initialProps: { axis, load } });
}
async function settle(pending: ReturnType<typeof deferred>, ...keys: string[]) {
  await act(async () => { pending.resolve(response(...keys)); await pending.promise; });
}

describe("selection with current-request loading", () => {
  it("uses current groups after a grouping input changes axis", async () => {
    const a = deferred(), b = deferred();
    const hook = requestAndSelection("platform", () => a.promise);
    await settle(a, "Meta", "TikTok");
    hook.rerender({ axis: "hook_type", load: () => b.promise });
    expect(hook.result.current.loading).toBe(true);
    expect(hook.result.current.selected.size).toBe(0);
    await settle(b, "question", "testimonial");
    expect([...hook.result.current.selected]).toEqual(["question", "testimonial"]);
  });

  it("prunes a removed selection when filters change without changing the axis", async () => {
    const a = deferred(), b = deferred();
    const hook = requestAndSelection("platform", () => a.promise);
    await settle(a, "Meta", "TikTok");
    hook.rerender({ axis: "platform", load: () => b.promise });
    expect(hook.result.current.selected.size).toBe(0);
    await settle(b, "TikTok", "YouTube");
    expect([...hook.result.current.selected]).toEqual(["TikTok"]);
  });

  it("ignores late old grouping responses", async () => {
    const a = deferred(), b = deferred();
    const hook = requestAndSelection("platform", () => a.promise);
    hook.rerender({ axis: "hook_type", load: () => b.promise });
    await settle(a, "Meta", "TikTok");
    expect(hook.result.current.selected.size).toBe(0);
    await settle(b, "question", "testimonial");
    expect([...hook.result.current.selected]).toEqual(["question", "testimonial"]);
  });

  it("leaves comparison empty on a failed new grouping and initializes after retry", async () => {
    const a = deferred(), b = deferred(), retry = deferred();
    const hook = requestAndSelection("platform", () => a.promise);
    await settle(a, "Meta", "TikTok");
    hook.rerender({ axis: "hook_type", load: () => b.promise });
    await act(async () => { b.reject(new Error("unavailable")); await b.promise.catch(() => {}); });
    expect(hook.result.current.error).toBe("unavailable");
    expect(hook.result.current.selected.size).toBe(0);
    hook.rerender({ axis: "hook_type", load: () => retry.promise });
    await settle(retry, "question", "testimonial");
    expect([...hook.result.current.selected]).toEqual(["question", "testimonial"]);
  });
});
