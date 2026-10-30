import { describe, expect, it } from "vitest";
import { compareSelectionNames, compareSelectionQuery } from "./compareSelection";

describe("compareSelectionNames", () => {
  it("keeps an encoded comma inside a legacy joined link", () => {
    const search = `?mode=campaigns&campaigns=${encodeURIComponent("US, CA")},Other`;
    expect(compareSelectionNames(search, "campaigns")).toEqual(["US, CA", "Other"]);
  });

  it("still splits an ordinary legacy list", () => {
    expect(compareSelectionNames("?creatives=A,B", "creatives")).toEqual(["A", "B"]);
    expect(compareSelectionNames("?campaigns=Two,One", "campaigns")).toEqual(["Two", "One"]);
  });

  it("round-trips exact names, including a trimmed surrounding space", () => {
    const query = compareSelectionQuery("campaigns", "campaigns", [" US, CA ", "A&B", "100%", "Łódź"]);
    expect(new URLSearchParams(query).getAll("campaigns")).toEqual([" US, CA ", "A&B", "100%", "Łódź"]);
    expect(compareSelectionNames(`?${query}`, "campaigns")).toEqual(["US, CA", "A&B", "100%", "Łódź"]);
  });
});
