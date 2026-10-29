import { describe, expect, it } from "vitest";
import { benchmarkChartData, benchmarkMetricValue, type BenchmarkRow } from "./benchmarkMetrics";

function row(overrides: Partial<BenchmarkRow> = {}): BenchmarkRow {
  return { spend: 300, impressions: 1000, clicks: 100, conversions: 10, revenue: 600,
    cpm: 12, cpa: 30, cpc: 3, ctr: 0.1, roas: 2, n_ads: 2,
    currency: "GBP", currencies: ["GBP"], currency_known: true,
    mixed_currency: false, unknown_currency_contribution: false, ...overrides };
}

describe("canonical benchmark values", () => {
  it("preserves null CPM even when raw spend and impressions could form a number", () => {
    expect(benchmarkMetricValue(row({ cpm: null, currency: null, currencies: ["GBP", "EUR"],
      currency_known: false, mixed_currency: true }), "cpm")).toBeNull();
  });
  it("uses supplied CPM rather than reconstructing it from raw totals", () => {
    expect(benchmarkMetricValue(row({ cpm: 2.5 }), "cpm")).toBe(2.5);
  });
  it("keeps old responses without canonical CPM unavailable", () => {
    expect(benchmarkMetricValue(row({ cpm: undefined }), "cpm")).toBeNull();
  });
  it("preserves zero and nullable CPA/ROAS", () => {
    expect(benchmarkMetricValue(row({ cpm: 0 }), "cpm")).toBe(0);
    expect(benchmarkMetricValue(row({ cpa: null }), "cpa")).toBeNull();
    expect(benchmarkMetricValue(row({ roas: null }), "roas")).toBeNull();
  });
  it("preserves the existing CTR percentage conversion", () => {
    expect(benchmarkMetricValue(row({ ctr: 0.123 }), "ctr")).toBeCloseTo(12.3);
    expect(benchmarkMetricValue(row({ ctr: 0 }), "ctr")).toBe(0);
    expect(benchmarkMetricValue(row({ ctr: null }), "ctr")).toBeNull();
  });
  it("rejects nonfinite values without coercing them to zero", () => {
    for (const cpm of [NaN, Infinity, -Infinity]) expect(benchmarkMetricValue(row({ cpm }), "cpm")).toBeNull();
    expect(benchmarkMetricValue(row({ ctr: Number.MAX_VALUE }), "ctr")).toBeNull();
  });
});

describe("benchmark chart populations", () => {
  it("keeps missing slots between measured values without blocking known units", () => {
    const result = benchmarkChartData([row({ cpa: 10 }), row({ cpa: null, currency: null, currencies: [],
      currency_known: false }), row({ cpa: 20 })], "cpa");
    expect(result).toEqual({ values: [10, null, 20], currency: "GBP", currencyUnavailable: false });
  });
  it("withholds a comparison of two known different currencies", () => {
    expect(benchmarkChartData([row(), row({ currency: "EUR", currencies: ["EUR"] })], "cpm"))
      .toEqual({ values: [null, null], currency: null, currencyUnavailable: true });
  });
  it("withholds a known and an unknown monetary amount", () => {
    expect(benchmarkChartData([row(), row({ currency: null, currencies: [], currency_known: false })], "cpa"))
      .toEqual({ values: [null, null], currency: null, currencyUnavailable: true });
  });
  it("rejects mixed or contradictory metadata even if a cost value exists", () => {
    for (const change of [{ mixed_currency: true }, { unknown_currency_contribution: true },
      { currencies: ["EUR"] }, { currency_known: false }]) {
      expect(benchmarkChartData([row(), row(change)], "cpm").currencyUnavailable).toBe(true);
    }
  });
  it("does not block dimensionless metrics across currencies", () => {
    const rows = [row({ ctr: 0.1, roas: 1 }), row({ currency: "EUR", currencies: ["EUR"], ctr: 0.2, roas: 2 })];
    expect(benchmarkChartData(rows, "ctr").values).toEqual([10, 20]);
    expect(benchmarkChartData(rows, "roas").values).toEqual([1, 2]);
  });
  it("distinguishes no reported costs from incompatible reported costs", () => {
    expect(benchmarkChartData([row({ cpa: null }), row({ cpa: null })], "cpa"))
      .toEqual({ values: [null, null], currency: null, currencyUnavailable: false });
    expect(benchmarkChartData([], "cpa").values).toEqual([]);
  });
  it("keeps a measured zero in a matching currency", () => {
    expect(benchmarkChartData([row({ cpm: 0 }), row({ cpm: 12 })], "cpm").values).toEqual([0, 12]);
  });
  it("does not mutate source rows or their currency lists", () => {
    const rows = [row(), row({ currency: "EUR", currencies: ["EUR"] })];
    const before = structuredClone(rows);
    benchmarkChartData(rows, "cpm");
    expect(rows).toEqual(before);
  });
});
