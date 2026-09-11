import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FilterProvider } from "@/state/FilterContext";
import { ComparePage } from "@/pages/ComparePage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <FilterProvider>
      <ComparePage />
    </FilterProvider>,
  );
}

const campaignPayload = {
  kpis: {
    "Camp A": { spend: 500, impressions: 50000, clicks: 500, conversions: 50, cpm: 10, vtr: 0.5, ctr: 0.01, cpa: 10, roas: 2 },
    "Camp B": { spend: 300, impressions: 20000, clicks: 100, conversions: 10, cpm: 15, vtr: 0.3, ctr: 0.005, cpa: 30, roas: 1 },
  },
  ranking: ["Camp A", "Camp B"],
  winner: "Camp A",
  rank_by: "roas",
  why: { top: "Camp A leads on ROAS", differences: ["Camp A leads Camp B on ROAS (2 vs 1)"] },
  scope: "All data",
};

const creativePayload = {
  ka: {
    spend: 100, impressions: 10000, clicks: 100, conversions: 10, cpm: 10, vtr: 0.5, ctr: 0.01, cpc: 1, cpa: 10, roas: 2,
    annotation: { hook_type: "question", creator_vs_branded: "creator", edit_style: "fast", status: "auto" },
  },
  kb: {
    spend: 100, impressions: 10000, clicks: 50, conversions: 5, cpm: 10, vtr: 0.4, ctr: 0.005, cpc: 2, cpa: 20, roas: 1,
    annotation: { hook_type: "demo_open", creator_vs_branded: "branded", edit_style: "slow", status: "auto" },
  },
  keys: ["ka", "kb"],
  ranking: ["ka", "kb"],
  winner: "ka",
  rank_by: "roas",
  scope: "All data",
  why: { top: "ka", differences: ["ka leads kb on ROAS (2 vs 1)"] },
  attributes: [{ attribute: "Hook type", values: { ka: "question", kb: "demo_open" } }],
};

const periodPayload = {
  a: { label: "Period A", from: "2026-08-01", to: "2026-08-07", n_ads: 10, kpis: { spend: 100, roas: 1.5 } },
  b: { label: "Period B", from: "2026-08-08", to: "2026-08-14", n_ads: 12, kpis: { spend: 120, roas: 1.8 } },
  delta: { spend: 20, roas: 0.3 },
  scope: "All data",
};

const campaignOptions = {
  "Camp A": { spend: 500, impressions: 50000, clicks: 500, conversions: 50, revenue: 1000, ctr: 0.01, cpa: 10, roas: 2 },
  "Camp B": { spend: 300, impressions: 20000, clicks: 100, conversions: 10, revenue: 300, ctr: 0.005, cpa: 30, roas: 1 },
};

const creativeOptions = [
  { creative_key: "ka", name: "KA", platform: "meta", campaigns: ["Camp A"], metrics: {}, annotation: { duration_s: 28 } },
  { creative_key: "kb", name: "KB", platform: "tiktok", campaigns: ["Camp B"], metrics: {}, annotation: { duration_s: 23 } },
];

function mockFetchAll() {
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.startsWith("/api/compare/campaigns")) return Response.json(campaignPayload);
    if (url.startsWith("/api/compare/periods")) return Response.json(periodPayload);
    if (url.startsWith("/api/compare")) return Response.json(creativePayload);
    if (url.startsWith("/api/kpis/daily")) return Response.json({ days: [] });
    if (url.startsWith("/api/retention/curve")) return Response.json({ points: [] });
    if (url.startsWith("/api/creatives")) return Response.json(creativeOptions);
    if (url.startsWith("/api/campaigns")) return Response.json(campaignOptions);
    return Response.json({ error: "not found" }, { status: 404 });
  }) as unknown as typeof fetch;
}

describe("ComparePage", () => {
  it("auto-runs a campaign comparison on first load", async () => {
    mockFetchAll();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Performance Over Time")).toBeDefined();
    });
    expect(screen.getAllByText("Camp A").length).toBeGreaterThan(0);
    expect(screen.getByText("KPI Comparison")).toBeDefined();
    expect(screen.getByText("Difference Summary")).toBeDefined();
    expect(screen.getByText("Creative Attributes Comparison")).toBeDefined();
    expect(screen.getByText("Key Takeaways")).toBeDefined();
    expect(screen.getByText("Recommended Next Tests")).toBeDefined();
    expect(screen.getByText("Camp A leads Camp B on ROAS (2 vs 1)")).toBeDefined();
  });

  it("compares creatives with chips and backend ranking", async () => {
    mockFetchAll();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Performance Over Time")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Compare By"), { target: { value: "creatives" } });
    const add = screen.getByLabelText("Select Creatives");
    fireEvent.change(add, { target: { value: "kb" } });
    fireEvent.change(screen.getByLabelText("Select Creatives"), { target: { value: "ka" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply Comparison" }));
    await waitFor(() => {
      expect(screen.getByText("Hook type")).toBeDefined();
    });
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    const called = fetchMock.mock.calls.map((c) => String(c[0]));
    const cmpCall = called.find((u) => u.startsWith("/api/compare?")) ?? "";
    expect(cmpCall).toContain("key=kb");
    expect(cmpCall).toContain("key=ka");
    expect(cmpCall).toContain("rank_by=roas");
  });

  it("shows a loading state while comparing", async () => {
    let resolveFetch!: (r: Response) => void;
    mockFetchAll();
    const base = window.fetch;
    window.fetch = vi.fn((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/compare/campaigns")) {
        return new Promise<Response>((res) => { resolveFetch = res; });
      }
      return (base as typeof fetch)(input, init);
    }) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Remove Camp A" })).toBeDefined();
    });
    // The boot auto-run is still pending, so the button already shows its loading state.
    expect(screen.getByText("Comparing…")).toBeDefined();
    resolveFetch(Response.json(campaignPayload));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Apply Comparison" })).toBeDefined();
    });
    expect(screen.getByText("Performance Over Time")).toBeDefined();
  });

  it("renders API errors", async () => {
    window.fetch = vi.fn(async () =>
      Response.json({ error: "boom" }, { status: 500 }),
    ) as unknown as typeof fetch;
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Apply Comparison" }));
    await waitFor(() => {
      expect(screen.getByText(/Select At Least Two/)).toBeDefined();
    });
  });

  it("compares periods with a B−A delta table", async () => {
    mockFetchAll();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Performance Over Time")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("A From"), { target: { value: "2026-08-01" } });
    fireEvent.change(screen.getByLabelText("A To"), { target: { value: "2026-08-07" } });
    fireEvent.change(screen.getByLabelText("B From"), { target: { value: "2026-08-08" } });
    fireEvent.change(screen.getByLabelText("B To"), { target: { value: "2026-08-14" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare Periods" }));
    await waitFor(() => {
      expect(screen.getByText("B−A")).toBeDefined();
    });
    expect(screen.getByText(/Period A \(2026-08-01/)).toBeDefined();
  });
});
