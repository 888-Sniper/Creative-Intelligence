import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LocaleProvider } from "@/i18n";
import { AskPage } from "@/pages/AskPage";
import { FilterProvider, useFilters } from "@/state/FilterContext";

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({ me: { employee: { id: "ada", first_name: "Ada" } } }),
  useOptionalAuth: () => ({ me: { employee: { id: "ada", first_name: "Ada" } } }),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function SetCampaign() {
  const { setFilter } = useFilters();
  return <button type="button" onClick={() => setFilter("campaign", "Brand B")}>Set Campaign</button>;
}

function compareBody(url: string) {
  const campaign = new URL(url, "http://local").searchParams.get("campaign");
  const spend = campaign === "Brand B" ? 222 : 111;
  const known = {
    currency: "USD",
    currencies: ["USD"],
    currency_known: true,
    mixed_currency: false,
    unknown_currency_contribution: false,
  };
  return {
    current_period: null,
    previous_period: null,
    comparison: null,
    current_n_ads: 3,
    currency_context: { current: known, previous: known, same_known_currency: true },
    metrics: {
      spend: { current: spend },
      conversions: { current: 1 },
      cpa: { current: 2 },
      roas: { current: 3 },
    },
  };
}

function installFetch(ask: (url: string, init: RequestInit | undefined, n: number) => Promise<Response>) {
  let asks = 0;
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("/api/ask")) {
      asks += 1;
      return ask(url, init, asks);
    }
    if (url.startsWith("/api/kpis/compare")) return Response.json(compareBody(url));
    if (url.startsWith("/api/kpis/daily")) return Response.json({ days: [] });
    if (url.startsWith("/api/benchmarks")) return Response.json({});
    if (url.startsWith("/api/analyst/conversations")) return Response.json({ conversations: [] });
    if (url.startsWith("/api/campaigns/meta")) return Response.json({ demo: false });
    return Response.json({});
  }) as unknown as typeof fetch;
  return () => asks;
}

function showsSpend(amount: string) {
  const pattern = new RegExp(`USD[\\s\\u00a0]*${amount}`);
  return (_content: string, node: Element | null) =>
    node?.classList.contains("kpi-value") === true && pattern.test(node.textContent ?? "");
}

function renderAsk() {
  return render(
    <MemoryRouter>
      <LocaleProvider>
        <FilterProvider>
          <SetCampaign />
          <AskPage />
        </FilterProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

describe("AskPage answer scope", () => {
  it("shows a retryable platform failure in the context panel after an answer", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/ask")) return Response.json({ answer: "ANSWER-A", sources: [], scope: "all" });
      if (url.startsWith("/api/kpis/compare")) return Response.json(compareBody(url));
      if (url.startsWith("/api/kpis/daily")) return Response.json({ error: "daily down" }, { status: 503 });
      if (url.startsWith("/api/benchmarks") && url.includes("group_by=platform")) {
        return Response.json({ error: "platforms down" }, { status: 503 });
      }
      if (url.startsWith("/api/benchmarks")) return Response.json({});
      if (url.startsWith("/api/analyst/conversations")) return Response.json({ conversations: [] });
      if (url.startsWith("/api/campaigns/meta")) return Response.json({ demo: false });
      return Response.json({});
    }) as unknown as typeof fetch;
    renderAsk();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(screen.getByText("ANSWER-A")).toBeDefined();
    });
    expect(screen.getByText("daily down")).toBeDefined();
    expect(screen.getByText("platforms down")).toBeDefined();
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(0);
  });

  it("shows a same-scope answer and clears the busy state", async () => {
    installFetch(async () => Response.json({ answer: "ANSWER-A", sources: ["ads"], scope: "All data" }));
    renderAsk();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("ANSWER-A")).toBeDefined();
    expect(screen.getByText(showsSpend("111"))).toBeDefined();
    expect(screen.queryByText("Ask Failed.")).toBeNull();
  });

  it("shows an ask failure without leaving the composer busy", async () => {
    installFetch(async () => {
      throw new Error("network down");
    });
    renderAsk();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Ask Failed.")).toBeDefined();
    expect(screen.queryByText("ANSWER-A")).toBeNull();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDefined();
  });

  it("does not pair a finished answer with KPIs from a later campaign filter", async () => {
    installFetch(async () => Response.json({ answer: "ANSWER-A", sources: [], scope: "All data" }));
    renderAsk();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("ANSWER-A")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Set Campaign" }));
    await waitFor(() => {
      expect(screen.queryByText("ANSWER-A")).toBeNull();
    });
    expect(screen.queryByText(showsSpend("222"))).toBeNull();
    expect(screen.getByText("Ask a Question to Begin")).toBeDefined();
  });

  it("ignores a late answer after the filter changes and accepts the newer request", async () => {
    let resolveFirst: (value: Response) => void = () => {};
    let resolveSecond: (value: Response) => void = () => {};
    const asks = installFetch((_url, _init, n) => new Promise((resolve) => {
      if (n === 1) resolveFirst = resolve;
      else resolveSecond = resolve;
    }));
    renderAsk();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(asks()).toBe(1));
    fireEvent.click(screen.getByRole("button", { name: "Set Campaign" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(asks()).toBe(2));
    resolveFirst(Response.json({ answer: "ANSWER-A", sources: [], scope: "All data" }));
    await waitFor(() => {
      expect(screen.queryByText("ANSWER-A")).toBeNull();
    });
    expect(screen.queryByText(showsSpend("222"))).toBeNull();
    resolveSecond(Response.json({ answer: "ANSWER-B", sources: [], scope: "Brand B" }));
    expect(await screen.findByText("ANSWER-B")).toBeDefined();
    expect(screen.queryByText("ANSWER-A")).toBeNull();
    expect(screen.getByText(showsSpend("222"))).toBeDefined();
  });
});
