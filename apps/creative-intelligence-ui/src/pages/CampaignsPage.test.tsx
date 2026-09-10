import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CampaignsPage } from "@/pages/CampaignsPage";
import { FilterProvider } from "@/state/FilterContext";

const campaigns = {
  Alpha: { n_ads: 4, spend: 120.5, ctr: 0.02, cpc: 1.5, cpa: 12.5 },
  Beta: { n_ads: 2, spend: 40, ctr: 0.05, cpc: 0.8, cpa: 6.0 },
};

const creatives = [
  {
    creative_key: "c1",
    name: "Winner One",
    platform: "meta",
    duration_s: 15,
    campaigns: ["Alpha"],
    metrics: { spend: 80, cpa: 5.0, ctr: 0.04, roas: 2.1 },
    annotation: { hook_type: "question", creator_vs_branded: "creator", duration_s: 15 },
  },
  {
    creative_key: "c2",
    name: "Trailer Two",
    platform: "meta",
    duration_s: 20,
    campaigns: ["Alpha"],
    metrics: { spend: 40, cpa: 20.0, ctr: 0.01, roas: 0.5 },
    annotation: { hook_type: "question", creator_vs_branded: "branded", duration_s: 20 },
  },
];

const bench = {
  Alpha: {
    spend: 120.5, impressions: 1000, clicks: 20, conversions: 8,
    cpm: 5.0, vtr: 0.3, ctr: 0.02, cpc: 1.5, cpa: 12.5, roas: 1.4,
  },
};

const reco = {
  campaign: "Alpha",
  rank_by: "cpa",
  notice: "",
  sections: [
    { title: "Scale", bullets: [{ text: "Scale: c1 — lowest CPA." }] },
  ],
};

function fetchFor(full: Record<string, unknown>) {
  return vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.startsWith("/api/campaigns/recommendations")) return Response.json(full.reco);
    if (url.startsWith("/api/benchmarks")) return Response.json(full.bench);
    if (url.startsWith("/api/creatives")) return Response.json(full.creatives);
    if (url.startsWith("/api/campaigns")) return Response.json(full.campaigns);
    return Response.json({});
  }) as unknown as typeof fetch;
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

  it("renders the campaign list with mocked data", async () => {
    window.fetch = fetchFor({ campaigns, creatives: [], bench: {}, reco });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Alpha" })).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Beta" })).toBeDefined();
    expect(screen.getByText("$120.5")).toBeDefined();
  });

  it("shows a loading state before data arrives", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    renderPage();
    expect(screen.getByText("Loading campaigns…")).toBeDefined();
  });

  it("renders list errors", async () => {
    window.fetch = vi.fn(async () =>
      Response.json({ error: "db is locked" }, { status: 409 }),
    ) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("db is locked")).toBeDefined();
    });
  });

  it("opens campaign detail with best/watch, ranking and recommendations", async () => {
    window.fetch = fetchFor({ campaigns, creatives, bench, reco });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Alpha" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Alpha" }));
    await waitFor(() => {
      expect(screen.getByText("Best")).toBeDefined();
    });
    expect(screen.getByText("Watch")).toBeDefined();
    expect(screen.getByText("Campaign totals (scoped)")).toBeDefined();
    expect(screen.getByText("Creatives ranked by CPA")).toBeDefined();
    expect(screen.getByText("Creative learning")).toBeDefined();
    expect(screen.getByText("Scale: c1 — lowest CPA.")).toBeDefined();
    expect(screen.getByText(/question hooks lead 2 of 2 creatives here/)).toBeDefined();
  });
});
