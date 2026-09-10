import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import type { FilterValues } from "@/state/FilterContext";

const GROUP_OPTIONS = ["hook_type", "creator_vs_branded", "edit_style", "platform", "campaign"];
const METRIC_OPTIONS = ["cpa", "cpm", "ctr", "vtr", "roas"];
const KPI_OPTIONS = ["all", "spend", "ctr", "cpc", "cpa", "cpm", "vtr", "roas"];
const LOWER_BETTER = ["cpa", "cpc", "cpm"];
const SCOPE_AXES: (keyof Omit<FilterValues, "kpi">)[] = [
  "client",
  "project",
  "campaign",
  "platform",
  "vertical",
  "market",
  "funnel",
  "objective",
  "date",
  "date_from",
  "date_to",
];
const VIEW_ROUTES: Record<string, string> = {
  main: "/",
  campaign: "/campaigns",
  creative: "/creatives",
  compare: "/compare",
  benchmark: "/benchmarks",
  report: "/reports",
  profile: "/profile",
  admin: "/admin",
};

interface BenchmarkGroup {
  n_ads: number;
  spend: number;
  ctr: number | null;
  cpc: number | null;
  cpa: number | null;
}

interface RetentionPattern {
  slot: string | null;
  product_demo: boolean;
  brand_visible: boolean;
  cta_present: boolean;
  voiceover: boolean;
  n_creatives: number;
  avg_drop_pts: number;
  max_drop_pts: number;
  examples: string[];
}

interface PatternsResponse {
  scope?: string;
  n_creatives?: number;
  n_events?: number;
  patterns?: RetentionPattern[];
}

interface Cohort {
  id: number;
  name: string;
  filters: Record<string, string[]>;
}

interface CohortBuild {
  name?: string;
  cohort?: { name?: string };
  metric?: string;
  n_ads?: number;
  project_list?: string[];
  stats?: {
    n?: number;
    mean_weighted?: number | null;
    median?: number | null;
    p25?: number | null;
    p75?: number | null;
  };
  status?: string;
}

interface ViewState {
  filters?: Record<string, string[]>;
  kpi?: string;
  view?: string;
  benchmark?: string;
  benchmark_scope?: string;
  rank_by?: string;
}

interface SavedView {
  id: number;
  name: string;
  state: ViewState;
}

/** Legacy kpi() parity: uncomputable (null) renders as an em dash, never zero. */
function fmt(v: number | null | undefined, money = false): string {
  if (v === null || v === undefined) return "—";
  return (money ? "$" : "") + String(v);
}

function rankVal(v: number | null | undefined, lower: boolean): number {
  if (v === null || v === undefined) return lower ? Infinity : -Infinity;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** Legacy sort_rows() parity: sort benchmark groups by the KPI selector. */
function sortEntries(entries: [string, BenchmarkGroup][], kpi: string): [string, BenchmarkGroup][] {
  if (!kpi || kpi === "all") return entries;
  const lower = LOWER_BETTER.includes(kpi);
  const val = (g: BenchmarkGroup): number | null | undefined =>
    (g as unknown as Record<string, number | null | undefined>)[kpi];
  return entries.slice().sort((a, b) => {
    const va = rankVal(val(a[1]), lower);
    const vb = rankVal(val(b[1]), lower);
    return lower ? va - vb : vb - va;
  });
}

function patternBits(p: RetentionPattern): string {
  const bits: (string | null)[] = [
    p.slot ? `during ${p.slot}` : "any segment",
    p.product_demo ? "product demo on screen" : null,
    p.brand_visible ? "brand visible" : null,
    p.cta_present ? "CTA present" : null,
    p.voiceover ? "voiceover running" : null,
  ];
  return bits.filter((b): b is string => b !== null).join(" · ");
}

function splitList(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function BenchmarksPage() {
  const { filters, setFilter, scope } = useFilters();
  const navigate = useNavigate();
  const scopeKey = scope.toString();

  const [groupBy, setGroupBy] = useState("hook_type");
  const [bench, setBench] = useState<Record<string, BenchmarkGroup> | null>(null);
  const [benchLoading, setBenchLoading] = useState(true);
  const [benchError, setBenchError] = useState("");

  const [patterns, setPatterns] = useState<PatternsResponse | null>(null);
  const [patternsLoading, setPatternsLoading] = useState(true);
  const [patternsError, setPatternsError] = useState("");

  const [cohortName, setCohortName] = useState("");
  const [cohortMetric, setCohortMetric] = useState("cpa");
  const [includeProjects, setIncludeProjects] = useState("");
  const [excludeProjects, setExcludeProjects] = useState("");
  const [cohorts, setCohorts] = useState<Cohort[] | null>(null);
  const [cohortsLoading, setCohortsLoading] = useState(true);
  const [cohortsError, setCohortsError] = useState("");
  const [buildingId, setBuildingId] = useState<number | null>(null);
  const [build, setBuild] = useState<CohortBuild | null>(null);
  const [buildError, setBuildError] = useState("");

  const [viewName, setViewName] = useState("");
  const [views, setViews] = useState<SavedView[] | null>(null);
  const [viewsLoading, setViewsLoading] = useState(true);
  const [viewsError, setViewsError] = useState("");
  const [viewStatus, setViewStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    setBenchLoading(true);
    setBenchError("");
    const params = new URLSearchParams(scopeKey);
    void api<Record<string, BenchmarkGroup>>(
      "GET",
      scopedPath(`/api/benchmarks?group_by=${encodeURIComponent(groupBy)}`, params),
    ).then(
      (b) => {
        if (!cancelled) {
          setBench(b);
          setBenchLoading(false);
        }
      },
      (e: Error) => {
        if (!cancelled) {
          setBenchError(e.message);
          setBenchLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [groupBy, scopeKey]);

  useEffect(() => {
    let cancelled = false;
    setPatternsLoading(true);
    setPatternsError("");
    const params = new URLSearchParams(scopeKey);
    void api<PatternsResponse>("GET", scopedPath("/api/retention/patterns", params)).then(
      (p) => {
        if (!cancelled) {
          setPatterns(p);
          setPatternsLoading(false);
        }
      },
      (e: Error) => {
        if (!cancelled) {
          setPatternsError(e.message);
          setPatternsLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [scopeKey]);

  useEffect(() => {
    let cancelled = false;
    setCohortsLoading(true);
    setCohortsError("");
    void api<Cohort[]>("GET", "/api/cohorts").then(
      (list) => {
        if (!cancelled) {
          setCohorts(list);
          setCohortsLoading(false);
        }
      },
      (e: Error) => {
        if (!cancelled) {
          setCohortsError(e.message);
          setCohortsLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setViewsLoading(true);
    setViewsError("");
    void api<SavedView[]>("GET", "/api/views").then(
      (list) => {
        if (!cancelled) {
          setViews(list);
          setViewsLoading(false);
        }
      },
      (e: Error) => {
        if (!cancelled) {
          setViewsError(e.message);
          setViewsLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  /** Legacy cohort_filters_from_ui() parity: the whole active scope is copied
   *  (every filter-bar axis), with include/exclude project lists afterwards. */
  function cohortFiltersFromUi(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    const params = new URLSearchParams(scopeKey);
    for (const [k, v] of params) {
      if (!out[k]) out[k] = [];
      out[k].push(v);
    }
    const inc = splitList(includeProjects);
    const exc = splitList(excludeProjects);
    if (inc.length) out["include_projects"] = inc;
    if (exc.length) out["exclude_projects"] = exc;
    return out;
  }

  async function refreshCohorts(showId?: number): Promise<void> {
    try {
      const list = await api<Cohort[]>("GET", "/api/cohorts");
      setCohorts(list);
      setCohortsError("");
      const target = showId ?? (list.length ? list[list.length - 1].id : null);
      if (target !== null && target !== undefined) await buildCohort(target, list);
      else setBuild(null);
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : String(e));
    }
  }

  async function buildCohort(id: number, known?: Cohort[]): Promise<void> {
    setBuildingId(id);
    setBuildError("");
    try {
      const q = new URLSearchParams({ id: String(id), metric: cohortMetric }).toString();
      const r = await api<CohortBuild>("GET", `/api/cohorts/build?${q}`);
      setBuild({ ...r, cohort: r.cohort ?? known?.find((c) => c.id === id) });
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuildingId(null);
    }
  }

  async function createCohort(): Promise<void> {
    setBuildError("");
    try {
      const name = cohortName.trim() || `Cohort ${new Date().toISOString().slice(0, 10)}`;
      const saved = await api<Cohort>("POST", "/api/cohorts", {
        name,
        filters: cohortFiltersFromUi(),
      });
      setCohortName("");
      await refreshCohorts(saved.id);
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : String(e));
    }
  }

  function currentViewState(): ViewState {
    const params = new URLSearchParams(scopeKey);
    const f: Record<string, string[]> = {};
    for (const [k, v] of params) {
      if (!f[k]) f[k] = [];
      f[k].push(v);
    }
    return {
      filters: f,
      kpi: filters.kpi,
      view: "benchmark",
      benchmark: groupBy,
      benchmark_scope: "filters",
      rank_by: ["cpa", "cpm", "ctr", "vtr", "roas"].includes(filters.kpi) ? filters.kpi : "cpa",
    };
  }

  /** Legacy apply_view() parity: restore filters + KPI + tab + benchmark + rank. */
  function applyView(st: ViewState): void {
    const f = (st && st.filters) || {};
    for (const k of SCOPE_AXES) {
      let v = (f[k] || [])[0];
      if (v === null || v === undefined || v === "") v = k === "platform" ? "all" : "";
      if (k === "platform" && !["all", "meta", "tiktok"].includes(v)) v = "all";
      setFilter(k, v);
    }
    if (st.kpi && KPI_OPTIONS.includes(st.kpi)) setFilter("kpi", st.kpi);
    if (st.benchmark && GROUP_OPTIONS.includes(st.benchmark)) setGroupBy(st.benchmark);
    if (st.view && /^[a-z]+$/.test(st.view)) {
      const route = VIEW_ROUTES[st.view];
      if (route && route !== "/benchmarks") navigate(route);
    }
  }

  async function saveView(): Promise<void> {
    const name = viewName.trim();
    if (!name) {
      setViewStatus("Name the view first.");
      return;
    }
    try {
      const r = await api<{ name: string }>("POST", "/api/views", { name, state: currentViewState() });
      setViewName("");
      setViewStatus(`Saved ${r.name}.`);
      const list = await api<SavedView[]>("GET", "/api/views");
      setViews(list);
    } catch (e) {
      setViewStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteView(id: number): Promise<void> {
    try {
      await api<unknown>("POST", "/api/views/delete", { id });
      const list = await api<SavedView[]>("GET", "/api/views");
      setViews(list);
    } catch (e) {
      setViewStatus(e instanceof Error ? e.message : String(e));
    }
  }

  const benchEntries = sortEntries(Object.entries(bench ?? {}), filters.kpi);
  const patternList = (patterns && patterns.patterns) || [];

  return (
    <>
      <h1 className="page-title">Benchmarks</h1>
      <p className="page-sub">
        Saved cohorts with sample size, bands and status. Insufficient-data cohorts need more projects before
        they are reliable.
      </p>
      <div className="card">
        <label>
          Group by{" "}
          <select aria-label="Group by" value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            {GROUP_OPTIONS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>{" "}
        <button
          type="button"
          className="action"
          onClick={() => {
            setBench(null);
            setPatterns(null);
            setBenchLoading(true);
            setPatternsLoading(true);
            setBenchError("");
            setPatternsError("");
            const params = new URLSearchParams(scopeKey);
            void api<Record<string, BenchmarkGroup>>(
              "GET",
              scopedPath(`/api/benchmarks?group_by=${encodeURIComponent(groupBy)}`, params),
            ).then(
              (b) => {
                setBench(b);
                setBenchLoading(false);
              },
              (e: Error) => {
                setBenchError(e.message);
                setBenchLoading(false);
              },
            );
            void api<PatternsResponse>("GET", scopedPath("/api/retention/patterns", params)).then(
              (p) => {
                setPatterns(p);
                setPatternsLoading(false);
              },
              (e: Error) => {
                setPatternsError(e.message);
                setPatternsLoading(false);
              },
            );
          }}
        >
          Refresh
        </button>
      </div>
      <div>
        {benchLoading ? (
          <p className="muted">Loading benchmarks…</p>
        ) : benchError ? (
          <p className="muted">{benchError}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Group</th>
                <th>Ads</th>
                <th>Spend</th>
                <th>CTR</th>
                <th>CPC</th>
                <th>CPA</th>
              </tr>
            </thead>
            <tbody>
              {benchEntries.map(([k, g]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{g.n_ads}</td>
                  <td>${g.spend}</td>
                  <td>{fmt(g.ctr)}</td>
                  <td>{fmt(g.cpc, true)}</td>
                  <td>{fmt(g.cpa, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="card">
        <h3>Retention patterns</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          Where the scoped population normally loses viewers, aggregated across creatives (GET
          /api/retention/patterns follows the top filter bar).
        </div>
        {patternsLoading ? (
          <p className="muted">Loading retention patterns…</p>
        ) : patternsError ? (
          <p className="muted">{patternsError}</p>
        ) : !patternList.length ? (
          <span className="muted">
            No steep drops in scope ({patterns?.scope || "All data"}, {String(patterns?.n_creatives ?? 0)}{" "}
            creatives with curves).
          </span>
        ) : (
          <>
            <p className="muted" style={{ fontSize: 12 }}>
              Scope: {patterns?.scope || "All data"} · {String(patterns?.n_creatives)} creatives,{" "}
              {String(patterns?.n_events)} drop events.
            </p>
            <ul className="plain">
              {patternList.slice(0, 8).map((pt, i) => (
                <li key={i} style={{ fontSize: 13 }}>
                  <strong>
                    {pt.n_creatives} creative{pt.n_creatives === 1 ? "" : "s"}
                  </strong>{" "}
                  lose ~{pt.avg_drop_pts} pts (max {pt.max_drop_pts}) {patternBits(pt)} — e.g.{" "}
                  {(pt.examples || []).join(", ")}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <div className="card">
        <h3>Benchmark builder</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          Saved cohorts persist server-side (/api/cohorts) and start from the active top filter bar.
        </div>
        <div className="filter-grid">
          <label>
            Name
            <input
              type="text"
              aria-label="Cohort name"
              placeholder="e.g. Beauty TikTok lower"
              value={cohortName}
              onChange={(e) => setCohortName(e.target.value)}
            />
          </label>
          <label>
            Metric
            <select aria-label="Cohort metric" value={cohortMetric} onChange={(e) => setCohortMetric(e.target.value)}>
              {METRIC_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
          <label>
            Include projects (comma-separated)
            <input
              type="text"
              aria-label="Include projects"
              placeholder="optional"
              value={includeProjects}
              onChange={(e) => setIncludeProjects(e.target.value)}
            />
          </label>
          <label>
            Exclude projects (comma-separated)
            <input
              type="text"
              aria-label="Exclude projects"
              placeholder="optional"
              value={excludeProjects}
              onChange={(e) => setExcludeProjects(e.target.value)}
            />
          </label>
        </div>
        <div style={{ marginTop: 8 }}>
          <button type="button" className="action" onClick={() => void createCohort()}>
            Create
          </button>
        </div>
        <div style={{ marginTop: 8 }}>
          {cohortsLoading ? (
            <p className="muted">Loading saved cohorts…</p>
          ) : cohortsError ? (
            <p className="muted">{cohortsError}</p>
          ) : !cohorts || !cohorts.length ? (
            <span className="muted">No saved cohorts yet.</span>
          ) : (
            <ul className="plain">
              {cohorts.map((b) => (
                <li key={b.id}>
                  {b.name} — {JSON.stringify(b.filters || {})}{" "}
                  <button
                    type="button"
                    className="chip"
                    disabled={buildingId === b.id}
                    onClick={() => void buildCohort(b.id, cohorts)}
                  >
                    {buildingId === b.id ? "Building…" : "Build"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div style={{ marginTop: 8 }}>
          {buildError ? (
            <p className="muted">{buildError}</p>
          ) : build ? (
            <>
              <h4>
                Cohort: {build.cohort?.name ?? build.name ?? ""} ({build.metric ?? cohortMetric}) — {build.status ?? ""}
              </h4>
              <p className="muted">
                n={build.stats?.n ?? build.n_ads ?? "—"} · projects={(build.project_list || []).length} · mean=
                {fmt(build.stats?.mean_weighted)} · median={fmt(build.stats?.median)} · p25={fmt(build.stats?.p25)} ·
                p75={fmt(build.stats?.p75)}
              </p>
            </>
          ) : null}
        </div>
      </div>
      <div className="card">
        <h3>Saved views</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          Named snapshots of filters + KPI + tab + benchmark + report rank (GET/POST /api/views). Applying a view
          restores the exact analysis setup.
        </div>
        <div className="ask-row">
          <input
            type="text"
            aria-label="View name"
            placeholder="e.g. Beauty Spain TikTok"
            value={viewName}
            onChange={(e) => setViewName(e.target.value)}
          />
          <button type="button" className="action" onClick={() => void saveView()}>
            Save current view
          </button>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          {viewsLoading ? (
            <p className="muted">Loading saved views…</p>
          ) : viewsError ? (
            <span className="muted">{viewsError}</span>
          ) : !views || !views.length ? (
            <span>No saved views yet.</span>
          ) : (
            <ul className="plain">
              {views.map((v) => (
                <li key={v.id}>
                  {v.name}{" "}
                  <span className="muted" style={{ fontSize: 12 }}>
                    {JSON.stringify(v.state || {})}
                  </span>{" "}
                  <button type="button" className="chip" onClick={() => applyView(v.state || {})}>
                    Apply
                  </button>{" "}
                  <button type="button" className="chip" onClick={() => void deleteView(v.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {viewStatus}
        </div>
      </div>
    </>
  );
}
