import { describe, expect, it } from "vitest";
import { presetDateRange } from "./datePresets";

describe("presetDateRange", () => {
  const now = new Date("2026-10-29T23:45:00.000Z");

  it.each([
    [1, "2026-10-29"],
    [7, "2026-10-23"],
    [30, "2026-09-30"],
    [90, "2026-08-01"],
  ])("returns inclusive bounds for %i days", (days, date_from) => {
    expect(presetDateRange(days, now)).toEqual({ date_from, date_to: "2026-10-29" });
    expect(now.toISOString()).toBe("2026-10-29T23:45:00.000Z");
  });

  it("includes leap day when a range crosses February", () => {
    expect(presetDateRange(3, new Date("2024-03-01T00:15:00Z"))).toEqual({
      date_from: "2024-02-28", date_to: "2024-03-01",
    });
  });

  it.each([NaN, Infinity, -Infinity, 0, -1, 1.5, Number.MAX_SAFE_INTEGER, Number.MAX_VALUE])(
    "rejects an invalid or unrepresentable day count (%s)",
    (days) => expect(presetDateRange(days, now)).toBeNull(),
  );

  it("rejects an invalid clock value without formatting an invalid date", () => {
    expect(presetDateRange(7, new Date(NaN))).toBeNull();
  });
});
