import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage } from "@/pages/DashboardPage";
import { FilterProvider } from "@/state/FilterContext";

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({ me: { employee: { first_name: "Ada" } } }),
}));

const comparePayload = {
  current_period: { start: "2026-07-01", end: "2026-07-30" },
  previous_period: { start: "2026-06-01", end: "2026-06-30" },
  comparison: "30d vs prior 30d",
  metrics: {
    impressions: { state: "compared", direction: "up", sentiment: "good", percent_change: 12, current: 5000000, previous: 4464000, abs_change: 536000 },
    clicks: { state: "compared", direction: "up", sentiment: "good", percent_change: 8, current: 120000, previous: 111000, abs_change: 9000 },
    spend: { state: "compared", direction: "up", sentiment: "neutral", percent_change: 5, current: 60000, previous: 57100, abs_change: 2900 },
    roas: { state: "compared", direction: "up", sentiment: "good", percent_change: 6, current: 3.4, previous: 3.2, abs_change: 0.2 },
  },
};

const FIRST = "2026-07-01";
const LAST = "2026-07-30";

function dayPoints() {
  const out = [];
  for (let d = 1; d <= 30; d++) {
    const dd = String(d).padStart(2, "0");
    out.push({
      date: `2026-07-${dd}`, impressions: 1000, clicks: 20,
      spend: 50, conversions: 2, revenue: 170,
    });
  }
  return out;
}

function mockFetch() {
  const mock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url.startsWith("/api/kpis/compare")) return Response.json(comparePayload);
    if (url.startsWith("/api/kpis/daily")) return Response.json({ days: dayPoints() });
    if (url.startsWith("/api/campaigns")) return Response.json({});
    if (url.startsWith("/api/creatives")) return Response.json([]);
    if (url.startsWith("/api/benchmarks")) return Response.json({});
    if (url.startsWith("/api/retention/curve")) return Response.json({ points: [] });
    return Response.json({});
  });
  window.fetch = mock as unknown as typeof fetch;
  return mock;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FilterProvider>
        <DashboardPage />
      </FilterProvider>
    </MemoryRouter>,
  );
}

describe("DashboardPage precision pass", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("hides Team and shows ONE Date Range field", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Total Impressions")).toBeDefined();
    });
    expect(screen.queryByLabelText("Team")).toBeNull();
    expect(screen.getAllByText("Date Range")).toHaveLength(1);
    expect(screen.queryByLabelText("From date")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /All Time|–/ }));
    const from = screen.getByLabelText("From date");
    const to = screen.getByLabelText("To date");
    expect(from.closest(".daterange-pop")).toBe(to.closest(".daterange-pop"));
  });

  it("keeps the trailing-30-day default scope", async () => {
    const fetchMock = mockFetch();
    renderPage();
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) =>
        u.includes("/api/kpis/compare") &&
        u.includes(`date_from=${FIRST}`) &&
        u.includes(`date_to=${LAST}`),
      )).toBe(true);
    });
  });

  it("keeps KPI trend tooltips with no visible vs-previous-period text", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Total Impressions")).toBeDefined();
    });
    // Title Case KPI labels with trend tooltip affordances only.
    expect(screen.getByText("Total Clicks")).toBeDefined();
    expect(screen.getByText("Total Spend")).toBeDefined();
    expect(screen.getByText("Average ROAS")).toBeDefined();
    expect(screen.getAllByRole("button", { name: "Explain Comparison Period" }).length)
      .toBeGreaterThan(0);
    expect(screen.queryByText(/previous period/i)).toBeNull();
    expect(screen.queryByText(/vs\. previous/i)).toBeNull();
    // Approved copy preserved.
    expect(screen.getByText("Your creative performance at a glance.")).toBeDefined();
  });

  it("shows an honest empty state instead of an endless shimmer with no creative data", async () => {
    mockFetch();
    renderPage();
    // Creatives resolve empty: the retention chart must settle on an
    // empty state, never a perpetual skeleton.
    await waitFor(() => {
      expect(screen.getByText("No Retention Data")).toBeDefined();
    });
    expect(screen.getByText("No takeaways in the current scope yet.")).toBeDefined();
  });
});
