import { describe, expect, it } from "vitest";
import {
  EMPTY_KPI_NOTE,
  KPI_UNAVAILABLE,
  compareDisplayed,
  fmtCell,
  formatDuration,
  kpiDisplay,
  kpiPlaceholderNote,
  plural,
} from "@/components/product";

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

describe("kpiDisplay", () => {
  it("shows formatted zero placeholders for an empty loaded scope", () => {
    expect(kpiDisplay("money", null, true)).toBe("$0.00");
    expect(kpiDisplay("money", undefined, true)).toBe("$0.00");
    expect(kpiDisplay("mult", null, true)).toBe("0.0x");
    expect(kpiDisplay("count", null, true)).toBe("0");
    expect(kpiDisplay("pct", null, true)).toBe("0.0%");
  });

  it("says Unavailable for uncomputable metrics in nonempty data", () => {
    expect(kpiDisplay("money", null, false)).toBe(KPI_UNAVAILABLE);
    expect(kpiDisplay("mult", null, false)).toBe(KPI_UNAVAILABLE);
    expect(kpiDisplay("count", undefined, false)).toBe(KPI_UNAVAILABLE);
    expect(kpiDisplay("pct", Number.NaN, false)).toBe(KPI_UNAVAILABLE);
  });

  it("formats real values with the shared conventions", () => {
    expect(kpiDisplay("money", 2500, false)).toBe("$2.5K");
    expect(kpiDisplay("mult", 2.345, false)).toBe("2.3x");
    expect(kpiDisplay("count", 1500, false)).toBe("1.5K");
    expect(kpiDisplay("pct", 12.345, false)).toBe("12.3%");
  });
});

describe("kpiPlaceholderNote", () => {
  it("notes empty ratio/percentage placeholders only", () => {
    expect(kpiPlaceholderNote("mult", null, true)).toBe(EMPTY_KPI_NOTE);
    expect(kpiPlaceholderNote("pct", null, true)).toBe(EMPTY_KPI_NOTE);
    expect(kpiPlaceholderNote("money", null, true)).toBeNull();
    expect(kpiPlaceholderNote("count", null, true)).toBeNull();
    expect(kpiPlaceholderNote("mult", 1.5, true)).toBeNull();
    expect(kpiPlaceholderNote("mult", null, false)).toBeNull();
  });
});

describe("fmtCell", () => {
  it("marks missing measures Unavailable without touching values", () => {
    expect(fmtCell(null, (n: number) => `$${n}`)).toBe(KPI_UNAVAILABLE);
    expect(fmtCell(undefined, (n: number) => `$${n}`)).toBe(KPI_UNAVAILABLE);
    expect(fmtCell(Number.NaN, (n: number) => `$${n}`)).toBe(KPI_UNAVAILABLE);
    expect(fmtCell(0, (n: number) => `$${n}`)).toBe("$0");
    expect(fmtCell(5, (n: number) => `$${n}`)).toBe("$5");
  });
});
