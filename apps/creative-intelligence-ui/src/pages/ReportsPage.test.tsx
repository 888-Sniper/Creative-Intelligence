import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ReportsPage } from "@/pages/ReportsPage";
import { __resetCampaignMetaCache } from "@/components/product";
import { FilterProvider } from "@/state/FilterContext";

function renderPage() {
  return render(
    <FilterProvider>
      <ReportsPage />
    </FilterProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

function mockFetch(
  impl: (url: string, init?: { method?: string; body?: string }) => Promise<Response> | Response,
) {
  window.fetch = vi.fn(async (url: unknown, init?: unknown) => {
    const r = await impl(
      String(url),
      init as { method?: string; body?: string } | undefined,
    );
    return r;
  }) as unknown as typeof fetch;
}

const campaignsBody = { "Camp A": { n_ads: 2 }, "Camp B": { n_ads: 1 } };

const metaDemo = {
  campaigns: [
    { name: "Camp A", client: "Acme", team: "Growth", platforms: ["meta"], markets: [], objectives: [], verticals: [], projects: [], last_date: "", status: "Active" },
    { name: "Camp B", client: "Acme", team: "Brand", platforms: ["tiktok"], markets: [], objectives: [], verticals: [], projects: [], last_date: "", status: "Active" },
  ],
  demo: true,
};

function mockCatalog(meta: unknown = metaDemo) {
  mockFetch((url, init) => {
    if (init?.method === "POST") return jsonResponse({});
    if (url.includes("/api/campaigns/meta")) return jsonResponse(meta);
    if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
    return jsonResponse({});
  });
}

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetCampaignMetaCache();
    window.URL.createObjectURL = vi.fn(() => "blob:mock") as unknown as (
      obj: Blob | MediaSource,
    ) => string;
    window.URL.revokeObjectURL = vi.fn();
    try {
      window.localStorage.clear();
    } catch {
      /* storage unavailable */
    }
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the generator with campaign/KPI multiselects and format cards", async () => {
    mockCatalog();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("New Report")).toBeDefined();
    });
    expect(screen.getByText("2 Campaigns Selected")).toBeDefined();
    expect(screen.getByText("5 KPIs Selected")).toBeDefined();
    expect(screen.getByRole("button", { name: /PPTX Presentation Deck/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /XLSX Data Workbook/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /One-Pager Executive Summary/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /Generate Report/ })).toBeDefined();
    expect(screen.getByText("Report Tips")).toBeDefined();
    expect(screen.getByText("Latest Generated Files")).toBeDefined();
  });

  it("labels the estimate briefly and orders tips Tailor before Benchmarks", async () => {
    mockCatalog();
    const { container } = renderPage();
    await waitFor(() => {
      expect(screen.getByText("Report Tips")).toBeDefined();
    });
    expect(screen.getByText("Estimated time: 1–2 minutes")).toBeDefined();
    expect(screen.queryByText(/Estimated generation time/i)).toBeNull();
    const tips = Array.from(
      container.querySelectorAll(".tips-list h4"),
    ).map((h) => h.textContent);
    expect(tips.slice(0, 4)).toEqual([
      "Focus on Key KPIs",
      "Tailor to Your Audience",
      "Choose the Right Format",
      "Use Benchmarks for Context",
    ]);
  });

  it("singularizes the multiselect count at exactly one", async () => {
    mockCatalog();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2 Campaigns Selected")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: /2 Campaigns Selected/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Camp B" }));
    await waitFor(() => {
      expect(screen.getByText("1 Campaign Selected")).toBeDefined();
    });
  });

  it("shows a loading state while the catalog resolves", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    const { container } = renderPage();
    // Loading is a skeleton, never an "empty" message.
    expect(container.querySelector(".skel")).not.toBeNull();
  });

  it("renders catalog errors", async () => {
    mockFetch(() => jsonResponse({ error: "catalog down" }, 500));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("catalog down")).toBeDefined();
    });
  });

  it("generates a PPTX with selected campaigns/KPIs and adds history", async () => {
    let reportBody: Record<string, unknown> = {};
    mockFetch((url, init) => {
      if (url === "/api/report" && init?.method === "POST") {
        reportBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ format: "pptx", filename: "camp-report.pptx", pptx_b64: "eA==" });
      }
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2 Campaigns Selected")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate Report/ }));
    await waitFor(() => {
      expect(screen.getByText("PPTX Built: camp-report.pptx.")).toBeDefined();
    });
    expect(reportBody["format"]).toBe("pptx");
    expect(reportBody["campaigns"]).toEqual(["Camp A", "Camp B"]);
    expect(reportBody["kpis"]).toEqual(["spend", "impressions", "clicks", "ctr", "roas"]);
    expect(screen.getByRole("link", { name: "Download 2-Campaign Performance" })).toBeDefined();
  });

  it("falls back to cpa + ctr when every KPI is deselected", async () => {
    let reportBody: Record<string, unknown> = {};
    mockFetch((url, init) => {
      if (url === "/api/report" && init?.method === "POST") {
        reportBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ format: "one-pager", markdown: "# Report" });
      }
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("5 KPIs Selected")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: /One-Pager Executive Summary/ }));
    fireEvent.click(screen.getByText("5 KPIs Selected"));
    for (const k of ["Spend", "Impressions", "Clicks", "CTR", "ROAS"]) {
      fireEvent.click(screen.getByRole("checkbox", { name: k }));
    }
    fireEvent.click(screen.getByRole("button", { name: /Generate Report/ }));
    await waitFor(() => {
      expect(reportBody["kpis"]).toEqual(["cpa", "ctr"]);
    });
  });

  it("renders BLOCKED status when generation is refused", async () => {
    mockFetch((url, init) => {
      if (url === "/api/report" && init?.method === "POST") {
        return jsonResponse({ detail: { error: "2 reviews pending" } }, 409);
      }
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2 Campaigns Selected")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate Report/ }));
    await waitFor(() => {
      expect(screen.getByText("BLOCKED: 2 reviews pending")).toBeDefined();
    });
  });

  it("seeds demo history rows that regenerate through the backend", async () => {
    let posts = 0;
    mockFetch((url, init) => {
      if (url === "/api/report" && init?.method === "POST") {
        posts += 1;
        return jsonResponse({ format: "pptx", filename: "regen.pptx", pptx_b64: "eA==" });
      }
      if (url.includes("/api/campaigns/meta")) return jsonResponse(metaDemo);
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Camp A Performance").length).toBeGreaterThan(0);
    });
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("Completed").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Download Camp A Performance" }));
    await waitFor(() => {
      expect(posts).toBe(1);
    });
    await waitFor(() => {
      expect(screen.getByText("PPTX Built: regen.pptx.")).toBeDefined();
    });
  });

  it("filters history by search text", async () => {
    mockCatalog();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Camp A Performance").length).toBeGreaterThan(0);
    });
    fireEvent.change(screen.getByLabelText("Search Reports"), { target: { value: "zzz-no-match" } });
    await waitFor(() => {
      expect(screen.getByText("No Matching Reports")).toBeDefined();
    });
  });

  it("shows no synthetic history outside demo workspaces", async () => {
    mockCatalog({ campaigns: [], demo: false });
    renderPage();
    await waitFor(() => {
      // Real workspace: no fabricated rows even though campaigns exist.
      expect(screen.getByText(/No Reports Yet/)).toBeDefined();
    });
    expect(screen.queryByText("Camp A Performance")).toBeNull();
  });

  it("sends the visible date range in the report body", async () => {
    let reportBody: Record<string, unknown> = {};
    mockFetch((url, init) => {
      if (url === "/api/report" && init?.method === "POST") {
        reportBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ format: "pptx", filename: "r.pptx", pptx_b64: "eA==" });
      }
      if (url.includes("/api/campaigns/meta")) return jsonResponse(metaDemo);
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2 Campaigns Selected")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Date Range/ }));
    fireEvent.change(screen.getByLabelText("Report From Date"), { target: { value: "2024-01-01" } });
    fireEvent.change(screen.getByLabelText("Report To Date"), { target: { value: "2024-01-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    fireEvent.click(screen.getByRole("button", { name: /Generate Report/ }));
    await waitFor(() => {
      const filters = reportBody["filters"] as Record<string, string[]>;
      expect(filters["date_from"]).toEqual(["2024-01-01"]);
      expect(filters["date_to"]).toEqual(["2024-01-31"]);
    });
  });

  it("filters history by time window", async () => {
    mockCatalog();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Camp A Performance").length).toBeGreaterThan(0);
    });
    // Demo rows are stamped Mar 2024: a 7-day window hides them all.
    fireEvent.change(screen.getByLabelText("Filter By Time"), { target: { value: "Last 7 Days" } });
    await waitFor(() => {
      expect(screen.getByText("No Matching Reports")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Filter By Time"), { target: { value: "All Time" } });
    await waitFor(() => {
      expect(screen.getAllByText("Camp A Performance").length).toBeGreaterThan(0);
    });
  });
});
