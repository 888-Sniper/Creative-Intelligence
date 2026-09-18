import { describe, expect, it } from "vitest";
import { errorMessage, errorSheets } from "@/components/videoUploadApi";

/** Backend errors arrive top-level ({error, ...}) via the app's
 *  HTTPException handler — never under a {"detail"} envelope. */
describe("videoUploadApi error shapes", () => {
  it("reads top-level error text", () => {
    expect(errorMessage({ error: "boom" }, "fallback")).toBe("boom");
    expect(errorMessage({}, "fallback")).toBe("fallback");
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });

  it("tolerates a detail envelope when present", () => {
    expect(errorMessage({ detail: { error: "wrapped" } }, "fallback")).toBe("wrapped");
  });

  it("reads top-level sheet catalogues", () => {
    expect(errorSheets({ error: "x", sheets: ["Meta", "Notes"] })).toEqual(["Meta", "Notes"]);
    expect(errorSheets({ detail: { sheets: ["A"] } })).toEqual(["A"]);
    expect(errorSheets({ error: "x" })).toBeNull();
  });
});
