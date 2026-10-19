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
  currentCommitGen,
  isStaleServerPrefs,
  nextCommitGen,
  recordSaveOutcome,
  saveOutcome,
  withoutPendingPrefs,
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

  it("a stale GET response cannot move the snapshot backward", () => {
    noteServerPrefsSnapshot("emp-s", { density: "Compact", _rev: 12 });
    // Read before an in-flight PUT landed, delivered after it:
    expect(isStaleServerPrefs("emp-s", { density: "Comfortable", _rev: 11 }))
      .toBe(true);
    noteServerPrefsSnapshot("emp-s", { density: "Comfortable", _rev: 11 });
    expect(serverPrefsSnapshot("emp-s")?.["density"]).toBe("Compact");
    expect(serverPrefsSnapshot("emp-s")?.["_rev"]).toBe(12);
    // Equal/newer revisions are not stale.
    expect(isStaleServerPrefs("emp-s", { _rev: 12 })).toBe(false);
    expect(isStaleServerPrefs("emp-s", { _rev: 13 })).toBe(false);
    expect(isStaleServerPrefs("emp-none", { _rev: 1 })).toBe(false);
    // An UNVERSIONED legacy payload counts as version 0: stale
    // against any confirmed save, and it cannot replace the
    // snapshot either.
    expect(isStaleServerPrefs("emp-s", { density: "Comfortable" })).toBe(true);
    noteServerPrefsSnapshot("emp-s", { density: "Comfortable" });
    expect(serverPrefsSnapshot("emp-s")?.["density"]).toBe("Compact");
    expect(serverPrefsSnapshot("emp-s")?.["_rev"]).toBe(12);
  });

  it("save outcomes are per-account, generation-ordered, and survive remounts", () => {
    const g1 = nextCommitGen();
    const g2 = nextCommitGen();
    expect(g2).toBeGreaterThan(g1);
    expect(currentCommitGen()).toBe(g2);
    recordSaveOutcome("emp-o", g2, true);
    // An older settle cannot overwrite the newer failure.
    recordSaveOutcome("emp-o", g1, false);
    expect(saveOutcome("emp-o").failed).toBe(true);
    // A newer success clears it; other accounts unaffected.
    recordSaveOutcome("emp-o", nextCommitGen(), false);
    expect(saveOutcome("emp-o").failed).toBe(false);
    expect(saveOutcome("emp-other").failed).toBe(false);
  });

  it("merging can exclude keys whose writes are still in flight", () => {
    queuePrefsChanges("emp-w", { density: "Compact" });
    const filtered = withoutPendingPrefs("emp-w", {
      density: "Comfortable", theme: "dark", _rev: 5,
    });
    expect(filtered).not.toHaveProperty("density");
    expect(filtered["theme"]).toBe("dark");
  });
});
