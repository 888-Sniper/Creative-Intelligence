import { describe, expect, it, vi } from "vitest";
import {
  applySavedView,
  compareDeepLink,
  type SavedView,
} from "@/components/savedViews";

const CMP4: SavedView = {
  id: 1,
  name: "Sample — Compare: Four Contrasts (ROAS)",
  state: {
    filters: {
      campaign: ["First Light Ritual", "One Sip Ahead", "The 6AM Commitment", "Find Your Focus"],
      date_from: ["2026-01-01"],
      date_to: ["2026-03-31"],
    },
    kpi: "roas",
    view: "compare",
    compare_mode: "campaigns",
  },
};

const FOCUS: SavedView = {
  id: 2,
  name: "Sample — Compare: Focus Creatives (CTR)",
  state: {
    filters: {
      campaign: ["Find Your Focus"],
      creative: ["smp-focus-desk-noise", "smp-focus-focus-session", "smp-focus-one-button"],
    },
    kpi: "ctr",
    view: "compare",
    compare_mode: "creatives",
  },
};

describe("compareDeepLink", () => {
  it("carries the full four-campaign selection", () => {
    expect(compareDeepLink(CMP4)).toBe(
      "/compare?mode=campaigns&campaigns=" +
        ["First Light Ritual", "One Sip Ahead", "The 6AM Commitment", "Find Your Focus"]
          .map(encodeURIComponent).join(","),
    );
  });

  it("carries explicit creative identities, not the campaign", () => {
    const link = compareDeepLink(FOCUS);
    expect(link).toContain("mode=creatives");
    expect(link).toContain("creatives=smp-focus-desk-noise");
    expect(link).toContain("smp-focus-one-button");
    expect(link).not.toContain("Find%20Your%20Focus");
  });

  it("returns null for non-compare views and single selections", () => {
    expect(compareDeepLink({ id: 3, name: "b", state: { view: "benchmark", filters: {} } })).toBeNull();
    expect(compareDeepLink({
      id: 4, name: "c",
      state: { view: "compare", compare_mode: "campaigns", filters: { campaign: ["Solo"] } },
    })).toBeNull();
  });
});

describe("applySavedView", () => {
  it("restores scope axes and KPI alongside the comparison link", () => {
    const setFilter = vi.fn();
    const navigate = vi.fn();
    const dest = applySavedView(CMP4, setFilter, navigate);
    expect(dest).toBe(compareDeepLink(CMP4));
    expect(navigate).toHaveBeenCalledWith(dest);
    const got = Object.fromEntries(setFilter.mock.calls.map(([k, v]) => [k, v]));
    expect(got["date_from"]).toBe("2026-01-01");
    expect(got["date_to"]).toBe("2026-03-31");
    expect(got["kpi"]).toBe("roas");
    // The deep link owns the selection: the single-value campaign
    // scope is cleared so Compare validates all four names.
    expect(got["campaign"]).toBe("");
  });

  it("falls back to the saved route for plain views", () => {
    const setFilter = vi.fn();
    const navigate = vi.fn();
    const dest = applySavedView({
      id: 5, name: "bench",
      state: { filters: { vertical: ["Beauty"] }, kpi: "cpa", view: "benchmark" },
    }, setFilter, navigate);
    expect(dest).toBe("/benchmarks");
    const got = Object.fromEntries(setFilter.mock.calls.map(([k, v]) => [k, v]));
    expect(got["vertical"]).toBe("Beauty");
    expect(got["kpi"]).toBe("cpa");
  });
});
