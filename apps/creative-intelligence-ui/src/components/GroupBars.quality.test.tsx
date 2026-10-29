import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { GroupBars } from "./charts";
import { topPerformanceValue } from "./performanceRanking";

vi.mock("@/i18n", () => ({ useLocale: () => ({ locale: "en", t: (key: string) => key }) }));
afterEach(cleanup);

describe("benchmark bars with unavailable measurements", () => {
  it("does not fabricate bars when every metric and reference is unavailable", () => {
    const values = [null, null];
    const bench = topPerformanceValue(values, "cpa");
    render(<GroupBars groups={values.map((yours, index) => ({ label: `Platform ${index}`, yours, bench }))} />);
    const svg = screen.getByRole("img");
    expect(svg.querySelectorAll("rect")).toHaveLength(0);
    expect(svg.textContent?.match(/—/g)).toHaveLength(4);
    expect(svg.outerHTML).not.toMatch(/NaN|Infinity/);
  });

  it("retains a measured zero while leaving a missing benchmark absent", () => {
    const view = render(<GroupBars groups={[{ label: "Platform", yours: 0, bench: null }]} />);
    expect(screen.getByRole("img").querySelectorAll("rect")).toHaveLength(1);
    expect(screen.getByRole("img").textContent?.match(/—/g)).toHaveLength(1);
    view.rerender(<GroupBars groups={[{ label: "Platform", yours: 0, bench: 0 }]} />);
    expect(screen.getByRole("img").querySelectorAll("rect")).toHaveLength(2);
    expect(screen.getByRole("img").textContent).not.toContain("—");
  });

  it("keeps valid bar geometry when another measurement is non-finite", () => {
    render(<GroupBars groups={[{ label: "A", yours: NaN, bench: 2 }, { label: "B", yours: 5, bench: Infinity }]} />);
    const svg = screen.getByRole("img");
    expect(svg.querySelectorAll("rect")).toHaveLength(2);
    expect(svg.outerHTML).not.toMatch(/NaN|Infinity/);
    for (const rect of svg.querySelectorAll("rect")) {
      for (const key of ["x", "y", "width", "height"]) expect(Number.isFinite(Number(rect.getAttribute(key)))).toBe(true);
    }
  });
});
