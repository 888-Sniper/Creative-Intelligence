import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { fmtAxis, GroupBars, TrendChart, type TrendSeries } from "./charts";

const language = vi.hoisted(() => ({ locale: "en" }));
vi.mock("@/i18n", () => ({ useLocale: () => ({ locale: language.locale, t: (key: string) => key }) }));
afterEach(() => { cleanup(); language.locale = "en"; });

const quarterTicks = [0, 0.25, 0.5, 0.75, 1];
const sample = (value: number, axis: "left" | "right" = "left"): TrendSeries => ({
  label: axis, color: "#123456", soft: "#abcdef", points: [value], axis,
});
const labels = (container: HTMLElement) => [...container.querySelectorAll("svg text")].map((n) => n.textContent);

describe("fractional chart-axis labels", () => {
  it.each([
    { locale: "en", expected: ["0", "0.25", "0.5", "0.75", "1"] },
    { locale: "es", expected: ["0", "0,25", "0,5", "0,75", "1"] },
    { locale: "pl", expected: ["0", "0,25", "0,5", "0,75", "1"] },
  ])("keeps quarter ticks distinct in $locale", ({ locale, expected }) => {
    const result = quarterTicks.map((n) => fmtAxis(n, locale, 0.25));
    expect(result).toEqual(expected);
    expect(new Set(result).size).toBe(5);
  });

  it.each([
    { locale: "en", expected: ["0.005", "0.0075", "1.25"] },
    { locale: "es", expected: ["0,005", "0,0075", "1,25"] },
    { locale: "pl", expected: ["0,005", "0,0075", "1,25"] },
  ])("retains small cost/ratio values without a supplied interval in $locale", ({ locale, expected }) => {
    expect([0.005, 0.0075, 1.25].map((n) => fmtAxis(n, locale))).toEqual(expected);
  });

  it("does not round a small nonzero value into a zero label", () => {
    expect(fmtAxis(0.00000025)).toBe("0.00000025");
    expect(fmtAxis(-0.00000025)).toBe("-0.00000025");
  });

  it("keeps dense compact ticks distinct using their interval", () => {
    expect([1000, 1001, 1002].map((n) => fmtAxis(n, "en", 1)))
      .toEqual(["1K", "1.001K", "1.002K"]);
  });

  it("preserves the existing compact default when no interval is supplied", () => {
    expect([1000, 1250, 1000000].map((n) => fmtAxis(n))).toEqual(["1K", "1.3K", "1M"]);
  });

  it("uses the supplied interval for localized compact labels", () => {
    expect(fmtAxis(1250, "es", 250)).toBe("1,25\u00a0mil");
    expect(fmtAxis(1250, "pl", 250)).toBe("1,25\u00a0tys.");
  });

  it("keeps fractional information in the invalid-locale fallback", () => {
    expect(fmtAxis(0.25, "invalid_locale", 0.25)).toBe("0.25");
    expect(fmtAxis(1.875, "invalid_locale", 0.625)).toBe("1.875");
    expect(fmtAxis(1250, "invalid_locale", 250)).toBe("1.25K");
  });

  it("keeps zero unsigned and retains negative fractional measurements", () => {
    expect(fmtAxis(-0, "en", 0.25)).toBe("0");
    expect(fmtAxis(-0.25, "pl", 0.25)).toBe("-0,25");
  });

  it("falls back to value precision when the interval is absent or invalid", () => {
    for (const interval of [undefined, 0, -1, NaN, Infinity]) {
      expect(fmtAxis(0.25, "en", interval)).toBe("0.25");
    }
  });

  it("labels a fractional left trend axis at each actual grid level", () => {
    const view = render(<TrendChart series={[sample(1)]} labels={[]} />);
    expect(labels(view.container)).toEqual(["0", "0.25", "0.5", "0.75", "1"]);
  });

  it("uses each trend axis' own interval", () => {
    const view = render(<TrendChart series={[sample(2.5), sample(1, "right")]} labels={[]} />);
    expect(labels(view.container)).toEqual([
      "0", "0.625", "1.25", "1.875", "2.5", "0", "0.25", "0.5", "0.75", "1",
    ]);
  });

  it("keeps the default bar-axis ticks fractional", () => {
    const view = render(<GroupBars groups={[{ label: "A", yours: 1, bench: 0.5 }]} />);
    expect(labels(view.container).slice(0, 5)).toEqual(["0", "0.25", "0.5", "0.75", "1"]);
  });

  it("preserves an explicitly supplied bar formatter", () => {
    const view = render(<GroupBars groups={[{ label: "A", yours: 1, bench: 0.5 }]}
      format={(value) => `${value} units`} />);
    expect(labels(view.container).slice(0, 5)).toEqual(["0 units", "0.25 units", "0.5 units", "0.75 units", "1 units"]);
  });

  it("updates tick punctuation after a locale rerender", () => {
    const view = render(<TrendChart series={[sample(1)]} labels={[]} />);
    expect(labels(view.container)).toContain("0.25");
    language.locale = "pl";
    view.rerender(<TrendChart series={[sample(1)]} labels={[]} />);
    expect(labels(view.container)).toContain("0,25");
    expect(labels(view.container)).not.toContain("0.25");
  });

  it("avoids duplicate compact labels in a denser supported tick set", () => {
    const view = render(<TrendChart series={[sample(2000)]} labels={[]} ticks={41} />);
    const result = labels(view.container);
    expect(result).toHaveLength(41);
    expect(new Set(result).size).toBe(41);
  });
});
