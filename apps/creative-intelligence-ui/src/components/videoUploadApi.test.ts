import { describe, expect, it, vi } from "vitest";
import {
  correctDraft,
  errorMessage,
  errorSheets,
  HOOK_TYPE_OPTIONS,
} from "@/components/videoUploadApi";

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

describe("videoUploadApi corrections", () => {
  it("posts corrections to the draft endpoint and returns the revision", async () => {
    const seen: Array<{ url: string; body: unknown }> = [];
    window.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      seen.push({ url: String(input), body: JSON.parse(String(init?.body)) });
      return Response.json({ draft: { id: "d" }, annotation: {}, revision: "rev-9" });
    }) as typeof fetch;
    const res = await correctDraft("d", {
      transcript: "fixed words",
      tests: [{ id: "hook-clarity", status: "accepted" }],
    });
    expect(seen).toHaveLength(1);
    expect(seen[0].url).toBe("/api/drafts/d/corrections");
    expect(seen[0].body).toEqual({
      transcript: "fixed words",
      tests: [{ id: "hook-clarity", status: "accepted" }],
    });
    expect(res.revision).toBe("rev-9");
    vi.restoreAllMocks();
  });

  it("covers the server hook taxonomy", () => {
    expect(HOOK_TYPE_OPTIONS).toContain("bold_claim");
    expect(HOOK_TYPE_OPTIONS).toContain("question");
  });
});
