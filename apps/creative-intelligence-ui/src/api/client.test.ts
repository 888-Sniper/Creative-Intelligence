import { describe, expect, it } from "vitest";
import { scopedPath } from "@/api/client";

describe("scopedPath", () => {
  it("appends scope to the KPI compare endpoint", () => {
    const scope = new URLSearchParams({
      platform: "tiktok",
      date_from: "2024-01-01",
      date_to: "2024-01-07",
    });
    const url = scopedPath("/api/kpis/compare", scope);
    const params = new URLSearchParams(url.split("?")[1] ?? "");
    expect(params.get("platform")).toBe("tiktok");
    expect(params.get("date_from")).toBe("2024-01-01");
    expect(params.get("date_to")).toBe("2024-01-07");
  });

  it("leaves unscoped paths untouched", () => {
    const scope = new URLSearchParams({ platform: "tiktok" });
    expect(scopedPath("/api/sync/status", scope)).toBe("/api/sync/status");
  });
});
