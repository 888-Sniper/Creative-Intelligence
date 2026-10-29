import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { KpiTrend, type KpiComparison } from "./KpiTrend";

vi.mock("@/i18n", () => ({ useLocale: () => ({
  lang: "en", locale: "en",
  t: (key: string, values?: Record<string, unknown>) => values ? `${key} ${JSON.stringify(values)}` : key,
}) }));
afterEach(cleanup);

// These state projections are also reconciled against the pure Python producer
// by the bounded remediation contract check. Translation content is stubbed.
const comparisonCases: Record<string, KpiComparison> = {
  "undefined_prior": { "percent_change": null, "direction": "flat", "sentiment": "neutral", "state": "none" },
  "zero_prior": { "percent_change": null, "direction": "up", "sentiment": "neutral", "state": "new" },
  "measured_increase": { "percent_change": 50, "direction": "up", "sentiment": "good", "state": "compared" },
};
const previous = { start: "2026-01-01", end: "2026-01-07" };

describe("KPI comparison availability", () => {
  it("shows no zero-baseline claim when the prior measurement is unavailable", () => {
    const view = render(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.undefined_prior} previous={previous} />);
    expect(view.container.innerHTML).toBe("");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("retains the zero-baseline explanation for a measured zero", () => {
    render(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.zero_prior} previous={previous} />);
    expect(screen.getByText("trend.isNew")).toBeTruthy();
    fireEvent.focus(screen.getByRole("button"));
    expect(screen.getByRole("tooltip").textContent).toContain("trend.zeroPrevWithRange");
    expect(screen.getByRole("tooltip").textContent).not.toMatch(/Infinity|NaN/);
  });

  it("preserves percentages and the delta explanation for measured values", () => {
    render(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.measured_increase} previous={previous} />);
    expect(screen.getByText("+50%")).toBeTruthy();
    fireEvent.focus(screen.getByRole("button"));
    expect(screen.getByRole("tooltip").textContent).toContain("trend.deltaWithRange");
    expect(screen.getByRole("tooltip").textContent).not.toContain("trend.zeroPrev");
  });

  it("removes an open zero explanation when the next comparison is unavailable", () => {
    const view = render(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.zero_prior} previous={previous} />);
    fireEvent.focus(screen.getByRole("button"));
    expect(screen.getByRole("tooltip")).toBeTruthy();
    view.rerender(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.undefined_prior} previous={previous} />);
    expect(view.container.innerHTML).toBe("");
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("renders a later valid comparison after an unavailable one", () => {
    const view = render(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.undefined_prior} previous={previous} />);
    view.rerender(<KpiTrend metricLabel="ROAS" comparison={comparisonCases.measured_increase} previous={previous} />);
    expect(screen.getByText("+50%")).toBeTruthy();
    const button = screen.getByRole("button");
    fireEvent.focus(button);
    expect(screen.getByRole("tooltip").textContent).toContain("trend.deltaWithRange");
    fireEvent.blur(button);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("keeps null or nonfinite percentage payloads out of the DOM", () => {
    for (const percent_change of [null, NaN, Infinity, -Infinity]) {
      const view = render(<KpiTrend metricLabel="ROAS" previous={previous}
        comparison={{ ...comparisonCases.measured_increase, percent_change }} />);
      expect(view.container.innerHTML).toBe("");
      view.unmount();
    }
  });
});
