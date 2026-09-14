import { useEffect, useState } from "react";
import { EMPTY_FILTERS, useFilters, type FilterValues } from "@/state/FilterContext";
import { useLocale } from "@/i18n";

export const SAMPLE_SCOPE_KEY = "ci-sample-scope";

interface SampleScope {
  from: string; to: string; batch: string;
  prev?: Partial<FilterValues>;
  applied?: boolean;
}

function readScope(): SampleScope | null {
  try {
    const raw = localStorage.getItem(SAMPLE_SCOPE_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as SampleScope;
    if (!v || typeof v.from !== "string" || typeof v.to !== "string") return null;
    return v;
  } catch {
    return null;
  }
}

/** Sample Data banner: shown while a sample scope is active. Applies
 *  a clean presentation scope once (all five surviving sample
 *  campaigns visible: every narrowing filter cleared, pack date
 *  range set), re-asserts the pack dates after a full page load
 *  (which resets filter state but keeps the stored scope), and
 *  restores the pre-demo filters saved by the admin panel on
 *  return — user preferences are never silently wiped. */
export function SampleScopeBanner() {
  const { t } = useLocale();
  const { filters, setFilter, clearFilters } = useFilters();
  const [scope, setScope] = useState<SampleScope | null>(null);

  useEffect(() => {
    const s = readScope();
    if (!s) return;
    // A full page load resets FilterContext while the stored scope
    // survives: a pristine (all-empty) filter state with an already
    // applied scope means the demo dates were lost and must be
    // re-asserted — without touching the saved return path.
    const pristine = (Object.keys(EMPTY_FILTERS) as (keyof FilterValues)[])
      .every((k) => filters[k] === EMPTY_FILTERS[k]);
    if (!s.applied) {
      // The panel snapshots live pre-demo filters before navigating;
      // fall back to current non-empty filters only when it stored none.
      const prev: Partial<FilterValues> = { ...(s.prev ?? {}) };
      if (s.prev === undefined) {
        (Object.keys(EMPTY_FILTERS) as (keyof FilterValues)[]).forEach((k) => {
          if (filters[k] !== EMPTY_FILTERS[k]) prev[k] = filters[k];
        });
      }
      const next = { ...s, prev, applied: true };
      try {
        localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify(next));
      } catch { /* ignore */ }
      clearFilters();
      setFilter("date_from", s.from);
      setFilter("date_to", s.to);
      setScope(next);
    } else {
      if (pristine) {
        setFilter("date_from", s.from);
        setFilter("date_to", s.to);
      }
      setScope(s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!scope) return null;
  const ret = () => {
    const prev = scope.prev ?? {};
    (Object.keys(EMPTY_FILTERS) as (keyof FilterValues)[]).forEach((k) => {
      setFilter(k, (prev[k] as string | undefined) ?? EMPTY_FILTERS[k]);
    });
    try {
      localStorage.removeItem(SAMPLE_SCOPE_KEY);
    } catch { /* ignore */ }
    setScope(null);
  };
  return (
    <div role="status" aria-label={t("sample.scopeLabel")}
      style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        background: "var(--shell-green-soft)", border: "1px solid var(--shell-line)",
        borderRadius: 10, padding: "8px 12px", marginBottom: 12 }}>
      <span className="badge-demo">{t("sample.badge")}</span>
      <span className="panel-sub" style={{ margin: 0 }}>
        {t("sample.pack")} · {scope.from} → {scope.to}
      </span>
      <button type="button" className="link-btn" onClick={ret}>
        {t("sample.ret")}
      </button>
    </div>
  );
}
