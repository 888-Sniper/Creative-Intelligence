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
      screen.getByText("How are your campaigns performing? What creatives are winning? What needs attention?"),
    ).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText("$200.00")).toBeDefined();
    });
    expect(screen.getAllByText("across 2 campaigns").length).toBeGreaterThan(0);
    expect(screen.getByText("Best CPA")).toBeDefined();
    expect(screen.getByText("$12.05")).toBeDefined();
    expect(screen.getByText("15,000")).toBeDefined();
    expect(screen.getByText("Meta: ok @ 2026-09-01 (2 new, 1 updated)", { exact: false })).toBeDefined();
    expect(screen.getByText("Scheduled jobs: meta.", { exact: false })).toBeDefined();
    expect(
      screen.getByText("Providers: mock mode — set CREATIVE_INTEL_PROVIDER_MODE=live", { exact: false }),
    ).toBeDefined();
    const campaignsCall = seen.find((c) => c.url.startsWith("/api/campaigns"));
    expect(campaignsCall).toBeDefined();
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
      expect(screen.getByText("Inserted 3 rows.")).toBeDefined();
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
    fireEvent.click(screen.getByRole("button", { name: "Sync Meta now" }));
    await waitFor(() => {
      expect(screen.getByText("Synced meta: 2 new, 1 updated (0 quarantined).")).toBeDefined();
    });
    const run = seen.find((c) => c.url === "/api/sync/run");
    expect(run?.method).toBe("POST");
    expect(run?.body).toEqual({ source: "meta" });
  });

  it("shows the server fixture command instead of inventing rows", async () => {
    mockDefault();
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Load Fixture (server --load-fixture)" }));
    expect(
      screen.getByText("Run: python3 Backend/server.py --load-fixture --db Data/local.db"),
    ).toBeDefined();
    expect(seen.some((c) => c.url === "/api/ingest")).toBe(false);
  });
});
