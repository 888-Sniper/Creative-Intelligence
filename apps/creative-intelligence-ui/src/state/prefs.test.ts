import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULTS,
  campaignStatusTouched,
  clearCampaignStatusTouched,
  currentPrefsRevision,
  markCampaignStatusTouched,
  noteServerPrefsSnapshot,
  savePrefs,
  loadPrefs,
  serverPrefsDelta,
  serverPrefsSnapshot,
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

  it("clearing forgets the choice so the saved default applies again", () => {
    markCampaignStatusTouched("emp-a", "Completed");
    clearCampaignStatusTouched("emp-a");
    expect(campaignStatusTouched("emp-a")).toBe(false);
    expect(touchedCampaignStatus("emp-a")).toBeNull();
  });

  it("bumps the edit revision on every save, including revert-to-original", () => {
    const before = currentPrefsRevision();
    const prefs = loadPrefs("emp-a");
    savePrefs("emp-a", { ...prefs, theme: "dark" });
    savePrefs("emp-a", { ...prefs, theme: "light" });
    expect(currentPrefsRevision()).toBe(before + 2);
  });
});

describe("server prefs snapshot + delta (cross-tab safety)", () => {
  it("delta contains only keys changed since this tab's snapshot", () => {
    const snapshot = { theme: "light", density: "Compact", _rev: 3 };
    const delta = serverPrefsDelta(
      snapshot, { ...DEFAULTS, theme: "dark", density: "Compact" });
    expect(delta["theme"]).toBe("dark");
    // Unchanged since the snapshot: never re-sent, so another
    // tab's newer density cannot be overwritten by this tab.
    expect(delta).not.toHaveProperty("density");
  });

  it("null snapshot yields the full bootstrap document", () => {
    const delta = serverPrefsDelta(null, { ...DEFAULTS });
    expect(delta["theme"]).toBe(DEFAULTS.theme);
    expect(delta["density"]).toBe(DEFAULTS.density);
  });

  it("snapshots are noted per account for this tab", () => {
    noteServerPrefsSnapshot("emp-x", { theme: "dark", _rev: 7 });
    expect(serverPrefsSnapshot("emp-x")?.["_rev"]).toBe(7);
    expect(serverPrefsSnapshot("emp-y")).toBeNull();
  });
});
