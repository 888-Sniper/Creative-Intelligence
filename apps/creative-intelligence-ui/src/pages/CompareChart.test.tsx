import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { GroupedBars } from "./ComparePage";

const SERIES = [
  { label: "Alpha Campaign", color: "#2F6FBE", values: { ctr: 0.022, cpa: 11.4, roas: 3.6 } },
  { label: "Beta Campaign", color: "#0E9F6E", values: { ctr: 0.015, cpa: 9.1, roas: 4.2 } },
];

describe("GroupedBars single-metric scale", () => {
  it("draws one bar per campaign, all inside the plot area", () => {
    // Regression: the old renderer drew all five KPIs against the
    // selected metric's scale, so CPA/ROAS bars escaped the plot
    // (negative y) while CTR shrank to noise.
    const { container } = render(<GroupedBars series={SERIES} metric="ctr" />);
    const rects = container.querySelectorAll("rect");
    expect(rects).toHaveLength(2);
    rects.forEach((r) => {
      const y = Number(r.getAttribute("y"));
      const bottom = y + Number(r.getAttribute("height"));
      expect(y).toBeGreaterThanOrEqual(10);
      expect(bottom).toBeLessThanOrEqual(200 - 34 + 1);
    });
  });

  it("labels ticks and bars in the selected metric's unit", () => {
    const { container } = render(<GroupedBars series={SERIES} metric="cpa" />);
    expect(container.textContent).toContain("$");
    expect(container.textContent).not.toContain("%");
    const roas = render(<GroupedBars series={SERIES} metric="roas" />);
    expect(roas.container.textContent).toContain("x");
  });

  it("marks missing values without breaking the scale", () => {
    const { container } = render(
      <GroupedBars
        series={[{ label: "Gamma", color: "#7C6BD6", values: { ctr: null } }]}
        metric="ctr"
      />,
    );
    expect(container.querySelectorAll("rect")).toHaveLength(0);
    expect(container.textContent).toContain("—");
  });
});
