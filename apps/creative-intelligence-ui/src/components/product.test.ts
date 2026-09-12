import { describe, expect, it } from "vitest";
import { compareDisplayed } from "@/components/product";

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
