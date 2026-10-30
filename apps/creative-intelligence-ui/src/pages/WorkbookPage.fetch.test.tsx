import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { FilterProvider } from "@/state/FilterContext";
import { WorkbookPage } from "@/pages/WorkbookPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("WorkbookPage preview failure", () => {
  it("shows the same retryable preview failure in fullscreen", async () => {
    window.fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.startsWith("/api/kpis/compare")) {
        return Response.json({ error: "preview down" }, { status: 503 });
      }
      if (url.startsWith("/api/creatives")) return Response.json([]);
      return Response.json({});
    }) as unknown as typeof fetch;
    render(
      <MemoryRouter>
        <FilterProvider>
          <WorkbookPage />
        </FilterProvider>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Preview Failed To Load")).toBeDefined();
    });
    fireEvent.click(screen.getByRole("button", { name: "Full screen" }));
    expect(screen.getAllByText("Preview Failed To Load").length).toBe(2);
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(1);
  });
});
