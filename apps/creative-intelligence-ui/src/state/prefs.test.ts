import { beforeEach, describe, expect, it } from "vitest";
import {
  campaignStatusTouched,
  currentPrefsRevision,
  markCampaignStatusTouched,
  savePrefs,
  loadPrefs,
  touchedCampaignStatus,
} from "./prefs";

describe("campaign status touched (per account)", () => {
  beforeEach(() => {
    try {
      window.sessionStorage?.clear();
    } catch { /* storage unavailable in this jsdom setup */ }
    try {
      window.localStorage?.clear();
    } catch { /* storage unavailable in this jsdom setup */ }
  });

  it("is scoped per employee and survives remount via sessionStorage", () => {
    expect(campaignStatusTouched("emp-a")).toBe(false);
    expect(touchedCampaignStatus("emp-a")).toBeNull();
    markCampaignStatusTouched("emp-a", "Completed");
    expect(campaignStatusTouched("emp-a")).toBe(true);
    // The VALUE travels with the flag so a reload restores it
    // instead of stranding the page on All.
    expect(touchedCampaignStatus("emp-a")).toBe("Completed");
    // Account B's saved default must not be disabled by A's choice.
    expect(campaignStatusTouched("emp-b")).toBe(false);
    expect(touchedCampaignStatus("emp-b")).toBeNull();
  });

  it("bumps the edit revision on every save, including revert-to-original", () => {
    const before = currentPrefsRevision();
    const prefs = loadPrefs("emp-a");
    savePrefs("emp-a", { ...prefs, theme: "dark" });
    savePrefs("emp-a", { ...prefs, theme: "light" });
    expect(currentPrefsRevision()).toBe(before + 2);
  });
});
