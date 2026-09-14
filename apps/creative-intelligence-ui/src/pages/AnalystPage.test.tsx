import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FilterProvider } from "@/state/FilterContext";
import { AnalystPage, scopeBody } from "@/pages/AnalystPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <FilterProvider>
      <AnalystPage />
    </FilterProvider>,
  );
}

const askPayload = {
  conversation_id: "conv-1",
  answer: {
    text: "Hook rate: A 30%, B 12%.",
    language: "en",
    tables: [
      {
        title: "2s hook rate",
        columns: ["creative", "hook_rate_2s_pct"],
        rows: [
          ["A", 30.0],
          ["B", 12.0],
        ],
      },
    ],
    findings_stored: [
      {
        finding_id: "f-1",
        status: "proposed",
        primary_signal: "Low 2s retention on B",
        diagnosis: "Opening may not establish context.",
        creative_hypothesis: "First frame lacks a clear promise.",
        recommended_iteration: "Test 3 alternative openings.",
        priority: "high",
        confidence_level: "medium",
        element_to_preserve: "Body pacing",
        element_to_change: "First 2 seconds",
        creative_ids: ["B"],
      },
    ],
    follow_ups: ["Show watch time for all creatives"],
    warnings: [],
  },
  scope_snapshot: { campaign: "C1", objective: "reach" },
  dataset_version: "d1",
};

function mockFetch() {
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("/api/analyst/conversations") && (!init || init.method === "GET")) {
      return Response.json({ conversations: [] });
    }
    if (url.startsWith("/api/analyst/conversations")) {
      return Response.json({ id: "conv-1" });
    }
    if (url.startsWith("/api/analyst/ask")) return Response.json(askPayload);
    if (url.includes("/api/analyst/findings/")) return Response.json({ ok: true });
    return Response.json({ error: "not found" }, { status: 404 });
  }) as unknown as typeof fetch;
}

describe("AnalystPage", () => {
  // Advanced controls live in the disclosure; tests follow the UX.
  function openMore() {
    fireEvent.click(screen.getByText("More Filters, Conversations & Exports"));
  }

  it("renders controls and composer", () => {
    mockFetch();
    renderPage();
    expect(screen.getByLabelText("Ask Foap Analyst")).toBeDefined();
    expect(screen.getByText("Objective")).toBeDefined();
    expect(screen.getByText("Language")).toBeDefined();
    openMore();
    expect(screen.getByRole("button", { name: "New Conversation" })).toBeDefined();
  });

  it("sends a question and renders table plus finding actions", async () => {
    mockFetch();
    renderPage();
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "hook rate for each creative, goal was reach" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(screen.getByText("2s hook rate")).toBeDefined();
    });
    expect(screen.getByText("Hook rate: A 30%, B 12%.")).toBeDefined();
    expect(screen.getByText("Low 2s retention on B")).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Save To Next-Flight Plan" }),
    ).toBeDefined();
    expect(screen.getByRole("button", { name: "3 Points" })).toBeDefined();
  });

  it("spins only the clicked action (3 Points never lights up Ask)", async () => {
    // Hang the ask request so the loading state is observable.
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/analyst/ask")) return new Promise<Response>(() => {});
      if (url.startsWith("/api/benchmarks")) return Response.json({});
      if (url.startsWith("/api/campaigns")) return Response.json({});
      if (url.startsWith("/api/creatives")) return Response.json([]);
      if (url.startsWith("/api/campaigns/meta")) return Response.json({ campaigns: [], demo: false });
      if (url.startsWith("/api/analyst/conversations")) return Response.json({ conversations: [] });
      return Response.json({ error: "not found" }, { status: 404 });
    }) as unknown as typeof fetch;
    renderPage();
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "condense this" },
    });
    fireEvent.click(screen.getByRole("button", { name: "3 Points" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Condensing…" })).toBeDefined();
    });
    // Ask stays idle (disabled but not spinning).
    expect(screen.queryByRole("button", { name: "Analysing…" })).toBeNull();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDefined();
  });

  it("renders the partner heading and supporting copy", () => {
    mockFetch();
    renderPage();
    expect(screen.getByRole("heading", { name: "Your Creative Partner" })).toBeDefined();
    expect(
      screen.getByText("Ask questions and get recommendations from your creative data."),
    ).toBeDefined();
  });

  it("exposes report and workbook exports", async () => {
    mockFetch();
    renderPage();
    openMore();
    expect(screen.getByRole("button", { name: "Report" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Report XLSX" })).toBeDefined();
    // The workbook is built server-side on demand, so it downloads
    // through a loading button (with parsed errors) rather than a
    // direct link that would save error pages as .xlsx files.
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      blob: () => Promise.resolve(new Blob(["wb"])),
    });
    const createSpy = vi.fn(() => "blob:mock");
    window.URL.createObjectURL = createSpy;
    window.URL.revokeObjectURL = vi.fn();
    fireEvent.click(screen.getByRole("button", { name: "Blank Workbook" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith("/api/analyst/workbook"),
      );
      expect(call).toBeDefined();
    });
    await waitFor(() => {
      expect(createSpy).toHaveBeenCalled();
    });
    expect(screen.getByRole("button", { name: "Blank Workbook" })).toBeDefined();
  });

  it("sends the filter scope in the ask body", async () => {
    mockFetch();
    renderPage();
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "analyse hooks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const ask = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith("/api/analyst/ask"),
      );
      expect(ask).toBeDefined();
      // No query string: scope travels in the JSON body or the
      // backend analyses the whole dataset.
      expect(String(ask?.[0])).not.toContain("?");
      expect(JSON.parse(String(ask?.[1]?.body))).toHaveProperty("scope");
    });
  });

  it("sends language only when explicitly chosen", async () => {
    mockFetch();
    renderPage();
    fireEvent.change(screen.getByLabelText(/Language/), {
      target: { value: "pl" },
    });
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "analyse hooks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const ask = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith("/api/analyst/ask"),
      );
      expect(ask).toBeDefined();
      const body = JSON.parse(String(ask?.[1]?.body));
      // Backend contract is `language`; `locale` would be ignored.
      expect(body).toHaveProperty("language", "pl");
      expect(body).not.toHaveProperty("locale");
    });
  });

  it("omits language on auto so the backend detects it", async () => {
    mockFetch();
    renderPage();
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "analyse hooks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const ask = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith("/api/analyst/ask"),
      );
      expect(ask).toBeDefined();
      const body = JSON.parse(String(ask?.[1]?.body));
      expect(body).not.toHaveProperty("language");
      expect(body).not.toHaveProperty("locale");
    });
  });

  it("maps scope params to body arrays", () => {
    expect(
      scopeBody(new URLSearchParams("campaign=C&platform=tiktok")),
    ).toEqual({ campaign: ["C"], platform: ["tiktok"] });
    expect(scopeBody(new URLSearchParams())).toEqual({});
  });

  it("accepts a finding via the decision endpoint", async () => {
    mockFetch();
    renderPage();
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "analyse hooks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Save To Next-Flight Plan" }),
      ).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Save To Next-Flight Plan" }));
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/api/analyst/findings/f-1"),
      );
      expect(call).toBeDefined();
      // Backend contract: POST /api/analyst/findings/{id} with
      // {"status"} — no /decision suffix, no "decision" key.
      expect(String(call?.[0])).not.toContain("/decision");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        status: "accepted",
      });
    });
  });

  it("drops a late answer from the previous account after identity change", async () => {
    // A07: Account A asks, the identity flips to B mid-flight, then
    // A's answer resolves. It must never render under B.
    let resolveAsk!: (value: Response) => void;
    const askGate = new Promise<Response>((resolve) => {
      resolveAsk = resolve;
    });
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/analyst/conversations") && (!init || init.method === "GET")) {
        return Response.json({ conversations: [] });
      }
      if (url.startsWith("/api/analyst/ask")) return askGate;
      return Response.json({ error: "not found" }, { status: 404 });
    }) as unknown as typeof fetch;
    const { rerender } = render(
      <FilterProvider>
        <AnalystPage accountKey="emp-A" />
      </FilterProvider>,
    );
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "hook rate for each creative" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
      expect(fetchMock.mock.calls.some((c) => String(c[0]).startsWith("/api/analyst/ask"))).toBe(true);
    });
    rerender(
      <FilterProvider>
        <AnalystPage accountKey="emp-B" />
      </FilterProvider>,
    );
    resolveAsk(Response.json(askPayload));
    // Flush the whole late-response chain: without the accountKey
    // guard the stale answer would render here and fail the test.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(screen.queryByText("Hook rate: A 30%, B 12%.")).toBeNull();
    expect(screen.queryByText("hook rate for each creative")).toBeNull();
  });

  it("renders a plain 0 with No Duration Data when durations are missing", async () => {
    // Item 20: missing duration is a display-only 0 (not 0.0, not a
    // dash) with the "No Duration Data" note kept underneath.
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/analyst/conversations")) return Response.json({ conversations: [] });
      if (url.startsWith("/api/benchmarks")) return Response.json({});
      if (url.startsWith("/api/campaigns")) return Response.json({ campaigns: [] });
      if (url.startsWith("/api/creatives")) {
        return Response.json([
          { creative_key: "a", name: "A", metrics: { clicks: 5, impressions: 100 }, annotation: { duration_s: null }, duration_s: null },
        ]);
      }
      return Response.json({ error: "not found" }, { status: 404 });
    }) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Optimal Video Length")).toBeDefined();
    });
    const card = screen.getByText("Optimal Video Length").closest(".kpi-card") as HTMLElement;
    expect(card.querySelector(".kpi-value")?.textContent).toBe("0");
    expect(card.textContent).toContain("No Duration Data");
  });

  it("keeps the display-only zero out of length calculations", async () => {
    // A duration-less high-volume creative must not dilute the
    // bucketed CTR: only the timed 20s creative counts (10% CTR).
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/analyst/conversations")) return Response.json({ conversations: [] });
      if (url.startsWith("/api/benchmarks")) return Response.json({});
      if (url.startsWith("/api/campaigns")) return Response.json({ campaigns: [] });
      if (url.startsWith("/api/creatives")) {
        return Response.json([
          { creative_key: "a", name: "A", metrics: { clicks: 10, impressions: 100 }, annotation: { duration_s: 20 }, duration_s: 20 },
          { creative_key: "b", name: "B", metrics: { clicks: 10000, impressions: 10000 }, annotation: { duration_s: null }, duration_s: null },
        ]);
      }
      return Response.json({ error: "not found" }, { status: 404 });
    }) as unknown as typeof fetch;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Optimal Video Length")).toBeDefined();
    });
    const card = screen.getByText("Optimal Video Length").closest(".kpi-card") as HTMLElement;
    expect(card.querySelector(".kpi-value")?.textContent).toBe("15-30s");
    expect(card.textContent).toContain("10.0% CTR in band");
  });

  it("explains the empty state and disables 3 Points with no conversation", () => {
    mockFetch();
    renderPage();
    expect(screen.getByText("Ask something first — 3 Points will condense the answer to 3 key points.")).toBeDefined();
    expect((screen.getByRole("button", { name: "3 Points" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("condenses the last answer from a populated conversation with empty input", async () => {
    const condensed = {
      conversation_id: "conv-1",
      answer: { text: "In 3 points (numbers and caveats kept):\n1. A\n2. B\n3. C", language: "en" },
    };
    let resolveAsk!: (value: Response) => void;
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/analyst/conversations") && (!init || init.method === "GET")) {
        return Response.json({ conversations: [] });
      }
      if (url.startsWith("/api/analyst/ask")) {
        if (init?.body && String(init.body).includes("hook rate")) return Response.json(askPayload);
        return new Promise<Response>((resolve) => { resolveAsk = resolve; });
      }
      return Response.json({ error: "not found" }, { status: 404 });
    }) as unknown as typeof fetch;
    renderPage();
    // Populate the conversation first.
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "hook rate for each creative" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(screen.getByText("Hook rate: A 30%, B 12%.")).toBeDefined();
    });
    // Input cleared by send; 3 Points stays enabled on the thread …
    expect((screen.getByRole("button", { name: "3 Points" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText("3 Points condenses the latest answer — numbers and caveats kept.")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "3 Points" }));
    // … sends the condense override with the cap and spins …
    await waitFor(() => {
      const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith("/api/analyst/ask")
        && String(c[1]?.body ?? "").includes("Condense the last answer"),
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ max_points: 3 });
    });
    expect(screen.getByRole("button", { name: "Condensing…" })).toBeDefined();
    // … and visibly renders the condensed answer.
    await act(async () => { resolveAsk(Response.json(condensed)); });
    await waitFor(() => {
      expect(screen.getByText(/In 3 points/)).toBeDefined();
    });
  });

  it("surfaces 3 Points failures instead of hanging", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/analyst/conversations") && (!init || init.method === "GET")) {
        return Response.json({ conversations: [] });
      }
      if (url.startsWith("/api/analyst/ask")) {
        return Response.json({ error: "Analyst overloaded" }, { status: 503 });
      }
      return Response.json({ error: "not found" }, { status: 404 });
    }) as unknown as typeof fetch;
    renderPage();
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "condense this thread" },
    });
    fireEvent.click(screen.getByRole("button", { name: "3 Points" }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
    expect(screen.getByRole("alert").textContent).toContain("Analyst overloaded");
    expect((screen.getByRole("button", { name: "3 Points" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("clears chat state when the account key changes", async () => {
    mockFetch();
    const { rerender } = render(
      <FilterProvider>
        <AnalystPage accountKey="emp-A" />
      </FilterProvider>,
    );
    fireEvent.change(screen.getByLabelText("Ask Foap Analyst"), {
      target: { value: "hook rate for each creative, goal was reach" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(screen.getByText("Hook rate: A 30%, B 12%.")).toBeDefined();
    });
    rerender(
      <FilterProvider>
        <AnalystPage accountKey="emp-B" />
      </FilterProvider>,
    );
    await waitFor(() => {
      expect(screen.queryByText("Hook rate: A 30%, B 12%.")).toBeNull();
    });
  });
});
