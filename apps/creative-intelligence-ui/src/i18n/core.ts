/** Minimal typed interface localization (no third-party dependency).
 *
 *  Conventions:
 *  - Stable dot-separated keys (e.g. "nav.dashboard", "settings.save").
 *  - Every supported language carries the SAME key set: English is the
 *    source of truth, Spanish and Polish must stay aligned with it.
 *  - Missing keys fall back to English at runtime and are reported
 *    through `missingKeys()` so developers can find gaps (and tests
 *    can assert parity across locales).
 *  - Interpolation uses {name} placeholders; pluralization picks
 *    `<key>_<category>` via Intl.PluralRules with fallback to
 *    `<key>_other`, then the bare key.
 *  - User-entered content, campaign names, uploaded data, and AI
 *    conversation history are NEVER passed through t(): only fixed
 *    interface chrome is localized.
 */

export type Lang = "en" | "es" | "pl";

export const LANGS: Array<{ id: Lang; label: string }> = [
  { id: "en", label: "English" },
  { id: "es", label: "Español" },
  { id: "pl", label: "Polski" },
];

export function isLang(v: unknown): v is Lang {
  return v === "en" || v === "es" || v === "pl";
}

type Dict = { [key: string]: string | Dict };

function flatten(dict: Dict, prefix: string, out: Map<string, string>): void {
  for (const [k, v] of Object.entries(dict)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out.set(key, v);
    else flatten(v, key, out);
  }
}

// Locale resources live beside this module so bundlers include them
// statically (no runtime fetching, no network failure mode).
import { en } from "./locales/en";
import { es } from "./locales/es";
import { pl } from "./locales/pl";

const resources: Record<Lang, Dict> = { en, es, pl };

const tables = new Map<Lang, Map<string, string>>();
function table(lang: Lang): Map<string, string> {
  let t = tables.get(lang);
  if (!t) {
    t = new Map();
    flatten(resources[lang], "", t);
    tables.set(lang, t);
  }
  return t;
}

const seenMissing = new Set<string>();

/** Keys requested in a non-English language that fell back to English
 *  (or vanished entirely). Surfaced for tests and dev warnings. */
export function missingKeys(): string[] {
  return [...seenMissing].sort();
}

export function resetMissingKeys(): void {
  seenMissing.clear();
}

function lookup(lang: Lang, key: string): string | null {
  const hit = table(lang).get(key);
  if (hit !== undefined) return hit;
  if (lang !== "en") {
    seenMissing.add(`${lang}:${key}`);
    const en = table("en").get(key);
    if (en !== undefined) return en;
  }
  seenMissing.add(`en:${key}`);
  return null;
}

function fill(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, name: string) =>
    vars[name] === undefined ? m : String(vars[name]),
  );
}

export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const hit = lookup(lang, key);
  if (hit === null) return key;
  return fill(hit, vars);
}

export function translatePlural(
  lang: Lang, key: string, count: number,
  vars?: Record<string, string | number>,
): string {
  let category = "other";
  try {
    category = new Intl.PluralRules(lang).select(count);
  } catch {
    category = count === 1 ? "one" : "other";
  }
  const all = { ...vars, count };
  const specific = lookup(lang, `${key}_${category}`);
  if (specific !== null) return fill(specific, all);
  if (category !== "other") {
    const other = lookup(lang, `${key}_other`);
    if (other !== null) return fill(other, all);
  }
  const bare = lookup(lang, key);
  if (bare !== null) return fill(bare, all);
  return key;
}

/** Every key the English source defines (parity target for es/pl). */
export function englishKeys(): string[] {
  return [...table("en").keys()].sort();
}

/** Keys missing from a locale relative to English (empty when aligned). */
export function localeGaps(lang: Lang): string[] {
  const en = table("en");
  const other = table(lang);
  const gaps: string[] = [];
  for (const key of en.keys()) {
    if (!other.has(key)) gaps.push(key);
  }
  return gaps.sort();
}
