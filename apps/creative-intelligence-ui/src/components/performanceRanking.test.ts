import { describe, expect, it } from "vitest";
import { selectTopCreatives, topPerformanceValue } from "./performanceRanking";

describe("top performer benchmarks", () => {
  it.each([
    ["cpa", [2, 5], 2],
    ["cpc", [0.3, 0.8], 0.3],
    ["ctr", [1, 3], 3],
    ["roas", [1.2, 4], 4],
  ] as const)("uses the correct direction for %s", (metric, values, expected) => {
    expect(topPerformanceValue(values, metric)).toBe(expected);
    expect(topPerformanceValue([...values].reverse(), metric)).toBe(expected);
  });

  it.each(["cpa", "cpc", "ctr", "roas"] as const)("excludes missing measurements for %s", (metric) => {
    expect(topPerformanceValue([null, undefined, NaN, Infinity, -Infinity, 2], metric)).toBe(2);
    expect(topPerformanceValue([null, undefined, NaN, Infinity], metric)).toBeNull();
    expect(topPerformanceValue([], metric)).toBeNull();
  });

  it("preserves a measured zero cost", () => {
    expect(topPerformanceValue([null, 0, 5], "cpa")).toBe(0);
  });
});

describe("Top Creatives ordering", () => {
  const creative = (key: string, roas: number | null, ctr: number | null) => ({
    creative_key: key, metrics: { roas, ctr },
  });
  const keys = (rows: Parameters<typeof selectTopCreatives>[0]) => selectTopCreatives(rows).map((row) => row.creative_key);

  it("breaks equal ROAS with CTR in either input order", () => {
    const rows = [creative("low-ctr", 2, 0.01), creative("high-ctr", 2, 0.03)];
    expect(keys(rows)).toEqual(["high-ctr", "low-ctr"]);
    expect(keys([...rows].reverse())).toEqual(["high-ctr", "low-ctr"]);
  });

  it("ranks measured ROAS before missing ROAS without comparing ROAS to CTR", () => {
    const rows = [creative("missing-roas", null, 0.99), creative("zero-roas", 0, null)];
    expect(keys(rows)).toEqual(["zero-roas", "missing-roas"]);
  });

  it("prioritizes ROAS over a higher CTR", () => {
    expect(keys([creative("high-ctr", 1, 0.9), creative("high-roas", 2, 0.01)]))
      .toEqual(["high-roas", "high-ctr"]);
  });

  it("uses a deterministic key tie-breaker and does not mutate input", () => {
    const rows = Object.freeze(["f", "c", "e", "a", "d", "b"].map((key) => Object.freeze(creative(key, 2, 0.03))));
    expect(keys(rows)).toEqual(["a", "b", "c", "d"]);
    expect(keys([...rows].reverse())).toEqual(["a", "b", "c", "d"]);
    expect(rows.map((row) => row.creative_key)).toEqual(["f", "c", "e", "a", "d", "b"]);
  });

  it("keeps zero CTR measurable when ROAS is missing", () => {
    expect(keys([creative("unknown", null, null), creative("zero-ctr", null, 0)]))
      .toEqual(["zero-ctr", "unknown"]);
  });

  it("handles absent and non-finite metrics deterministically", () => {
    const rows = [
      creative("d", NaN, Infinity),
      { creative_key: "c", metrics: null },
      { creative_key: "b" },
      creative("a", null, null),
    ];
    expect(keys(rows)).toEqual(["a", "b", "c", "d"]);
    expect(keys([])).toEqual([]);
  });
});
