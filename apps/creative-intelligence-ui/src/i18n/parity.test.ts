import { describe, expect, it } from "vitest";
import { englishKeys, localeGaps, missingKeys, resetMissingKeys, translate } from "@/i18n/core";

/** §9/§16: English is the key source of truth — Spanish and Polish
 *  must carry the same key set so no interface surface falls back
 *  to English unnoticed. */
describe("locale parity", () => {
  it("defines the same keys in es and pl as in en", () => {
    expect(englishKeys().length).toBeGreaterThan(0);
    expect(localeGaps("es")).toEqual([]);
    expect(localeGaps("pl")).toEqual([]);
  });

  it("translates without falling back to English", () => {
    resetMissingKeys();
    for (const key of englishKeys()) {
      expect(translate("es", key)).not.toBe(key);
      expect(translate("pl", key)).not.toBe(key);
    }
    expect(missingKeys()).toEqual([]);
  });
});
