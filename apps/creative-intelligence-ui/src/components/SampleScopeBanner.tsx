import { useEffect, useState } from "react";
import { EMPTY_FILTERS, useFilters, type FilterValues } from "@/state/FilterContext";

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
 *  the pack date range once (saving prior filters), and restores them
 *  on return — user preferences are never silently wiped. */
export function SampleScopeBanner() {
  const { filters, setFilter } = useFilters();
  const [scope, setScope] = useState<SampleScope | null>(null);

  useEffect(() => {
    const s = readScope();
    if (!s) return;
    if (!s.applied) {
      const prev: Partial<FilterValues> = {};
      (Object.keys(EMPTY_FILTERS) as (keyof FilterValues)[]).forEach((k) => {
        if (filters[k] !== EMPTY_FILTERS[k]) prev[k] = filters[k];
      });
      const next = { ...s, prev, applied: true };
      try {
        localStorage.setItem(SAMPLE_SCOPE_KEY, JSON.stringify(next));
      } catch { /* ignore */ }
      setFilter("date_from", s.from);
      setFilter("date_to", s.to);
      setScope(next);
    } else {
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
    <div role="status" aria-label="Sample Data Scope"
      style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        background: "#EAF6F1", border: "1px solid var(--shell-line)",
        borderRadius: 10, padding: "8px 12px", marginBottom: 12 }}>
      <span className="badge-demo">Sample Data</span>
      <span className="panel-sub" style={{ margin: 0 }}>
        Presentation Pack · {scope.from} → {scope.to}
      </span>
      <button type="button" className="link-btn" onClick={ret}>
        Return To My Scope
      </button>
    </div>
  );
}
