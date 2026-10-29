import { describe, expect, it } from "vitest";
import { dailyMetricValue } from "./compareDaily";

const base = {
  spend: 200, revenue: 200, impressions: 10000, clicks: 200, conversions: 10,
};

describe("dailyMetricValue", () => {
  it("prefers canonical daily ratios over recomputation", () => {
    const point = { ...base, roas: 2, cpa: 10, cpm: 20 };
    expect(dailyMetricValue(point, "roas")).toBe(2);
    expect(dailyMetricValue(point, "cpa")).toBe(10);
    expect(dailyMetricValue(point, "cpm")).toBe(20);
  });

  it("keeps explicit canonical nulls unavailable", () => {
    const point = { ...base, roas: null, cpa: null, cpm: null };
    expect(dailyMetricValue(point, "roas")).toBeNull();
    expect(dailyMetricValue(point, "cpa")).toBeNull();
    expect(dailyMetricValue(point, "cpm")).toBeNull();
  });

  it("falls back for payloads without canonical keys", () => {
    expect(dailyMetricValue(base, "roas")).toBe(1);
    expect(dailyMetricValue(base, "cpa")).toBe(20);
    expect(dailyMetricValue(base, "cpm")).toBe(20);
  });

  it("computes dimensionless ctr and raw metrics", () => {
    expect(dailyMetricValue(base, "ctr")).toBe(2);
    expect(dailyMetricValue(base, "spend")).toBe(200);
    expect(dailyMetricValue({ ...base, impressions: 0 }, "ctr")).toBeNull();
  });
});
