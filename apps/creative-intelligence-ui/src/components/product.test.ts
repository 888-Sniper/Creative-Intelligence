import { describe, expect, it } from "vitest";
import { compareDisplayed, formatDuration, plural } from "@/components/product";

describe("plural", () => {
  it("uses the singular form for exactly one", () => {
    expect(plural(1, "Campaign")).toBe("1 Campaign");
    expect(plural(1, "KPI", "KPIs")).toBe("1 KPI");
  });

  it("uses the plural form otherwise", () => {
    expect(plural(0, "Campaign")).toBe("0 Campaigns");
    expect(plural(2, "Campaign")).toBe("2 Campaigns");
    expect(plural(5, "KPI", "KPIs")).toBe("5 KPIs");
  });
});

describe("compareDisplayed", () => {
  it("crowns a strict lead at display precision", () => {
    expect(compareDisplayed(3.7, 3.6)).toBe("lead");
    expect(compareDisplayed(3.6, 3.7)).toBe("trail");
  });

  it("ties values the UI prints identically", () => {
    // 3.61 vs 3.60 both print "3.6": a heading must not crown either.
    expect(compareDisplayed(3.61, 3.6)).toBe("tie");
    expect(compareDisplayed(2.0, 2.0)).toBe("tie");
  });

  it("reports unknown for missing evidence", () => {
    expect(compareDisplayed(NaN, 3.6)).toBe("unknown");
    expect(compareDisplayed(3.6, Number.NaN)).toBe("unknown");
  });
});

describe("formatDuration", () => {
  it("formats sub-minute clips", () => {
    expect(formatDuration(9)).toBe("0:09");
    expect(formatDuration(45)).toBe("0:45");
  });

  it("never renders a bare 0:SS minute part past 59 seconds", () => {
    // Regression: 75 seconds once rendered as "0:75".
    expect(formatDuration(75)).toBe("1:15");
    expect(formatDuration(150)).toBe("2:30");
    expect(formatDuration(null)).toBe("0:00");
  });
});
