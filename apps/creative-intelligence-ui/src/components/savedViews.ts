import type { FilterValues } from "@/state/FilterContext";

export interface SavedViewState {
  filters?: Record<string, string[]>;
  kpi?: string;
  view?: string;
  benchmark?: string;
  benchmark_scope?: string;
  rank_by?: string;
  compare_mode?: string;
}

export interface SavedView {
  id: number;
  name: string;
  state?: SavedViewState;
}

export const VIEW_ROUTES: Record<string, string> = {
  main: "/",
  campaign: "/campaigns",
  creative: "/creatives",
  compare: "/compare",
  benchmark: "/benchmarks",
  report: "/reports",
  profile: "/profile",
  admin: "/admin",
};

/** Single-value global scope axes, restored first-wins from storage. */
export const SAVED_SCOPE_KEYS: (keyof FilterValues)[] = [
  "client", "project", "team", "campaign", "platform",
  "vertical", "market", "funnel", "objective", "status", "spend_min",
  "spend_max", "hook_type", "creator_vs_branded", "format", "date",
  "date_from", "date_to",
];

/** Deep link carrying the FULL multi-entry selection (up to 4) for
 *  saved comparisons — campaign or explicit creative identities —
 *  or null when the view is not a restorable comparison. */
export function compareDeepLink(v: SavedView): string | null {
  if (v.state?.view !== "compare") return null;
  const mode = v.state?.compare_mode === "creatives" ? "creatives" : "campaigns";
  const key = mode === "campaigns" ? "campaign" : "creative";
  const f = v.state?.filters ?? {};
  const raw = f[key];
  const list = [...new Set(
    (Array.isArray(raw) ? raw : (raw ? [raw] : []))
      .map((s) => String(s)).filter(Boolean))].slice(0, 4);
  if (list.length < 2) return null;
  const param = mode === "campaigns" ? "campaigns" : "creatives";
  return `/compare?mode=${mode}&${param}=${list.map(encodeURIComponent).join(",")}`;
}

export type SetFilter = (key: keyof FilterValues, value: string) => void;

/** Restore a saved view: the comparison deep link (full selection)
 *  when one applies, otherwise the saved route; every stored scope
 *  axis and the saved KPI travel along either way. The global scope
 *  model holds one value per axis, so the first stored value wins
 *  when several were saved. MUST navigate client-side (SPA): a hard
 *  reload would reset filter state and silently drop the restore. */
export function applySavedView(
  v: SavedView, setFilter: SetFilter, navigate: (to: string) => void,
): string {
  const link = compareDeepLink(v);
  const f = v.state?.filters ?? {};
  for (const k of SAVED_SCOPE_KEYS) {
    // A comparison deep link owns the campaign/creative selection:
    // the single-value scope must be cleared, never narrowed to the
    // first entry — Compare validates the link against scope-filtered
    // options, so a narrowed scope rejects the other selections.
    if (link && k === "campaign") {
      setFilter(k, "");
      continue;
    }
    const vals = f[k] ?? [];
    setFilter(k, vals[0] ?? "");
  }
  if (v.state?.kpi) setFilter("kpi", v.state.kpi);
  const dest = link ?? (v.state?.view ? (VIEW_ROUTES[v.state.view] ?? "/") : "/");
  navigate(dest);
  return dest;
}
