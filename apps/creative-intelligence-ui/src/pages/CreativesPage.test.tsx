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
  {
    // Heavy branded winner: the branded pool beats the creator pool,
    // so the heading must crown branded — never a fixed creator phrase.
    creative_key: "ck-gamma",
    name: "Gamma",
    platform: "meta",
    format: "9:16 Video",
    campaigns: ["Camp C"],
    duration_s: 45,
    metrics: { spend: 200, impressions: 10000000, clicks: 350000, conversions: 2000, revenue: 900, cpa: 4, ctr: 0.035, cpc: 0.8, cpm: 7, vtr: 0.35, roas: 4.5 },
    annotation: { hook_type: "testimonial", creator_vs_branded: "branded", duration_s: 45 },
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

  it("crowns the real leader and scopes every section to the length filter", async () => {
    mockLibrary();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Top Performing Creatives")).toBeDefined();
    });
    // Branded pool (3.2%) beats creator pool (2.8%): the heading must
    // say so instead of a fixed creator phrase.
    await waitFor(() => {
      expect(screen.getByText("Branded Hooks Perform Best")).toBeDefined();
    });
    expect(screen.queryByText("Creator-Led Hooks Perform Best")).toBeNull();
    expect(screen.getByText("Testimonial Hooks Lead CTR")).toBeDefined();
    // Narrow to long videos: only Gamma survives anywhere.
    fireEvent.change(screen.getByLabelText("Video Length"), { target: { value: "long" } });
    await waitFor(() => {
      expect(screen.queryByText("Alpha")).toBeNull();
    });
    expect(screen.queryByText("Beta")).toBeNull();
    expect(screen.getAllByText("Gamma").length).toBeGreaterThan(0);
    // Single-group learnings stay neutral; the duel disappears.
    expect(screen.queryByText("Branded Hooks Perform Best")).toBeNull();
    expect(screen.getByText("Over 30s Videos Snapshot")).toBeDefined();
    // KPIs describe the filtered group (Gamma only).
    expect(screen.getByText("Showing over-30s creatives only.")).toBeDefined();
  });

  it("shows an empty state instead of test ideas when zero creatives", async () => {
    window.fetch = vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url.startsWith("/api/kpis/compare")) return Response.json(comparePayload);
      if (url.startsWith("/api/creatives")) return Response.json([]);
      if (url.startsWith("/api/benchmarks")) return Response.json({});
      return Response.json({});
    }) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Not enough data for recommendations yet.")).toBeDefined();
    });
    expect(screen.queryByText("Test Creator vs. Branded Intros")).toBeNull();
    expect(screen.queryByText("Try Shorter Video Lengths")).toBeNull();
    expect(screen.queryByText("Experiment With New Hook Types")).toBeNull();
    expect(screen.getByText("Not enough data for learnings yet.")).toBeDefined();
  });

  it("reset restores the full scope and local view state", async () => {
    mockLibrary();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Top Performing Creatives")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Video Length"), { target: { value: "long" } });
    await waitFor(() => {
      expect(screen.queryByText("Alpha")).toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset Filters" }));
    await waitFor(() => {
      expect(screen.getAllByText("Alpha").length).toBeGreaterThan(0);
    });
    expect((screen.getByLabelText("Video Length") as HTMLSelectElement).value).toBe("all");
    expect(screen.getByText("Branded Hooks Perform Best")).toBeDefined();
  });
});
