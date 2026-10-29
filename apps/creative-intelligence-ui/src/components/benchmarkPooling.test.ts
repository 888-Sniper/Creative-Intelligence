import { describe, expect, it } from "vitest";
import {
  hasComparableBenchmarkCurrency, pooledBenchmark, pooledBenchmarkValue,
  type BenchmarkMetadata, type MetricComponent, type PooledBenchmarkMetric,
} from "./benchmarkPooling";

function group(
  metric: PooledBenchmarkMetric, numerator: number, denominator: number,
  overrides: Partial<BenchmarkMetadata> = {}, component: Partial<MetricComponent> = {},
): BenchmarkMetadata {
  return {
    n_ads: 1, currency: "USD", currencies: ["USD"], currency_known: true,
    mixed_currency: false, unknown_currency_contribution: false,
    metric_components: {
      [metric]: { numerator, denominator, reporting_rows: 1, total_rows: 1, ...component },
    },
    ...overrides,
  };
}

describe("reporting-population benchmark pooling", () => {
  it("excludes all unreported spend from the ROAS denominator", () => {
    const reported = group("roas", 200, 100, {}, { total_spend: 100 });
    const unreported = group("roas", 0, 0, {}, { reporting_rows: 0, total_spend: 900 });
    expect(pooledBenchmarkValue([reported, unreported], "roas")).toBe(2);
  });

  it("pools partially reporting groups using reported spend, not total group spend", () => {
    const a = group("roas", 200, 100, { n_ads: 2 }, { total_rows: 2, total_spend: 1000 });
    const b = group("roas", 400, 100, {}, { total_spend: 100 });
    expect(pooledBenchmarkValue([a, b], "roas")).toBe(3);
  });

  it("does not reconstruct revenue from rounded ROAS or total spend", () => {
    const a = { ...group("roas", 1, 3), spend: 9999, roas: 0.3333 };
    const b = { ...group("roas", 2, 7), spend: 5000, roas: 0.2857 };
    expect(pooledBenchmarkValue([a, b], "roas")).toBe(0.3);
  });

  it("keeps all-unreported revenue unavailable", () => {
    expect(pooledBenchmarkValue([group("roas", 0, 0, {}, { reporting_rows: 0 })], "roas")).toBeNull();
  });

  it("preserves explicitly reported zero revenue", () => {
    expect(pooledBenchmarkValue([group("roas", 0, 100)], "roas")).toBe(0);
  });

  it("keeps zero or negative reporting spend unavailable for ROAS", () => {
    expect(pooledBenchmarkValue([group("roas", 100, 0)], "roas")).toBeNull();
    expect(pooledBenchmarkValue([group("roas", 100, -10)], "roas")).toBeNull();
  });

  it("uses only matched clicks and impressions for CTR", () => {
    const a = group("ctr", 10, 100);
    const b = { ...group("ctr", 0, 0, {}, { reporting_rows: 0 }), impressions: 900 };
    expect(pooledBenchmarkValue([a, b], "ctr")).toBe(0.1);
  });

  it("excludes unreported spend rather than publishing zero CPA", () => {
    const absent = group("cpa", 0, 0, {}, { reporting_rows: 0 });
    expect(pooledBenchmarkValue([absent], "cpa")).toBeNull();
    expect(pooledBenchmarkValue([group("cpa", 100, 10), absent], "cpa")).toBe(10);
  });

  it("uses summed numerators and denominators instead of averaging ratios", () => {
    expect(pooledBenchmarkValue([group("cpc", 10, 10), group("cpc", 90, 30)], "cpc")).toBe(2.5);
  });

  it("keeps CTR fractional and applies CPM's thousand-impression scale", () => {
    expect(pooledBenchmarkValue([group("ctr", 2, 500)], "ctr")).toBe(0.004);
    expect(pooledBenchmarkValue([group("cpm", 2, 500)], "cpm")).toBe(4);
  });

  it("preserves measured zero CTR and zero costs", () => {
    for (const metric of ["ctr", "cpc", "cpm", "cpa"] as const) {
      expect(pooledBenchmarkValue([group(metric, 0, 100)], metric)).toBe(0);
    }
  });

  it("does not substitute raw totals when component metadata is absent", () => {
    const legacy = { ...group("roas", 200, 100), metric_components: undefined, spend: 1000, revenue: 200 };
    expect(pooledBenchmarkValue([legacy], "roas")).toBeNull();
    expect(pooledBenchmarkValue([group("roas", 200, 100), legacy], "roas")).toBeNull();
  });

  it("does not silently skip a group with a missing component", () => {
    expect(pooledBenchmarkValue([group("ctr", 10, 100), group("cpa", 20, 5)], "ctr")).toBeNull();
  });

  it("keeps empty scopes unavailable and ignores explicitly empty groups", () => {
    expect(pooledBenchmarkValue([], "roas")).toBeNull();
    expect(pooledBenchmarkValue([{ n_ads: 0 }], "ctr")).toBeNull();
    expect(pooledBenchmarkValue([{ n_ads: 0 }, group("roas", 200, 100)], "roas")).toBe(2);
  });

  it("rejects nonfinite components and overflow instead of emitting an invalid number", () => {
    expect(pooledBenchmarkValue([group("ctr", NaN, 100)], "ctr")).toBeNull();
    expect(pooledBenchmarkValue([group("ctr", 1, Infinity)], "ctr")).toBeNull();
    expect(pooledBenchmarkValue([group("ctr", 1e308, 1), group("ctr", 1e308, 1)], "ctr")).toBeNull();
    expect(pooledBenchmarkValue([group("ctr", 1, 1e308), group("ctr", 1, 1e308)], "ctr")).toBeNull();
  });

  it("rejects contradictory or invalid reporting counts", () => {
    for (const component of [
      { reporting_rows: -1 }, { reporting_rows: 0.5 },
      { reporting_rows: 2, total_rows: 1 }, { total_rows: -1 },
      { reporting_rows: 0 },
    ]) {
      expect(pooledBenchmarkValue([group("ctr", 10, 100, {}, component)], "ctr")).toBeNull();
    }
  });

  it("does not mutate payloads and preserves equivalent group order", () => {
    const a = group("cpa", 20, 2);
    const b = group("cpa", 30, 3);
    const before = JSON.stringify([a, b]);
    expect(pooledBenchmarkValue([a, b], "cpa")).toBe(10);
    expect(pooledBenchmarkValue([b, a], "cpa")).toBe(10);
    expect(JSON.stringify([a, b])).toBe(before);
  });
});

describe("benchmark currency comparability", () => {
  it("rejects cross-currency monetary baselines for every money ratio", () => {
    for (const metric of ["cpa", "cpc", "cpm", "roas"] as const) {
      const a = group(metric, 100, 10);
      const b = group(metric, 200, 10, { currency: "EUR", currencies: ["EUR"] });
      expect(pooledBenchmarkValue([a, b], metric)).toBeNull();
      expect(hasComparableBenchmarkCurrency([a, b])).toBe(false);
    }
  });

  it("still pools nonmonetary CTR across currencies", () => {
    const a = group("ctr", 10, 100);
    const b = group("ctr", 30, 100, { currency: "EUR", currencies: ["EUR"] });
    expect(pooledBenchmarkValue([a, b], "ctr")).toBe(0.2);
  });

  it("retains same-currency monetary pooling", () => {
    expect(pooledBenchmarkValue([group("cpa", 100, 10), group("cpa", 300, 10)], "cpa")).toBe(20);
    expect(hasComparableBenchmarkCurrency([group("roas", 100, 10)])).toBe(true);
  });

  it("withholds monetary baselines for mixed or unknown-contribution groups", () => {
    for (const overrides of [{ mixed_currency: true }, { unknown_currency_contribution: true }]) {
      const a = group("roas", 100, 10, overrides);
      expect(hasComparableBenchmarkCurrency([a])).toBe(false);
      expect(pooledBenchmarkValue([a, group("roas", 200, 10)], "roas")).toBeNull();
    }
  });

  it("does not invent a currency for legacy or unspecified metadata", () => {
    for (const overrides of [
      { currency_known: undefined }, { currency_known: false },
      { currency: null }, { currency: " " }, { currencies: ["USD", "EUR"] },
    ]) {
      const a = group("roas", 200, 100, overrides);
      expect(hasComparableBenchmarkCurrency([a])).toBe(false);
      expect(pooledBenchmarkValue([a], "roas")).toBeNull();
    }
  });

  it("normalizes explicit currency spelling without converting amounts", () => {
    const a = group("roas", 100, 10, { currency: " usd ", currencies: ["usd"] });
    const b = group("roas", 200, 10);
    expect(hasComparableBenchmarkCurrency([a, b])).toBe(true);
    expect(pooledBenchmarkValue([a, b], "roas")).toBe(15);
  });

  it("does not make unknown-currency spend comparable merely because revenue is unreported", () => {
    const unknown = group("roas", 0, 0, { currency: null, currency_known: false },
      { reporting_rows: 0, total_spend: 900 });
    expect(pooledBenchmarkValue([group("roas", 200, 100), unknown], "roas")).toBeNull();
  });

  it("ignores empty groups but does not certify an empty money scope", () => {
    expect(hasComparableBenchmarkCurrency([])).toBe(false);
    expect(hasComparableBenchmarkCurrency([{ n_ads: 0 }])).toBe(false);
    expect(hasComparableBenchmarkCurrency([{ n_ads: 0 }, group("cpa", 100, 10)])).toBe(true);
  });
});

describe("baseline explanations and coverage", () => {
  it("reports ROAS spend coverage rather than record coverage", () => {
    const a = group("roas", 200, 100, {}, { total_spend: 100 });
    const b = group("roas", 0, 0, { n_ads: 9 }, { reporting_rows: 0, total_rows: 9, total_spend: 900 });
    expect(pooledBenchmark([a, b], "roas")).toEqual({
      value: 2, reason: null, coverage: { kind: "spend", reported: 100, total: 1000, share: 0.1 },
    });
  });

  it("labels common-ratio coverage as records, not denominator weight", () => {
    const a = group("ctr", 10, 100);
    const b = group("ctr", 0, 0, {}, { reporting_rows: 0 });
    expect(pooledBenchmark([a, b], "ctr")).toEqual({
      value: 0.1, reason: null, coverage: { kind: "rows", reported: 1, total: 2, share: 0.5 },
    });
  });

  it("distinguishes an empty scope from an unreported population", () => {
    expect(pooledBenchmark([], "roas").reason).toBe("empty");
    const absent = pooledBenchmark([group("ctr", 0, 0, {}, { reporting_rows: 0 })], "ctr");
    expect(absent.reason).toBe("unreported");
    expect(absent.coverage).toEqual({ kind: "rows", reported: 0, total: 1, share: 0 });
  });

  it("distinguishes currency limitations from missing reporting metadata", () => {
    expect(pooledBenchmark([group("roas", 20, 10, { currency_known: false })], "roas").reason)
      .toBe("currency");
    expect(pooledBenchmark([group("roas", 20, 10, { metric_components: undefined })], "roas").reason)
      .toBe("metadata");
  });

  it("distinguishes reported zero denominators from absent input", () => {
    const result = pooledBenchmark([group("cpa", 20, 0)], "cpa");
    expect(result.reason).toBe("denominator");
    expect(result.coverage).toEqual({ kind: "rows", reported: 1, total: 1, share: 1 });
  });

  it("does not mark a measured zero value as unavailable", () => {
    const result = pooledBenchmark([group("roas", 0, 100, {}, { total_spend: 100 })], "roas");
    expect(result.value).toBe(0);
    expect(result.reason).toBeNull();
    expect(result.coverage?.share).toBe(1);
  });

  it("does not invent spend coverage when the total is missing", () => {
    const result = pooledBenchmark([group("roas", 200, 100)], "roas");
    expect(result.value).toBe(2);
    expect(result.reason).toBeNull();
    expect(result.coverage).toBeNull();
  });

  it("does not display out-of-range spend coverage or suppress an otherwise usable ratio", () => {
    for (const total_spend of [0, -1, 50, NaN, Infinity]) {
      const result = pooledBenchmark([group("roas", 200, 100, {}, { total_spend })], "roas");
      expect(result.value).toBe(2);
      expect(result.coverage).toBeNull();
    }
  });

  it("reports inconsistent components as invalid rather than as zero", () => {
    expect(pooledBenchmark([group("ctr", Infinity, 100)], "ctr").reason).toBe("invalid");
    expect(pooledBenchmark([group("roas", 100, -1)], "roas").reason).toBe("invalid");
  });
});
