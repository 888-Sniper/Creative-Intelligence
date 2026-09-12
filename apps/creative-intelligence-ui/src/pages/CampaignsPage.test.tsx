import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CampaignsPage } from "@/pages/CampaignsPage";
import { FilterProvider } from "@/state/FilterContext";

const comparePayload = {
  current_period: { start: "2026-06-01", end: "2026-08-29" },
  previous_period: { start: "2026-03-01", end: "2026-05-30" },
  comparison: "90d vs prior 90d",
  metrics: {
    impressions: { state: "up", direction: "up", sentiment: "good", percent_change: 24, current: 125400000, previous: 101000000, abs_change: 24400000 },
    clicks: { state: "up", direction: "up", sentiment: "good", percent_change: 32, current: 1800000, previous: 1360000, abs_change: 440000 },
    spend: { state: "up", direction: "up", sentiment: "neutral", percent_change: 12, current: 412600, previous: 368000, abs_change: 44600 },
    roas: { state: "up", direction: "up", sentiment: "good", percent_change: 28, current: 3.6, previous: 2.8, abs_change: 0.8 },
  },
};

const campaigns = {
  Alpha: { spend: 120.5, impressions: 1000, clicks: 20, conversions: 8, revenue: 168, ctr: 0.02, cpc: 6.0, cpa: 15.06, roas: 1.4, campaigns: 1 },
  Beta: { spend: 40, impressions: 500, clicks: 10, conversions: 2, revenue: 40, ctr: 0.02, cpc: 4.0, cpa: 20.0, roas: 1.0, campaigns: 1 },
};

const detail = {
  name: "Alpha",
  totals: { spend: 120.5, impressions: 1000, clicks: 20, conversions: 8, revenue: 168, ctr: 0.02, cpc: 6.0, cpa: 15.06, roas: 1.4 },
  top_creatives: [],
  recommendations: ["Scale Alpha while CPA holds."],
};

function fetchFor(full: Record<string, unknown>) {
  const mock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.startsWith("/api/campaigns/Alpha")) return Response.json(full.detail);
    if (url.startsWith("/api/campaigns/meta")) return Response.json(full.meta ?? { campaigns: [] });
    if (url.startsWith("/api/kpis/compare")) return Response.json(full.comparePayload);
    if (url.startsWith("/api/kpis/daily")) return Response.json({ days: [] });
    if (url.startsWith("/api/benchmarks")) return Response.json({});
    if (url.startsWith("/api/campaigns")) return Response.json(full.campaigns);
    return Response.json({});
  });
  return { fetch: mock as unknown as typeof fetch, mock };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FilterProvider>
        <CampaignsPage />
      </FilterProvider>
    </MemoryRouter>,
  );
}

describe("CampaignsPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the campaign table with mocked data", async () => {
    window.fetch = fetchFor({ campaigns, comparePayload, detail }).fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("All Campaigns (2)")).toBeDefined();
    });
    expect(screen.getAllByText("Alpha").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Beta").length).toBeGreaterThan(0);
    expect(screen.getByText("$121")).toBeDefined();
    expect(screen.getByRole("button", { name: "Apply Filters" })).toBeDefined();
    expect(screen.getByLabelText("Search campaigns")).toBeDefined();
    expect(screen.getByText("Total Campaigns")).toBeDefined();
  });

  it("shows skeletons while loading", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    const { container } = renderPage();
    expect(container.querySelector(".skel")).not.toBeNull();
  });

  it("renders list errors", async () => {
    window.fetch = vi.fn(async () =>
      Response.json({ error: "db is locked" }, { status: 409 }),
    ) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      // API failures surface as real error copy (KPI + table blocks),
      // never as permanent skeletons.
      expect(screen.getAllByText("db is locked").length).toBeGreaterThanOrEqual(2);
    });
  });

  it("offers real team options and scopes requests on pick", async () => {
    const meta = {
      campaigns: [
        { name: "Alpha", client: "Acme", team: "Growth", platforms: ["meta"], markets: [], objectives: [], verticals: [], last_date: "2026-08-01", status: "Active" },
        { name: "Beta", client: "Acme", team: "Brand", platforms: ["tiktok"], markets: [], objectives: [], verticals: [], last_date: "2026-08-01", status: "Active" },
      ],
    };
    const { fetch, mock: fetchMock } = fetchFor({ campaigns, comparePayload, detail, meta });
    window.fetch = fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("All Campaigns (2)")).toBeDefined();
    });
    const team = screen.getByLabelText("Team") as HTMLSelectElement;
    expect(team.disabled).toBe(false);
    expect([...team.options].map((o) => o.value)).toEqual(["", "Brand", "Growth"]);
    fireEvent.change(team, { target: { value: "Growth" } });
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u: string) => u.includes("/api/campaigns?") && u.includes("team=Growth"))).toBe(true);
    });
  });

  it("keeps a short Campaign Status label with an info explainer", async () => {
    window.fetch = fetchFor({ campaigns, comparePayload, detail }).fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("All Campaigns (2)")).toBeDefined();
    });
    expect(screen.getByLabelText("Campaign Status")).toBeDefined();
    expect(screen.queryByText(/activity-based/)).toBeNull();
    const info = screen.getByRole("button", { name: "How campaign status is determined" });
    // Explainer opens on click (touch/keyboard path) and closes on Escape.
    expect(screen.queryByText(/Activity-derived status/)).toBeNull();
    fireEvent.click(info);
    expect(screen.getByText(/Activity-derived status/)).toBeDefined();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText(/Activity-derived status/)).toBeNull();
  });

  it("presents a single Date Range group for From/To", async () => {
    window.fetch = fetchFor({ campaigns, comparePayload, detail }).fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("All Campaigns (2)")).toBeDefined();
    });
    expect(screen.getAllByText("Date Range")).toHaveLength(1);
    expect(screen.queryByLabelText("From date")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /All Time|–/ }));
    const from = screen.getByLabelText("From date");
    const to = screen.getByLabelText("To date");
    expect(from.closest(".daterange-pop")).toBe(to.closest(".daterange-pop"));
  });

  it("opens campaign details with totals and recommendations", async () => {
    window.fetch = fetchFor({ campaigns, comparePayload, detail }).fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("All Campaigns (2)")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Details for Alpha" }));
    await waitFor(() => {
      expect(screen.getByText("Top Creatives")).toBeDefined();
    });
    expect(screen.getByText("Scale Alpha while CPA holds.")).toBeDefined();
  });
});
