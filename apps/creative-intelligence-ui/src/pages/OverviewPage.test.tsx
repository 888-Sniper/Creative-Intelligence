import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FilterProvider } from "@/state/FilterContext";
import { OverviewPage } from "@/pages/OverviewPage";

const campaignData = {
  "Spring Sale": {
    n_ads: 4,
    spend: 120.5,
    impressions: 10000,
    clicks: 250,
    conversions: 10,
    video_views: 3000,
    revenue: 400,
    cpa: 12.05,
  },
  "Winter Push": {
    n_ads: 2,
    spend: 79.5,
    impressions: 5000,
    clicks: 100,
    conversions: 5,
    video_views: 1000,
    revenue: 100,
    cpa: 15.9,
  },
};

const syncData = {
  sources: {
    meta: { last_finished_at: "2026-09-01", last_status: "ok", last_inserted: 2, last_updated: 1 },
  },
  jobs: ["meta"],
};

const statusData = { mode: "mock", capabilities: {} };

const compareData = {
  current_period: { start: "2024-01-01", end: "2024-01-07" },
  previous_period: { start: "2023-12-25", end: "2023-12-31" },
  comparison: "previous_period",
  metrics: {
    spend: { current: 200, previous: 100, abs_change: 100, percent_change: 100, direction: "up", sentiment: "neutral", state: "compared" },
    impressions: { current: 15000, previous: 12000, abs_change: 3000, percent_change: 25, direction: "up", sentiment: "good", state: "compared" },
    cpm: { current: 13.33, previous: 8.33, abs_change: 5, percent_change: 60, direction: "up", sentiment: "bad", state: "compared" },
    view_rate: { current: 0.2, previous: 0.2, abs_change: 0, percent_change: 0, direction: "flat", sentiment: "neutral", state: "compared" },
    ctr: { current: 0.023, previous: 0.02, abs_change: 0.003, percent_change: 15, direction: "up", sentiment: "good", state: "compared" },
    cpa: { current: 13.33, previous: 20, abs_change: -6.67, percent_change: -33.3, direction: "down", sentiment: "good", state: "compared" },
    roas: { current: 2.5, previous: null, abs_change: null, percent_change: null, direction: "up", sentiment: "neutral", state: "new" },
  },
};

interface SeenCall {
  url: string;
  method?: string;
  body: unknown;
}

let seen: SeenCall[];

function mockFetch(
  impl: (url: string, init?: RequestInit) => Promise<Response> | Response,
) {
  seen = [];
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    let body: unknown;
    try {
      body = init?.body ? JSON.parse(String(init.body)) : undefined;
    } catch {
      body = init?.body;
    }
    seen.push({ url, method: init?.method, body });
    return impl(url, init);
  }) as unknown as typeof fetch;
}

function mockDefault() {
  mockFetch((url) => {
    if (url.startsWith("/api/campaigns")) return Response.json(campaignData);
    if (url === "/api/sync/status") return Response.json(syncData);
    if (url === "/api/providers/status") return Response.json(statusData);
    if (url === "/api/ingest") return Response.json({ inserted: 3, updated: 0, quarantined_count: 0 });
    if (url === "/api/sync/run") return Response.json({ inserted: 2, updated: 1, quarantined_count: 0 });
    if (url.startsWith("/api/kpis/compare")) return Response.json(compareData);
    return Response.json({ error: "unexpected " + url }, { status: 500 });
  });
}

function renderPage() {
  return render(
    <FilterProvider>
      <OverviewPage />
    </FilterProvider>,
  );
}

describe("OverviewPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders KPI cards, sync ledger and provider status from mocked data", async () => {
    mockDefault();
    renderPage();
    expect(screen.getByText("Overview")).toBeDefined();
    expect(
      screen.getByText("Your creative performance at a glance."),
    ).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText("$200.00")).toBeDefined();
    });
    expect(screen.getAllByText("Across 2 Campaigns").length).toBeGreaterThan(0);
    expect(screen.getByText("Best CPA")).toBeDefined();
    expect(screen.getByText("$12.05")).toBeDefined();
    expect(screen.getByText("15,000")).toBeDefined();
    expect(screen.getByText("Meta: OK @ 2026-09-01 (2 New, 1 Updated)", { exact: false })).toBeDefined();
    expect(screen.getByText("Scheduled Jobs: Meta.", { exact: false })).toBeDefined();
    expect(
      screen.getByText("Providers: Mock Mode — Set CREATIVE_INTEL_PROVIDER_MODE=live", { exact: false }),
    ).toBeDefined();
    const campaignsCall = seen.find((c) => c.url.startsWith("/api/campaigns"));
    expect(campaignsCall).toBeDefined();
  });

  it("renders period comparisons beside context, with tooltips", async () => {
    mockDefault();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("+25%")).toBeDefined();
    });
    // Context stays visible and separate from the comparison.
    expect(screen.getAllByText("Across 2 Campaigns").length).toBeGreaterThan(0);
    // Negative-good CPA trend and new-state ROAS trend render too.
    expect(screen.getByText("-33.3%")).toBeDefined();
    expect(screen.getByText("New")).toBeDefined();
    // The compare call carries the same scope as the campaigns call.
    const campaignsCall = seen.find((c) => c.url.startsWith("/api/campaigns"));
    const compareCall = seen.find((c) => c.url.startsWith("/api/kpis/compare"));
    expect(compareCall).toBeDefined();
    const campQuery = String(campaignsCall?.url).split("?")[1] ?? "";
    const compQuery = String(compareCall?.url).split("?")[1] ?? "";
    expect(new URLSearchParams(compQuery).toString()).toBe(
      new URLSearchParams(campQuery).toString(),
    );
    // Tooltip opens on focus with the real previous range.
    const info = screen.getAllByRole("button", { name: "Explain Comparison Period" })[0];
    fireEvent.focus(info);
    expect(screen.getByRole("tooltip").textContent).toContain("Dec 25 – Dec 31, 2023");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows no trend without comparison data", async () => {
    mockFetch((url) => {
      if (url.startsWith("/api/campaigns")) return Response.json(campaignData);
      if (url.startsWith("/api/kpis/compare")) {
        return Response.json({ current_period: null, previous_period: null, comparison: null, metrics: {} });
      }
      if (url === "/api/sync/status") return Response.json({ sources: {}, jobs: [] });
      if (url === "/api/providers/status") return Response.json(statusData);
      return Response.json({ error: "unexpected " + url }, { status: 500 });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("$200.00")).toBeDefined();
    });
    expect(screen.queryByRole("button", { name: "Explain Comparison Period" })).toBeNull();
  });

  it("shows the legacy placeholder while KPIs load", async () => {
    let resolveCampaigns!: (v: unknown) => void;
    mockFetch((url) => {
      if (url.startsWith("/api/campaigns")) {
        return new Promise<Response>((resolve) => {
          resolveCampaigns = (v) => resolve(Response.json(v));
        });
      }
      if (url === "/api/sync/status") return Response.json({ sources: {}, jobs: [] });
      if (url === "/api/providers/status") return Response.json(statusData);
      return Response.json({}, { status: 500 });
    });
    renderPage();
    expect(screen.getByText("—")).toBeDefined();
    resolveCampaigns(campaignData);
    await waitFor(() => {
      expect(screen.getByText("$200.00")).toBeDefined();
    });
  });

  it("renders campaign fetch errors in the KPI card", async () => {
    mockFetch((url) => {
      if (url.startsWith("/api/campaigns")) return Response.json({ error: "boom" }, { status: 500 });
      if (url === "/api/sync/status") return Response.json({ sources: {}, jobs: [] });
      if (url === "/api/providers/status") return Response.json(statusData);
      return Response.json({}, { status: 500 });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("boom")).toBeDefined();
    });
  });

  it("uploads CSV and reports the inserted row count", async () => {
    mockDefault();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("$200.00")).toBeDefined();
    });
    fireEvent.change(screen.getByPlaceholderText("Paste CSV export text here"), {
      target: { value: "campaign,spend\nSpring Sale,10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload CSV" }));
    await waitFor(() => {
      expect(screen.getByText("Inserted 3 Rows, 0 Updated (0 Quarantined).")).toBeDefined();
    });
    const ingest = seen.find((c) => c.url === "/api/ingest");
    expect(ingest?.method).toBe("POST");
    expect(ingest?.body).toEqual({ platform: "meta", csv: "campaign,spend\nSpring Sale,10" });
  });

  it("runs a sync and reports new/updated counts", async () => {
    mockDefault();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("$200.00")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Sync Meta Now" }));
    await waitFor(() => {
      expect(screen.getByText("Synced Meta: 2 New, 1 Updated (0 Quarantined).")).toBeDefined();
    });
    const run = seen.find((c) => c.url === "/api/sync/run");
    expect(run?.method).toBe("POST");
    expect(run?.body).toEqual({ source: "meta" });
  });

  it("shows the server fixture command instead of inventing rows", async () => {
    mockDefault();
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Load Fixture (main.py --load-fixture)" }));
    expect(
      screen.getByText("Run: python3 Backend/ci_backend/main.py --load-fixture --db Data/local.db"),
    ).toBeDefined();
    expect(seen.some((c) => c.url === "/api/ingest")).toBe(false);
  });
});
