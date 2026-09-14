import { useEffect, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
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

type TFn = (key: string, vars?: Record<string, string | number>) => string;

function patternBits(t: TFn, p: RetentionPattern): string {
  const bits: (string | null)[] = [
    p.slot ? t("dataTools.bits.during", { slot: p.slot }) : t("dataTools.bits.anySegment"),
    p.product_demo ? t("dataTools.bits.demoOn") : null,
    p.brand_visible ? t("dataTools.bits.brandVisible") : null,
    p.cta_present ? t("dataTools.bits.ctaPresent") : null,
    p.voiceover ? t("dataTools.bits.voiceover") : null,
  ];
  return bits.filter((b): b is string => b !== null).join(" · ");
}

function splitList(raw: string): string[] {
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

export function RetentionPatterns() {
  const { scope } = useFilters();
  const { t, tp, fmtNum } = useLocale();
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
      title={t("dataTools.retentionTitle")}
      sub={t("dataTools.retentionSub")}
    >
      {loading ? (
        <DataToolsSkeleton />
      ) : error ? (
        <EmptyState text={error} />
      ) : !patternList.length ? (
        <EmptyState
          text={t("dataTools.retentionEmpty", {
            scope: patterns?.scope || t("dataTools.allData"),
            n: patterns?.n_creatives ?? 0,
          })}
        />
      ) : (
        <>
          <p className="panel-sub">
            {t("dataTools.retentionScope", {
              scope: patterns?.scope || t("dataTools.allData"),
              n: patterns?.n_creatives ?? 0,
              e: patterns?.n_events ?? 0,
            })}
          </p>
          <ul className="rec-list">
            {patternList.slice(0, 8).map((pt, i) => (
              <li key={i}>
                <strong>
                  {pt.n_creatives} {tp("dataTools.creative", pt.n_creatives, { count: pt.n_creatives })}
                </strong>{" "}
                {t("dataTools.loseLine", {
                  avg: fmtNum(pt.avg_drop_pts, { maximumFractionDigits: 2 }),
                  max: fmtNum(pt.max_drop_pts, { maximumFractionDigits: 2 }),
                })}{" "}
                {patternBits(t, pt)} — {t("dataTools.egPrefix")}{" "}
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
  const { t, tp, fmtNum, fmtDate } = useLocale();
  const { me } = useAuth();
  const canDelete = me?.is_admin === true;
  const scopeKey = scope.toString();
  const [cohortName, setCohortName] = useState("");
  const [cohortMetric, setCohortMetric] = useState("cpa");
  const [includeProjects, setIncludeProjects] = useState("");
  const [excludeProjects, setExcludeProjects] = useState("");
  const [cohorts, setCohorts] = useState<Cohort[] | null>(null);
  const [cohortsLoading, setCohortsLoading] = useState(true);
  const [cohortsError, setCohortsError] = useState("");
  const [buildingId, setBuildingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [build, setBuild] = useState<CohortBuild | null>(null);
  const [builtId, setBuiltId] = useState<number | null>(null);
  const [buildError, setBuildError] = useState("");
  const [opStatus, setOpStatus] = useState("");

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
      setBuiltId(id);
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuildingId(null);
    }
  }

  async function deleteCohort(id: number, name: string): Promise<void> {
    // Destructive and admin-only: confirm first, then DELETE. The
    // row is removed server-side so it stays deleted after refresh;
    // a displayed result for this cohort clears with it.
    if (typeof window.confirm === "function"
        && !window.confirm(t("dataTools.deleteConfirm", { name }))) {
      return;
    }
    setDeletingId(id);
    setOpStatus("");
    setBuildError("");
    try {
      await api("DELETE", `/api/cohorts/${id}`);
      const list = await api<Cohort[]>("GET", "/api/cohorts");
      setCohorts(list);
      setCohortsError("");
      if (builtId === id) {
        setBuild(null);
        setBuiltId(null);
      }
      setOpStatus(t("dataTools.deleted", { name }));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      // 403 (or any explicit forbidden) means the role changed
      // mid-session: say so plainly instead of a generic failure.
      setBuildError(/forbidden|administrator|403/i.test(message)
        ? t("dataTools.deleteForbidden")
        : (message || t("dataTools.deleteFailed")));
    } finally {
      setDeletingId(null);
    }
  }

  async function createCohort(): Promise<void> {
    setBuildError("");
    try {
      const name = cohortName.trim() || t("dataTools.defaultName", {
        date: fmtDate(new Date().toISOString(), { month: "short", day: "numeric", year: "numeric" }),
      });
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
  // Backend facts render through the UI locale; missing stays an em dash.
  const fmtStat = (v: number | null | undefined): string =>
    v == null || !Number.isFinite(v) ? "—" : fmtNum(v, { maximumFractionDigits: 2 });
  return (
    <Panel
      title={t("dataTools.cohortTitle")}
      sub={t("dataTools.cohortSub")}
    >
      <div className="filter-grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
        <div className="field">
          <label htmlFor="dt-cohort-name">{t("dataTools.nameLabel")}</label>
          <input
            id="dt-cohort-name"
            type="text"
            aria-label={t("dataTools.nameAria")}
            placeholder={t("dataTools.namePh")}
            value={cohortName}
            onChange={(e) => setCohortName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="dt-cohort-metric">{t("dataTools.metricLabel")}</label>
          <select id="dt-cohort-metric" aria-label={t("dataTools.metricAria")} value={cohortMetric} onChange={(e) => setCohortMetric(e.target.value)}>
            {METRIC_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dt-include">{t("dataTools.includeLabel")}</label>
          <input
            id="dt-include"
            type="text"
            aria-label={t("dataTools.includeAria")}
            placeholder={t("dataTools.optionalPh")}
            value={includeProjects}
            onChange={(e) => setIncludeProjects(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="dt-exclude">{t("dataTools.excludeLabel")}</label>
          <input
            id="dt-exclude"
            type="text"
            aria-label={t("dataTools.excludeAria")}
            placeholder={t("dataTools.optionalPh")}
            value={excludeProjects}
            onChange={(e) => setExcludeProjects(e.target.value)}
          />
        </div>
      </div>
      <div className="filter-actions">
        <button type="button" className="btn-primary" onClick={() => void createCohort()}>
          {t("dataTools.create")}
        </button>
      </div>
      <div style={{ marginTop: 8 }}>
        {cohortsLoading ? (
          <DataToolsSkeleton />
        ) : cohortsError ? (
          <EmptyState text={cohortsError} />
        ) : !(cohorts ?? []).length ? (
          <EmptyState text={t("dataTools.noCohorts")} />
        ) : (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">{t("dataTools.cohortCol")}</th>
                  <th scope="col">{t("dataTools.filtersCol")}</th>
                  <th scope="col"><span className="sr-only">{t("dataTools.actionsCol")}</span></th>
                </tr>
              </thead>
              <tbody>
                {(cohorts ?? []).map((c) => (
                  <tr key={c.id}>
                    <td><span className="cell-main">{c.name}</span></td>
                    <td>{tp("dataTools.axes", Object.keys(c.filters ?? {}).length, { count: Object.keys(c.filters ?? {}).length })}</td>
                    <td>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <LoadingButton type="button" className="btn-outline" loading={buildingId === c.id} loadingLabel={t("dataTools.building")} spinnerClass="spinner dark"
                          disabled={buildingId === c.id || deletingId === c.id}
                          onClick={() => void buildCohort(c.id, cohorts ?? [])}>
                          {t("dataTools.build")}
                        </LoadingButton>
                        {canDelete ? (
                          <LoadingButton type="button" className="btn-outline" loading={deletingId === c.id} loadingLabel={t("dataTools.deleting")} spinnerClass="spinner dark"
                            disabled={buildingId === c.id || deletingId === c.id}
                            onClick={() => void deleteCohort(c.id, c.name)}
                            aria-label={t("dataTools.deleteLabel", { name: c.name })}>
                            {t("dataTools.delete")}
                          </LoadingButton>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {opStatus ? <p className="panel-sub" role="status" style={{ margin: "8px 0 0" }}>{opStatus}</p> : null}
        {buildError ? <EmptyState text={buildError} /> : null}
        {build ? (
          <p className="panel-sub">
            {t("dataTools.buildSummary", {
              name: build.cohort?.name ?? build.name ?? "—",
              metric: (build.metric ?? cohortMetric).toUpperCase(),
              n: fmtStat(stats?.n ?? build.n_ads),
              mean: fmtStat(stats?.mean_weighted),
              median: fmtStat(stats?.median),
              p25: fmtStat(stats?.p25),
              p75: fmtStat(stats?.p75),
              status: build.status ?? t("dataTools.buildOk"),
            })}
          </p>
        ) : null}
      </div>
    </Panel>
  );
}

export function DataToolsSkeleton() {
  return <Skeleton height={140} />;
}
