import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FilterProvider } from "@/state/FilterContext";
import { InsightsPage } from "@/pages/InsightsPage";

function mockFetch() {
  // Stateful saved views: delete removes the row so a re-fetched
  // list proves the deletion sticks (refresh persistence).
  let views = [
    { id: 7, name: "View One", state: { filters: {}, view: "main" } },
  ];
  window.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/views" && method === "GET") return Response.json(views);
    if (url === "/api/views/delete" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { id: number };
      views = views.filter((v) => v.id !== body.id);
      return Response.json({ ok: true, deleted: body.id });
    }
    if (url.startsWith("/api/analyst/conversations")) {
      return Response.json({
        conversations: [{ id: "c1", title: "Conv One", objective: "reach", updated_at: "2026-09-01T00:00:00Z" }],
      });
    }
    if (url.startsWith("/api/analyst/creatives")) return Response.json({ creatives: [] });
    if (url.startsWith("/api/campaigns/meta")) return Response.json({ campaigns: [] });
    return Response.json({});
  }) as unknown as typeof fetch;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/insights"]}>
      <FilterProvider>
        <InsightsPage />
      </FilterProvider>
    </MemoryRouter>,
  );
}

describe("InsightsPage saved views", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows no Saved View badge but keeps title, description and Open Insight", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("View One")).toBeDefined();
    });
    // Item 31: the Saved View badge is gone …
    expect(screen.queryByText("Saved View")).toBeNull();
    // … while conversation badges stay.
    expect(screen.getByText("Conversation")).toBeDefined();
    // The card keeps its item/title/description/Open Insight.
    expect(screen.getByRole("button", { name: /Open Insight/ })).toBeDefined();
  });

  it("deletes a saved view and keeps it deleted", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete insight View One" })).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete insight View One" }));
    await waitFor(() => {
      expect(screen.getByText("Deleted View One.")).toBeDefined();
    });
    const fetchMock = window.fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some((c) =>
      String(c[0]) === "/api/views/delete"
      && JSON.parse(String((c[1] as RequestInit)?.body ?? "{}")).id === 7,
    )).toBe(true);
    await waitFor(() => {
      expect(screen.queryByText("View One")).toBeNull();
    });
    // The conversation card is untouched.
    expect(screen.getAllByText("Conv One").length).toBeGreaterThan(0);
  });
});
