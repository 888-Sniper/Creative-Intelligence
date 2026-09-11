import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReportsPage } from "@/pages/ReportsPage";
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
const creativesBody = [{ creative_key: "ck1", name: "Ad 1", campaigns: ["Camp A"] }];

function mockCatalog() {
  mockFetch((url, init) => {
    if (init?.method === "POST") return jsonResponse({});
    if (url.includes("/api/creatives")) return jsonResponse(creativesBody);
    if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
    return jsonResponse({});
  });
}

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.URL.createObjectURL = vi.fn(() => "blob:mock") as unknown as (
      obj: Blob | MediaSource,
    ) => string;
    window.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders campaigns, creatives, and KPI defaults with mocked data", async () => {
    mockCatalog();
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "Camp A" })).toBeDefined();
    });
    expect(screen.getByRole("checkbox", { name: "Camp B" })).toBeDefined();
    expect(screen.getByRole("checkbox", { name: "Ad 1" })).toBeDefined();
    // Legacy defaults: every KPI checked except roas.
    expect(
      (screen.getByRole("checkbox", { name: "CPA" }) as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByRole("checkbox", { name: "ROAS" }) as HTMLInputElement).checked,
    ).toBe(false);
    expect(
      screen.getByRole("button", { name: "Generate Presentation (HTML Deck)" }),
    ).toBeDefined();
  });

  it("shows a loading state while the catalogs resolve", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    renderPage();
    expect(screen.getAllByText("Loading…")).toHaveLength(2);
  });

  it("renders load errors instead of the lists", async () => {
    mockFetch(() => jsonResponse({ error: "catalog down" }, 500));
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("catalog down")).toHaveLength(2);
    });
  });

  it("generates CSV with the selected campaigns and KPIs, plus a download link", async () => {
    let reportBody: Record<string, unknown> = {};
    mockFetch((url, init) => {
      if (url === "/api/report" && init?.method === "POST") {
        reportBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({
          format: "csv",
          csv: "campaign,cpa\nCamp A,1.5\n",
          markdown: "# Campaign Report",
        });
      }
      if (url.includes("/api/creatives")) return jsonResponse(creativesBody);
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "Camp A" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate CSV" }));
    await waitFor(() => {
      expect(screen.getByText(/campaign,cpa/)).toBeDefined();
    });
    expect(reportBody["format"]).toBe("csv");
    expect(reportBody["campaigns"]).toEqual(["Camp A", "Camp B"]);
    expect(reportBody["kpis"]).toContain("cpa");
    expect(screen.getByRole("link", { name: "Download report.csv" })).toBeDefined();
  });

  it("renders BLOCKED status when the gated export is refused", async () => {
    mockFetch((url, init) => {
      if (url === "/api/export" && init?.method === "POST") {
        return jsonResponse({ detail: { error: "2 reviews pending" } }, 409);
      }
      if (url.includes("/api/creatives")) return jsonResponse(creativesBody);
      if (url.includes("/api/campaigns")) return jsonResponse(campaignsBody);
      return jsonResponse({});
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "Ad 1" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Ad 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Export One-Pager" }));
    await waitFor(() => {
      expect(screen.getByText("BLOCKED: 2 reviews pending")).toBeDefined();
    });
  });
});
