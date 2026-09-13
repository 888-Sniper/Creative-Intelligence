import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

afterEach(cleanup);
import { FilterProvider, useFilters } from "@/state/FilterContext";
import { SAMPLE_SCOPE_KEY, SampleScopeBanner } from "@/components/SampleScopeBanner";

const SCOPE = { from: "2026-01-01", to: "2026-03-31", batch: "batch-1" };

function Probe() {
  const { filters, setFilter } = useFilters();
  return (
    <div>
      <span data-testid="from">{filters.date_from}</span>
      <span data-testid="to">{filters.date_to}</span>
      <span data-testid="campaign">{filters.campaign}</span>
      <button type="button" onClick={() => setFilter("campaign", "my-real-campaign")}>
        narrow
      </button>
    </div>
  );
}

function Shell({ showBanner }: { showBanner: boolean }) {
  return (
    <FilterProvider>
      {showBanner ? <SampleScopeBanner /> : null}
      <Probe />
    </FilterProvider>
  );
}

function renderShell(showBanner = true) {
  return render(<Shell showBanner={showBanner} />);
}

// jsdom here runs without an origin, so the real localStorage is
// unavailable: stub an in-memory store for the scope key.
const memStore = new Map<string, string>();
beforeEach(() => {
  memStore.clear();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (memStore.has(k) ? memStore.get(k)! : null),
    setItem: (k: string, v: string) => { memStore.set(k, String(v)); },
    removeItem: (k: string) => { memStore.delete(k); },
    clear: () => { memStore.clear(); },
  });
});

describe("SampleScopeBanner", () => {
  it("renders nothing without a stored scope", () => {
    renderShell();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("applies a clean scope once and keeps the panel-saved return path", () => {
    localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({
      ...SCOPE, prev: { campaign: "my-real-campaign" },
    }));
    renderShell(true);
    expect(screen.getByTestId("from").textContent).toBe(SCOPE.from);
    expect(screen.getByTestId("to").textContent).toBe(SCOPE.to);
    expect(screen.getByTestId("campaign").textContent).toBe("");
    const stored = JSON.parse(localStorage.getItem(SAMPLE_SCOPE_KEY) ?? "null");
    expect(stored.applied).toBe(true);
    expect(stored.prev).toEqual({ campaign: "my-real-campaign" });
  });

  it("falls back to live filters when the panel stored no return path", () => {
    localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({ ...SCOPE }));
    const r = renderShell(false);
    act(() => { screen.getByRole("button", { name: "narrow" }).click(); });
    r.rerender(<Shell showBanner={true} />);
    expect(screen.getByTestId("campaign").textContent).toBe("");
    const stored = JSON.parse(localStorage.getItem(SAMPLE_SCOPE_KEY) ?? "null");
    expect(stored.prev).toEqual({ campaign: "my-real-campaign" });
  });

  it("re-asserts pack dates after a full load without touching the return path", () => {
    localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({
      ...SCOPE, prev: { campaign: "my-real-campaign" }, applied: true,
    }));
    // Fresh load: filter state is pristine, stored scope survives.
    renderShell(true);
    expect(screen.getByTestId("from").textContent).toBe(SCOPE.from);
    expect(screen.getByTestId("to").textContent).toBe(SCOPE.to);
    const stored = JSON.parse(localStorage.getItem(SAMPLE_SCOPE_KEY) ?? "null");
    expect(stored.prev).toEqual({ campaign: "my-real-campaign" });
    expect(screen.getByRole("status")).not.toBeNull();
  });

  it("leaves in-demo customisations alone on remount", () => {
    localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({
      ...SCOPE, prev: {}, applied: true,
    }));
    const r = renderShell(true);
    act(() => { screen.getByRole("button", { name: "narrow" }).click(); });
    expect(screen.getByTestId("campaign").textContent).toBe("my-real-campaign");
    // In-app navigation remounts the banner with customised filters.
    r.rerender(<Shell showBanner={false} />);
    r.rerender(<Shell showBanner={true} />);
    expect(screen.getByTestId("campaign").textContent).toBe("my-real-campaign");
    expect(screen.getByTestId("from").textContent).toBe(SCOPE.from);
    const stored = JSON.parse(localStorage.getItem(SAMPLE_SCOPE_KEY) ?? "null");
    expect(stored.prev).toEqual({});
  });

  it("return restores the saved filters and clears the scope", () => {
    localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify({
      ...SCOPE, prev: { campaign: "my-real-campaign" }, applied: true,
    }));
    renderShell(true);
    act(() => { screen.getByRole("button", { name: /return to my scope/i }).click(); });
    expect(screen.getByTestId("campaign").textContent).toBe("my-real-campaign");
    expect(screen.getByTestId("from").textContent).toBe("");
    expect(localStorage.getItem(SAMPLE_SCOPE_KEY)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
