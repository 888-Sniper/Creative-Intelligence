import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { GlobalSearch } from "@/components/GlobalSearch";

function mockFetch() {
  window.fetch = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    if (url === "/api/campaigns/meta") {
      return Response.json({ campaigns: [{ name: "Summer Glow", client: "Glow Co" }] });
    }
    if (url === "/api/creatives") {
      return Response.json([{ creative_key: "ck1", name: "Hook Test", campaigns: ["Summer Glow"] }]);
    }
    if (url.startsWith("/api/analyst/creatives")) {
      return Response.json({
        creatives: [{
          creative_key: "ck1", name: "Hook Test", campaign: "Summer Glow",
          finding: { primary_signal: "Strong hook retains viewers" },
        }],
      });
    }
    return Response.json({});
  }) as unknown as typeof fetch;
}

function renderSearch() {
  return render(
    <MemoryRouter>
      <GlobalSearch />
    </MemoryRouter>,
  );
}

describe("GlobalSearch", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows grouped live results across campaigns, creatives, and insights", async () => {
    mockFetch();
    renderSearch();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "glow" } });
    await waitFor(() => {
      expect(screen.getByText("Campaigns")).toBeDefined();
    });
    expect(screen.getAllByText("Summer Glow").length).toBeGreaterThan(0);
    expect(screen.getByRole("option", { name: /Summer Glow.*Glow Co/ })).toBeDefined();
    expect(screen.getByText("Creatives")).toBeDefined();
    expect(screen.getByText("Insights")).toBeDefined();
    expect(screen.getByText(/See all campaign results/)).toBeDefined();
  });

  it("reports honestly when nothing matches", async () => {
    mockFetch();
    renderSearch();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "zzz-no-match" } });
    await waitFor(() => {
      expect(screen.getByText(/No matches for/)).toBeDefined();
    });
  });

  it("closes on Escape and navigates on suggestion click", async () => {
    mockFetch();
    renderSearch();
    const box = screen.getByRole("combobox");
    fireEvent.change(box, { target: { value: "glow" } });
    await waitFor(() => {
      expect(screen.getAllByText("Summer Glow").length).toBeGreaterThan(0);
    });
    fireEvent.keyDown(box, { key: "Escape" });
    expect(screen.queryByText("Summer Glow")).toBeNull();
    fireEvent.focus(box);
    await waitFor(() => {
      expect(screen.getAllByText("Summer Glow").length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getByRole("option", { name: /Summer Glow.*Glow Co/ }));
    await waitFor(() => {
      expect(screen.queryByText("Summer Glow")).toBeNull();
    });
    expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("");
  });
});
