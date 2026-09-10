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

const creativePayload = {
  ka: {
    spend: 100,
    impressions: 10000,
    clicks: 100,
    conversions: 10,
    cpm: 10,
    vtr: 0.5,
    ctr: 0.01,
    cpc: 1,
    cpa: 10,
    roas: 2,
    annotation: { hook_type: "question", creator_vs_branded: "creator", edit_style: "fast", status: "auto" },
  },
  kb: {
    spend: 100,
    impressions: 10000,
    clicks: 50,
    conversions: 5,
    cpm: 10,
    vtr: 0.4,
    ctr: 0.005,
    cpc: 2,
    cpa: 20,
    roas: 1,
    annotation: { hook_type: "demo_open", creator_vs_branded: "branded", edit_style: "slow", status: "auto" },
  },
  keys: ["ka", "kb"],
  ranking: ["ka", "kb"],
  winner: "ka",
  rank_by: "cpa",
  scope: "All data",
  why: { top: "ka", differences: ["ka leads kb on CPA (10 vs 20)"] },
  attributes: [{ attribute: "Hook type", values: { ka: "question", kb: "demo_open" } }],
};

const campaignPayload = {
  kpis: {
    "Camp A": { spend: 500, impressions: 50000, clicks: 500, conversions: 50, cpm: 10, vtr: 0.5, ctr: 0.01, cpa: 10, roas: 2 },
    "Camp B": { spend: 300, impressions: 20000, clicks: 100, conversions: 10, cpm: 15, vtr: 0.3, ctr: 0.005, cpa: 30, roas: 1 },
  },
  ranking: ["Camp A", "Camp B"],
  winner: "Camp A",
  rank_by: "cpa",
  why: { top: "Camp A", bottom: "Camp B", differences: ["hook_type differs: Camp A has question; Camp B has demo_open"] },
  scope: "All data",
};

const periodPayload = {
  a: { label: "Period A", from: "2026-08-01", to: "2026-08-07", n_ads: 10, kpis: { spend: 100, impressions: 1000, clicks: 10, conversions: 2, cpm: 100, vtr: 0.5, ctr: 0.01, cpc: 10, cpa: 50, roas: 1.5 } },
  b: { label: "Period B", from: "2026-08-08", to: "2026-08-14", n_ads: 12, kpis: { spend: 120, impressions: 1200, clicks: 12, conversions: 3, cpm: 100, vtr: 0.5, ctr: 0.01, cpc: 10, cpa: 40, roas: 1.8 } },
  delta: { spend: 20, impressions: 200, clicks: 2, conversions: 1, cpm: 0, vtr: 0, ctr: 0, cpc: 0, cpa: -10, roas: 0.3 },
  scope: "All data",
};

function mockFetchAll() {
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.startsWith("/api/compare/campaigns")) return Response.json(campaignPayload);
    if (url.startsWith("/api/compare/periods")) return Response.json(periodPayload);
    if (url.startsWith("/api/compare")) return Response.json(creativePayload);
    return Response.json({ error: "not found" }, { status: 404 });
  }) as unknown as typeof fetch;
}

describe("ComparePage", () => {
  it("renders all three compare modes", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "Compare creatives" })).toBeDefined();
    expect(screen.getByText("Campaign compare")).toBeDefined();
    expect(screen.getByText("Period comparison")).toBeDefined();
    expect(screen.getByLabelText("Rank creatives by")).toBeDefined();
    expect(screen.getByLabelText("Rank campaigns by")).toBeDefined();
  });

  it("compares creatives side by side with winner copy", async () => {
    mockFetchAll();
    renderPage();
    fireEvent.change(screen.getByPlaceholderText("creative A key"), { target: { value: "ka" } });
    fireEvent.change(screen.getByPlaceholderText("creative B key"), { target: { value: "kb" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare creatives" }));
    await waitFor(() => {
      expect(screen.getByText("Why ka won")).toBeDefined();
    });
    expect(screen.getByText(/Winner by CPA: ka/)).toBeDefined();
    expect(screen.getByText("Attributes side-by-side")).toBeDefined();
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("key=ka");
    expect(calledUrl).toContain("key=kb");
    expect(calledUrl).toContain("rank_by=cpa");
  });

  it("shows a loading state while comparing", async () => {
    let resolveFetch!: (r: Response) => void;
    window.fetch = vi.fn(
      () => new Promise<Response>((res) => { resolveFetch = res; }),
    ) as unknown as typeof fetch;
    renderPage();
    fireEvent.change(screen.getByPlaceholderText("creative A key"), { target: { value: "ka" } });
    fireEvent.change(screen.getByPlaceholderText("creative B key"), { target: { value: "kb" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare creatives" }));
    await waitFor(() => {
      expect(screen.getByText("Loading…")).toBeDefined();
    });
    resolveFetch(Response.json(creativePayload));
    await waitFor(() => {
      expect(screen.getByText("Why ka won")).toBeDefined();
    });
  });

  it("renders API errors for creative compare", async () => {
    window.fetch = vi.fn(async () => Response.json({ error: "boom" }, { status: 500 })) as unknown as typeof fetch;
    renderPage();
    fireEvent.change(screen.getByPlaceholderText("creative A key"), { target: { value: "ka" } });
    fireEvent.change(screen.getByPlaceholderText("creative B key"), { target: { value: "kb" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare creatives" }));
    await waitFor(() => {
      expect(screen.getByText("boom")).toBeDefined();
    });
  });

  it("requires at least two creative keys", async () => {
    mockFetchAll();
    renderPage();
    fireEvent.change(screen.getByPlaceholderText("creative A key"), { target: { value: "ka" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare creatives" }));
    await waitFor(() => {
      expect(screen.getByText("Enter at least two creative keys (up to six).")).toBeDefined();
    });
    expect(window.fetch as unknown as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
  });

  it("compares campaigns with why-analysis", async () => {
    mockFetchAll();
    renderPage();
    fireEvent.change(screen.getByPlaceholderText("campaigns, comma-separated (blank = all)"), {
      target: { value: "Camp A, Camp B" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Compare campaigns" }));
    await waitFor(() => {
      expect(screen.getByText("Why Camp A won")).toBeDefined();
    });
    expect(screen.getByText("Ranked by cpa")).toBeDefined();
    expect(screen.getByText("Winner by CPA: Camp A")).toBeDefined();
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(calledUrl.startsWith("/api/compare/campaigns")).toBe(true);
    expect(calledUrl).toContain("rank_by=cpa");
  });

  it("requires all four period dates", async () => {
    mockFetchAll();
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Compare periods" }));
    await waitFor(() => {
      expect(screen.getByText("Fill all four period dates.")).toBeDefined();
    });
    expect(window.fetch as unknown as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
  });

  it("compares periods with a B−A delta table", async () => {
    mockFetchAll();
    renderPage();
    fireEvent.change(screen.getByLabelText("A from"), { target: { value: "2026-08-01" } });
    fireEvent.change(screen.getByLabelText("A to"), { target: { value: "2026-08-07" } });
    fireEvent.change(screen.getByLabelText("B from"), { target: { value: "2026-08-08" } });
    fireEvent.change(screen.getByLabelText("B to"), { target: { value: "2026-08-14" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare periods" }));
    await waitFor(() => {
      expect(screen.getByText("B−A")).toBeDefined();
    });
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(calledUrl.startsWith("/api/compare/periods")).toBe(true);
    expect(calledUrl).toContain("a_from=2026-08-01");
  });
});
