import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FilterProvider } from "@/state/FilterContext";
import { CreativesPage } from "@/pages/CreativesPage";

const comparePayload = {
  current_period: { start: "2026-06-01", end: "2026-08-29" },
  previous_period: { start: "2026-03-01", end: "2026-05-30" },
  comparison: "90d vs prior 90d",
  metrics: {
    impressions: { state: "up", direction: "up", sentiment: "good", percent_change: 32, current: 412600000, previous: 312000000, abs_change: 100600000 },
    clicks: { state: "up", direction: "up", sentiment: "good", percent_change: 24, current: 7800000, previous: 6290000, abs_change: 1510000 },
    roas: { state: "up", direction: "up", sentiment: "good", percent_change: 18, current: 3.6, previous: 3.0, abs_change: 0.6 },
  },
};

const rows = [
  {
    creative_key: "ck-alpha",
    name: "Alpha",
    platform: "meta",
    format: "9:16 Video",
    campaigns: ["Camp A"],
    duration_s: 30,
    metrics: { spend: 100, impressions: 4200000, clicks: 117600, conversions: 1200, revenue: 360, cpa: 2.5, ctr: 0.028, cpc: 0.5, cpm: 5, vtr: 0.4, roas: 3.6 },
    annotation: { hook_type: "question", creator_vs_branded: "creator", duration_s: 30 },
  },
  {
    creative_key: "ck-beta",
    name: "Beta",
    platform: "tiktok",
    format: "9:16 Video",
    campaigns: ["Camp B"],
    duration_s: 15,
    metrics: { spend: 50, impressions: 2100000, clicks: 39900, conversions: 400, revenue: 105, cpa: 5, ctr: 0.019, cpc: 1, cpm: 6, vtr: 0.3, roas: 2.1 },
    annotation: { hook_type: "offer", creator_vs_branded: "branded", duration_s: 15 },
  },
];

const hooks = {
  question: { spend: 100, impressions: 4200000, clicks: 117600, conversions: 1200, revenue: 360, ctr: 0.028, cpc: 0.85, cpa: 2.5, roas: 3.6 },
  offer: { spend: 50, impressions: 2100000, clicks: 39900, conversions: 400, revenue: 105, ctr: 0.019, cpc: 1.25, cpa: 5, roas: 2.1 },
};

const modes = {
  creator: { spend: 100, impressions: 4200000, clicks: 117600, conversions: 1200, revenue: 360, ctr: 0.028, cpc: 0.85, cpa: 2.5, roas: 3.6 },
  branded: { spend: 50, impressions: 2100000, clicks: 39900, conversions: 400, revenue: 105, ctr: 0.019, cpc: 1.25, cpa: 5, roas: 2.1 },
};

function mockLibrary() {
  window.fetch = vi.fn(async (input: unknown) => {
    const url = String(input);
    if (url.startsWith("/api/kpis/compare")) return Response.json(comparePayload);
    if (url.startsWith("/api/benchmarks?group_by=hook_type")) return Response.json(hooks);
    if (url.startsWith("/api/benchmarks?group_by=creator_vs_branded")) return Response.json(modes);
    if (url.startsWith("/api/benchmarks")) return Response.json({});
    if (url.startsWith("/api/creatives")) return Response.json(rows);
    if (url.startsWith("/api/retention/curve")) {
      return Response.json({ points: [{ t: 0, p: 100 }, { t: 10, p: 80 }] });
    }
    return Response.json({});
  }) as unknown as typeof fetch;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FilterProvider>
        <CreativesPage />
      </FilterProvider>
    </MemoryRouter>,
  );
}

describe("CreativesPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders top cards and the creative table with mocked data", async () => {
    mockLibrary();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Top Performing Creatives")).toBeDefined();
    });
    expect(screen.getAllByText("Alpha").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Sort By")).toBeDefined();
    expect(screen.getByRole("button", { name: "Apply Filters" })).toBeDefined();
    expect(screen.getByText("Top Learnings")).toBeDefined();
    expect(screen.getByText("Recommended Tests")).toBeDefined();
  });

  it("shows skeletons while loading", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    const { container } = renderPage();
    expect(container.querySelector(".skel")).not.toBeNull();
  });

  it("renders fetch errors", async () => {
    window.fetch = vi.fn(async () =>
      Response.json({ error: "boom" }, { status: 500 }),
    ) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("boom")).toBeDefined();
    });
  });

  it("opens creative details with annotation facts and retention", async () => {
    mockLibrary();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Top Performing Creatives")).toBeDefined();
    });
    const names = screen.getAllByRole("button", { name: "Alpha" });
    fireEvent.click(names[0]);
    await waitFor(() => {
      expect(screen.getByText("Audience Retention")).toBeDefined();
    });
    expect(screen.getByText("Objective")).toBeDefined();
  });
});
