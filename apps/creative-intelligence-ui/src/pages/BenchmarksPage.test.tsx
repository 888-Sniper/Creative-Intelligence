import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useEffect } from "react";
import { BenchmarksPage } from "@/pages/BenchmarksPage";
import { FilterProvider, useFilters } from "@/state/FilterContext";

interface Call {
  url: string;
  method: string;
  body?: unknown;
}

function mockFetch(handler: (url: string, init: RequestInit | undefined, calls: Call[]) => unknown) {
  const calls: Call[] = [];
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ url, method: init?.method ?? "GET", body });
    return Response.json(handler(url, init, calls));
  }) as unknown as typeof fetch;
  return calls;
}

const benchData = {
  question: { n_ads: 6, spend: 120, ctr: 0.02, cpc: 1.1, cpa: 12.5 },
  demo_open: { n_ads: 5, spend: 80, ctr: null, cpc: null, cpa: null },
};

const patternsData = {
  scope: "All data",
  n_creatives: 2,
  n_events: 1,
  patterns: [
    {
      slot: "hook",
      product_demo: true,
      brand_visible: false,
      cta_present: false,
      voiceover: true,
      n_creatives: 2,
      avg_drop_pts: 7.5,
      max_drop_pts: 9.1,
      examples: ["ck1", "ck2"],
    },
  ],
};

const cohortsData = [{ id: 3, name: "Beauty", filters: { platform: ["tiktok"] }, created_at: "" }];

const viewsData = [
  {
    id: 7,
    name: "Spain view",
    state: { filters: { client: ["acme"] }, kpi: "roas", view: "benchmark", benchmark: "platform" },
    updated_at: "",
  },
];

function baseHandler(url: string) {
  if (url.startsWith("/api/benchmarks")) return benchData;
  if (url.startsWith("/api/retention/patterns")) return patternsData;
  if (url === "/api/cohorts") return cohortsData;
  if (url.startsWith("/api/cohorts/build")) {
    return {
      metric: "cpa",
      n_ads: 5,
      project_list: ["p1", "p2", "p3"],
      stats: { n: 5, mean_weighted: 11.2, median: 10.5, p25: 9.0, p75: 13.1 },
      status: "ok",
      cohort: { id: 3, name: "Beauty", filters: {} },
    };
  }
  if (url === "/api/views") return viewsData;
  throw new Error(`unexpected ${url}`);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FilterProvider>
        <BenchmarksPage />
      </FilterProvider>
    </MemoryRouter>,
  );
}

describe("BenchmarksPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders benchmarks, patterns, cohorts and views with mocked data", async () => {
    mockFetch(baseHandler);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("question")).toBeDefined();
    });
    expect(screen.getByText("demo_open")).toBeDefined();
    // Null KPIs render as an em dash, never zero.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText(/Lose ~/)).toBeDefined();
    });
    expect(screen.getByText(/during hook/)).toBeDefined();
    expect(screen.getByText(/Beauty/)).toBeDefined();
    expect(screen.getByText("Spain view")).toBeDefined();
  });

  it("shows loading states while fetching", () => {
    window.fetch = vi.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch;
    renderPage();
    expect(screen.getByText("Loading Benchmarks…")).toBeDefined();
    expect(screen.getByText("Loading Retention Patterns…")).toBeDefined();
    expect(screen.getByText("Loading Saved Cohorts…")).toBeDefined();
    expect(screen.getByText("Loading Saved Views…")).toBeDefined();
  });

  it("renders backend errors", async () => {
    window.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: "boom" }), { status: 409 }),
    ) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("boom").length).toBeGreaterThan(0);
    });
  });

  it("creates a cohort copying every active filter plus include/exclude lists", async () => {
    function Seed() {
      const { setFilter } = useFilters();
      useEffect(() => {
        setFilter("platform", "tiktok");
        setFilter("client", "acme");
      }, [setFilter]);
      return null;
    }
    const calls = mockFetch((url, _init, all) => {
      if (url === "/api/cohorts" && all.some((c) => c.url === url && c.method === "POST")) return cohortsData;
      if (url === "/api/cohorts") return cohortsData;
      return baseHandler(url);
    });
    // Intercept the POST to return the saved cohort.
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method: init?.method ?? "GET", body });
      if (url === "/api/cohorts" && (init?.method ?? "GET") === "POST") {
        return Response.json({ id: 9, name: body.name, filters: body.filters });
      }
      return Response.json(baseHandler(url));
    }) as unknown as typeof fetch;
    render(
      <MemoryRouter>
        <FilterProvider>
          <Seed />
          <BenchmarksPage />
        </FilterProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("question")).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText("Cohort Name"), { target: { value: "Lower" } });
    fireEvent.change(screen.getByLabelText("Include Projects"), { target: { value: "P1, P2" } });
    fireEvent.change(screen.getByLabelText("Exclude Projects"), { target: { value: "PX" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      const post = calls.find((c) => c.url === "/api/cohorts" && c.method === "POST");
      expect(post).toBeDefined();
    });
    const post = calls.find((c) => c.url === "/api/cohorts" && c.method === "POST");
    const body = post?.body as { name: string; filters: Record<string, string[]> };
    expect(body.name).toBe("Lower");
    expect(body.filters["platform"]).toEqual(["tiktok"]);
    expect(body.filters["client"]).toEqual(["acme"]);
    expect(body.filters["include_projects"]).toEqual(["P1", "P2"]);
    expect(body.filters["exclude_projects"]).toEqual(["PX"]);
    // Auto-build of the new cohort renders bands and status.
    await waitFor(() => {
      expect(screen.getByText(/Cohort:/)).toBeDefined();
    });
    expect(screen.getByText(/— ok/)).toBeDefined();
  });

  it("applies a saved view restoring filters and KPI", async () => {
    function Probe() {
      const { filters } = useFilters();
      return (
        <p>
          probe:{filters.client}:{filters.kpi}
        </p>
      );
    }
    mockFetch(baseHandler);
    render(
      <MemoryRouter>
        <FilterProvider>
          <Probe />
          <BenchmarksPage />
        </FilterProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Spain view")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(screen.getByText("probe:acme:roas")).toBeDefined();
    });
  });

  it("warns when saving a view without a name and deletes views", async () => {
    const calls = mockFetch(baseHandler);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Spain view")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Current View" }));
    expect(screen.getByText("Name The View First.")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      const del = calls.find((c) => c.url === "/api/views/delete" && c.method === "POST");
      expect(del).toBeDefined();
    });
  });
});
