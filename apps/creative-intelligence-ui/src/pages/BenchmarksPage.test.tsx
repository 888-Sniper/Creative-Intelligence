import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FilterProvider } from "@/state/FilterContext";
import { BenchmarksPage } from "@/pages/BenchmarksPage";

const platformBenchmarks = {
  meta: { spend: 300, impressions: 20000, clicks: 1000, conversions: 30, revenue: 900, ctr: 0.05, cpc: 0.3, cpa: 10, roas: 3, n_ads: 700 },
  tiktok: { spend: 200, impressions: 10000, clicks: 600, conversions: 20, revenue: 800, ctr: 0.06, cpc: 0.33, cpa: 10, roas: 4, n_ads: 600 },
};

function mockFetch() {
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/views" && method === "GET") {
      return Response.json([
        { id: 1, name: "Saved Benchmark", state: { filters: {}, view: "benchmark" } },
      ]);
    }
    if (url === "/api/views" && method === "POST") return Response.json({ id: 2 });
    if (url.startsWith("/api/exports/benchmarks")) {
      return new Response("a,b\n1,2\n", { status: 200, headers: { "Content-Type": "text/csv" } });
    }
    if (url.startsWith("/api/benchmarks")) return Response.json(platformBenchmarks);
    return Response.json({});
  }) as unknown as typeof fetch;
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

  it("renders grouped benchmark rows with mocked data", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Benchmark Results")).toBeDefined();
    });
    expect(screen.getAllByText("Meta").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TikTok").length).toBeGreaterThan(0);
    expect(screen.getByText("Saved Benchmarks")).toBeDefined();
    expect(screen.getByText("Saved Benchmark")).toBeDefined();
    expect(screen.getByText("Benchmark Insights")).toBeDefined();
    expect(screen.getByRole("button", { name: "Create Benchmark" })).toBeDefined();
  });

  it("compares two selected benchmarks in mini charts", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText("Select Meta")).toBeDefined();
    });
    fireEvent.click(screen.getByLabelText("Select Meta"));
    fireEvent.click(screen.getByLabelText("Select TikTok"));
    await waitFor(() => {
      expect(screen.getByText("Compare Benchmarks")).toBeDefined();
    });
    // Four metric mini-charts (CPM/CTR/CPA/ROAS) render comparison values.
    expect(screen.getAllByText("6.0%").length).toBeGreaterThan(0);
  });

  it("saves the current setup as a benchmark view", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Create Benchmark" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Benchmark" }));
    await waitFor(() => {
      expect(screen.getByText(/Saved Benchmark —/)).toBeDefined();
    });
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some((c) => String(c[0]) === "/api/views" && (c[1] as RequestInit)?.method === "POST")).toBe(true);
  });

  it("exports benchmarks to CSV", async () => {
    mockFetch();
    const createObjectURL = vi.fn(() => "blob:mock");
    const revokeObjectURL = vi.fn();
    window.URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
    window.URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL;
    const click = vi.spyOn(window.HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Export" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => {
      expect(screen.getByText(/Exported 2 benchmark groups/)).toBeDefined();
    });
    expect(createObjectURL).toHaveBeenCalled();
    click.mockRestore();
  });

  it("exports from the mobile overflow menu through the same handler", async () => {
    mockFetch();
    const createObjectURL = vi.fn(() => "blob:mock");
    window.URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
    window.URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(window.HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Benchmark Results actions" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Benchmark Results actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Export" }));
    await waitFor(() => {
      expect(screen.getByText(/Exported 2 benchmark groups/)).toBeDefined();
    });
    expect(createObjectURL).toHaveBeenCalled();
    click.mockRestore();
  });

  it("renders list errors", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/views") return Response.json([]);
      return Response.json({ error: "db is locked" }, { status: 409 });
    }) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("db is locked")).toBeDefined();
    });
  });

  it("keeps Group By with the results and links out to learn more", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Benchmark Results")).toBeDefined();
    });
    expect(screen.getByRole("combobox", { name: "Group By" })).toBeDefined();
    expect(screen.getByText("Learn More")).toBeDefined();
    expect(screen.getByRole("link", { name: "Open Analyst →" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Open Reports →" })).toBeDefined();
  });

  it("shows skeletons while loading", () => {
    window.fetch = vi.fn(
      () => new Promise<Response>(() => {}),
    ) as unknown as typeof fetch;
    const { container } = renderPage();
    expect(container.querySelector(".skel")).not.toBeNull();
  });
});
