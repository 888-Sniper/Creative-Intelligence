import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FilterProvider } from "@/state/FilterContext";
import { AnalystPage } from "@/pages/AnalystPage";

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
  it("renders controls and composer", () => {
    mockFetch();
    renderPage();
    expect(screen.getByLabelText("Ask Foap Analyst")).toBeDefined();
    expect(screen.getByText("Objective")).toBeDefined();
    expect(screen.getByText("Language")).toBeDefined();
    expect(screen.getByRole("button", { name: "New conversation" })).toBeDefined();
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
      screen.getByRole("button", { name: "Save to next-flight plan" }),
    ).toBeDefined();
    expect(screen.getByRole("button", { name: "3 points" })).toBeDefined();
  });

  it("exposes report and workbook exports", () => {
    mockFetch();
    renderPage();
    expect(screen.getByRole("button", { name: "Report" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Report XLSX" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Blank workbook" })).toHaveProperty(
      "href",
      expect.stringContaining("/api/analyst/workbook"),
    );
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
        screen.getByRole("button", { name: "Save to next-flight plan" }),
      ).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Save to next-flight plan" }));
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() => {
      const called = fetchMock.mock.calls.some((c) =>
        String(c[0]).includes("/api/analyst/findings/f-1/decision"),
      );
      expect(called).toBe(true);
    });
  });
});
