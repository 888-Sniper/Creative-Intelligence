import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULTS,
  campaignStatusTouched,
  clearCampaignStatusTouched,
  confirmPrefsChanges,
  currentPrefsRevision,
  markCampaignStatusTouched,
  noteServerPrefsSnapshot,
  pendingPrefsChanges,
  queuePrefsChanges,
  replacePendingPrefs,
  savePrefs,
  loadPrefs,
  serverPrefsChanges,
  takePendingBatch,
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

describe("server prefs snapshot + pending changes (cross-tab safety)", () => {
  it("a commit's changes contain only the keys it actually changed", () => {
    const prev = { ...DEFAULTS, density: "Comfortable" };
    const next = { ...prev, theme: "dark" as const };
    // Even if another tab has since set density Compact on the
    // server, this commit never mentions density at all.
    expect(serverPrefsChanges(prev, next)).toEqual({ theme: "dark" });
  });

  it("pending changes accumulate and confirm only what was sent", () => {
    queuePrefsChanges("emp-p", { theme: "dark" });
    queuePrefsChanges("emp-p", { accent: "Blue" });
    expect(pendingPrefsChanges("emp-p"))
      .toEqual({ theme: "dark", accent: "Blue" });
    const batch = takePendingBatch("emp-p");
    // A revert queued behind the in-flight write overwrites the
    // pending value; confirming the sent batch must not drop it.
    queuePrefsChanges("emp-p", { theme: "light" });
    confirmPrefsChanges("emp-p", batch.seqs);
    expect(pendingPrefsChanges("emp-p")).toEqual({ theme: "light" });
    confirmPrefsChanges("emp-p", takePendingBatch("emp-p").seqs);
    expect(pendingPrefsChanges("emp-p")).toEqual({});
  });

  it("a delayed response cannot confirm a newer edit with an equal value", () => {
    queuePrefsChanges("emp-g", { theme: "dark" });
    const first = takePendingBatch("emp-g"); // in flight, response delayed
    // Newer edits while it is in flight: Light, then Dark again.
    queuePrefsChanges("emp-g", { theme: "light" });
    queuePrefsChanges("emp-g", { theme: "dark" });
    // The delayed response for the FIRST edit arrives: value
    // equality would wrongly drop the pending Dark re-selection;
    // generation matching must keep it.
    confirmPrefsChanges("emp-g", first.seqs);
    expect(pendingPrefsChanges("emp-g")).toEqual({ theme: "dark" });
    confirmPrefsChanges("emp-g", takePendingBatch("emp-g").seqs);
    expect(pendingPrefsChanges("emp-g")).toEqual({});
  });

  it("replace supersedes accumulated pending changes (Reset Defaults)", () => {
    queuePrefsChanges("emp-r", { theme: "dark" });
    replacePendingPrefs("emp-r", { theme: "light", density: "Comfortable" });
    expect(pendingPrefsChanges("emp-r"))
      .toEqual({ theme: "light", density: "Comfortable" });
  });

  it("snapshots are noted per account for this tab", () => {
    noteServerPrefsSnapshot("emp-x", { theme: "dark", _rev: 7 });
    expect(serverPrefsSnapshot("emp-x")?.["_rev"]).toBe(7);
    expect(serverPrefsSnapshot("emp-y")).toBeNull();
  });
});
