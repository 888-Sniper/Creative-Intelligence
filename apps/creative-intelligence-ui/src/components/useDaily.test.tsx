import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useDaily } from "@/components/product";
import { FilterProvider, useFilters } from "@/state/FilterContext";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Probe() {
  const { setFilter } = useFilters();
  const state = useDaily(30);
  const label = state.loading
    ? "loading"
    : state.error || (state.data ? `days:${state.data.length}` : "no-data");
  return (
    <>
      <button type="button" onClick={() => setFilter("campaign", "Next")}>Next Scope</button>
      <span>{label}</span>
    </>
  );
}

function renderProbe() {
  return render(
    <FilterProvider>
      <Probe />
    </FilterProvider>,
  );
}

describe("useDaily", () => {
  it("keeps a successful empty series distinct from a rejected request", async () => {
    window.fetch = vi.fn(async () => Response.json({ days: [] })) as unknown as typeof fetch;
    renderProbe();
    await waitFor(() => {
      expect(screen.getByText("days:0")).toBeDefined();
    });
  });

  it("reports a rejected daily request instead of an empty series", async () => {
    window.fetch = vi.fn(async () => Response.json(
      { error: "daily down" },
      { status: 503 },
    )) as unknown as typeof fetch;
    renderProbe();
    await waitFor(() => {
      expect(screen.getByText("daily down")).toBeDefined();
    });
    expect(screen.queryByText("days:0")).toBeNull();
    expect(screen.queryByText("no-data")).toBeNull();
  });

  it("hides the previous series on the first render of a new scope", async () => {
    let releaseNext: (value: Response) => void = () => {};
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("campaign=Next")) {
        return new Promise<Response>((resolve) => { releaseNext = resolve; });
      }
      return Response.json({
        days: [{ date: "2026-07-01", impressions: 1, clicks: 1, spend: 1, conversions: 1, revenue: 1 }],
      });
    }) as unknown as typeof fetch;
    renderProbe();
    await waitFor(() => {
      expect(screen.getByText("days:1")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Next Scope" }));
    expect(screen.getByText("loading")).toBeDefined();
    expect(screen.queryByText("days:1")).toBeNull();
    releaseNext(Response.json({ days: [] }));
    await waitFor(() => {
      expect(screen.getByText("days:0")).toBeDefined();
    });
  });
});
