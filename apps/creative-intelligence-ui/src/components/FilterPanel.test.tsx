import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { FilterProvider } from "@/state/FilterContext";
import { FilterPanel } from "@/components/product";

function renderPanel(props?: { showTeam?: boolean; creative?: boolean }) {
  return render(
    <FilterProvider>
      <FilterPanel actions="none" {...props} />
    </FilterProvider>,
  );
}

describe("FilterPanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows Team by default", () => {
    renderPanel();
    expect(screen.getByLabelText("Team")).toBeDefined();
  });

  it("hides Team when showTeam is false (Dashboard only)", () => {
    renderPanel({ showTeam: false });
    expect(screen.queryByLabelText("Team")).toBeNull();
    // The global scope still works: Campaigns keeps its own Team
    // control bound to the same filter key (covered in CampaignsPage).
  });

  it("presents ONE Date Range field with From/To in a single row", () => {
    renderPanel({ showTeam: false });
    expect(screen.getAllByText("Date Range")).toHaveLength(1);
    const from = screen.getByLabelText("From date");
    const to = screen.getByLabelText("To date");
    expect(from.closest(".field")).not.toBeNull();
    expect(from.closest(".field")).toBe(to.closest(".field"));
  });

  it("keeps the single Date Range field in the creative variant", () => {
    renderPanel({ creative: true });
    expect(screen.getAllByText("Date Range")).toHaveLength(1);
    const from = screen.getByLabelText("From date");
    const to = screen.getByLabelText("To date");
    expect(from.closest(".field")).toBe(to.closest(".field"));
  });
});
