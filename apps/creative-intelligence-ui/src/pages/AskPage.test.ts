import { describe, expect, it } from "vitest";
import { bucket } from "./AskPage";

function days(start: string, n: number, revenue: number) {
  const out: Array<{ date: string; revenue: number }> = [];
  const t = Date.parse(start);
  for (let i = 0; i < n; i++) {
    out.push({
      date: new Date(t + i * 86400000).toISOString().slice(0, 10),
      revenue,
    });
  }
  return out;
}

describe("ask revenue bucketing", () => {
  it("passes short series through untouched", () => {
    const pts = days("2026-01-01", 5, 100);
    expect(bucket(pts)).toEqual({
      labels: ["01-01", "01-02", "01-03", "01-04", "01-05"],
      values: [100, 100, 100, 100, 100],
    });
  });

  it("keeps every bucket comparable on flat input (no final cliff)", () => {
    // 90 flat days: fixed-count chunking left a 2-day final bucket
    // (~25% mass) that read as a revenue cliff.
    const { labels, values } = bucket(days("2026-01-01", 90, 100));
    expect(values).toHaveLength(12);
    expect(labels).toHaveLength(12);
    expect(values.reduce((t, v) => t + v, 0)).toBe(9000);
    // Equal 7.5-day spans: every bucket holds 7 or 8 days.
    for (const v of values) expect([700, 800]).toContain(v);
  });

  it("preserves a genuine mid-series dip", () => {
    const pts = days("2026-01-01", 90, 100);
    for (let i = 40; i < 48; i++) pts[i].revenue = 0;
    const { values } = bucket(pts);
    expect(Math.min(...values)).toBeLessThan(700);
    expect(values[values.length - 1]).toBeGreaterThanOrEqual(700);
  });
});
