import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

  it("presents ONE Date Range field that opens From/To in a popover", () => {
    renderPanel({ showTeam: false });
    expect(screen.getAllByText("Date Range")).toHaveLength(1);
    // Collapsed: no date inputs in the grid until the field opens.
    expect(screen.queryByLabelText("From Date")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /All Time|–/ }));
    const from = screen.getByLabelText("From Date");
    const to = screen.getByLabelText("To Date");
    expect(from.closest(".daterange-pop")).not.toBeNull();
    expect(from.closest(".daterange-pop")).toBe(to.closest(".daterange-pop"));
    fireEvent.change(from, { target: { value: "2026-08-01" } });
    fireEvent.change(to, { target: { value: "2026-08-07" } });
    expect(screen.getByText("Aug 1 – Aug 7, 2026")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByLabelText("From Date")).toBeNull();
  });

  it("keeps the single Date Range field in the creative variant", () => {
    renderPanel({ creative: true });
    expect(screen.getAllByText("Date Range")).toHaveLength(1);
    expect(screen.queryByLabelText("From Date")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /All Time|–/ }));
    const from = screen.getByLabelText("From Date");
    const to = screen.getByLabelText("To Date");
    expect(from.closest(".daterange-pop")).toBe(to.closest(".daterange-pop"));
  });

  it("keeps selector machine values aligned with their options", () => {
    // Regression: the controlled value must always equal one of the
    // option values (the old Meta/meta fold produced a blank select).
    renderPanel();
    const platform = screen.getByLabelText("Platform") as HTMLSelectElement;
    expect([...platform.options].map((o) => o.value)).toEqual(["", "meta", "tiktok"]);
    expect(platform.value).toBe("");
    expect(platform.selectedOptions[0]?.text).toBe("All Platforms");
    const objective = screen.getByLabelText("Campaign Objective") as HTMLSelectElement;
    expect([...objective.options].map((o) => o.value)).toContain("video_views");
    expect(objective.value).toBe("");
    const funnel = screen.getByLabelText("Funnel Stage") as HTMLSelectElement;
    expect([...funnel.options].map((o) => o.value)).toEqual(["", "upper", "mid", "lower"]);
    const kpi = screen.getByLabelText("KPI") as HTMLSelectElement;
    expect([...kpi.options].map((o) => o.value)).toContain("roas");
  });

  it("uses explicit labels in the creative variant too", () => {
    renderPanel({ creative: true });
    const hook = screen.getByLabelText("Hook Type") as HTMLSelectElement;
    expect([...hook.options].map((o) => o.value)).toContain("bold_claim");
    const creator = screen.getByLabelText("Creator vs Branded") as HTMLSelectElement;
    expect([...creator.options].map((o) => o.value)).toEqual(["", "creator", "branded", "hybrid"]);
  });
});
