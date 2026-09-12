import { useEffect, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { EmptyState, Panel, Skeleton } from "@/components/product";
import { LoadingButton } from "@/components/LoadingButton";

/* Advanced data tooling relocated here from the old Benchmarks surface:
 * retention-pattern mining and the saved-cohort benchmark builder. All
 * backend contracts (/api/retention/patterns, /api/cohorts,
 * /api/cohorts/build) are unchanged; only the presentation moved into
 * Settings so product pages stay executive-clean. */

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

const METRIC_OPTIONS = ["cpa", "cpm", "ctr", "vtr", "roas"];

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
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

export function RetentionPatterns() {
  const { scope } = useFilters();
  const scopeKey = scope.toString();
  const [patterns, setPatterns] = useState<PatternsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const params = new URLSearchParams(scopeKey);
    void api<PatternsResponse>("GET", scopedPath("/api/retention/patterns", params)).then(
      (p) => {
        if (!cancelled) {
          setPatterns(p);
          setLoading(false);
        }
      },
      (e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [scopeKey]);

  const patternList = patterns?.patterns ?? [];
  return (
    <Panel
      title="Retention Patterns"
      sub="Where the scoped population normally loses viewers, aggregated across creatives."
    >
      {loading ? (
        <p className="muted">Loading Retention Patterns…</p>
      ) : error ? (
        <EmptyState text={error} />
      ) : !patternList.length ? (
        <EmptyState
          text={`No steep drops in scope (${patterns?.scope || "All data"}, ${String(patterns?.n_creatives ?? 0)} creatives with curves).`}
        />
      ) : (
        <>
          <p className="panel-sub">
            Scope: {patterns?.scope || "All data"} · {String(patterns?.n_creatives)} Creatives,{" "}
            {String(patterns?.n_events)} Drop Events.
          </p>
          <ul className="rec-list">
            {patternList.slice(0, 8).map((pt, i) => (
              <li key={i}>
                <strong>
                  {pt.n_creatives} creative{pt.n_creatives === 1 ? "" : "s"}
                </strong>{" "}
                Lose ~{pt.avg_drop_pts} Pts (Max {pt.max_drop_pts}) {patternBits(pt)} — E.g.{" "}
                {(pt.examples || []).join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

export function CohortBuilder() {
  const { scope } = useFilters();
  const scopeKey = scope.toString();
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

  const stats = build?.stats;
  return (
    <Panel
      title="Benchmark Builder"
      sub="Saved cohorts persist server-side and start from the active filter scope."
    >
      <div className="filter-grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
        <div className="field">
          <label htmlFor="dt-cohort-name">Name</label>
          <input
            id="dt-cohort-name"
            type="text"
            aria-label="Cohort Name"
            placeholder="e.g. Beauty TikTok lower"
            value={cohortName}
            onChange={(e) => setCohortName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="dt-cohort-metric">Metric</label>
          <select id="dt-cohort-metric" aria-label="Cohort Metric" value={cohortMetric} onChange={(e) => setCohortMetric(e.target.value)}>
            {METRIC_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dt-include">Include Projects (Comma-Separated)</label>
          <input
            id="dt-include"
            type="text"
            aria-label="Include Projects"
            placeholder="optional"
            value={includeProjects}
            onChange={(e) => setIncludeProjects(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="dt-exclude">Exclude Projects (Comma-Separated)</label>
          <input
            id="dt-exclude"
            type="text"
            aria-label="Exclude Projects"
            placeholder="optional"
            value={excludeProjects}
            onChange={(e) => setExcludeProjects(e.target.value)}
          />
        </div>
      </div>
      <div className="filter-actions">
        <button type="button" className="btn-primary" onClick={() => void createCohort()}>
          Create
        </button>
      </div>
      <div style={{ marginTop: 8 }}>
        {cohortsLoading ? (
          <p className="muted">Loading Saved Cohorts…</p>
        ) : cohortsError ? (
          <EmptyState text={cohortsError} />
        ) : !(cohorts ?? []).length ? (
          <EmptyState text="No Saved Cohorts Yet." />
        ) : (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">Cohort</th>
                  <th scope="col">Filters</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {(cohorts ?? []).map((c) => (
                  <tr key={c.id}>
                    <td><span className="cell-main">{c.name}</span></td>
                    <td>{Object.keys(c.filters ?? {}).length} axes</td>
                    <td>
                      <LoadingButton type="button" className="btn-outline" loading={buildingId === c.id} loadingLabel="Building…" spinnerClass="spinner dark"
                        disabled={buildingId === c.id}
                        onClick={() => void buildCohort(c.id, cohorts ?? [])}>
                        Build
                      </LoadingButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {buildError ? <EmptyState text={buildError} /> : null}
        {build ? (
          <p className="panel-sub">
            Cohort: {build.cohort?.name ?? build.name ?? "—"} · Metric {build.metric ?? cohortMetric} ·{" "}
            n={String(stats?.n ?? build.n_ads ?? "—")} · Mean {String(stats?.mean_weighted ?? "—")} · Median{" "}
            {String(stats?.median ?? "—")} · P25 {String(stats?.p25 ?? "—")} · P75 {String(stats?.p75 ?? "—")} —{" "}
            {build.status ?? "ok"}
          </p>
        ) : null}
      </div>
    </Panel>
  );
}

export function DataToolsSkeleton() {
  return <Skeleton height={140} />;
}
