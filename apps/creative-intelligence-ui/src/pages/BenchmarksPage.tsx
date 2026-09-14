import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, scopedPath } from "@/api/client";
import { applySavedView, VIEW_ROUTES, type SavedView } from "@/components/savedViews";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  EmptyState,
  MetaSelect,
  OverflowMenu,
  PageHeader,
  Panel,
  Skeleton,
  fmtCell,
  fmtMoney,
  fmtMult,
  fmtPct,
  platformLabel,
  useCampaignMeta,
  useScopedApi,
} from "@/components/product";

/* Benchmarks keeps every existing backend behavior (axis-grouped
 * benchmark rows, three-way compare, CSV export) and only changes the
 * presentation layer to the approved reference. "Saved Benchmarks" are
 * the backend-backed saved views, applied on click. */

type Axis = "platform" | "hook_type" | "format" | "creator_vs_branded";

const AXES: Array<Axis> = ["platform", "hook_type", "format", "creator_vs_branded"];

type TFn = (key: string, vars?: Record<string, string | number>) => string;

interface BenchRow {
  spend: number; impressions: number; clicks: number; conversions: number;
  revenue: number; ctr: number | null; cpc: number | null; cpa: number | null;
  roas: number | null; n_ads: number;
}

const BENCHMARK_AXES: ReadonlyArray<Axis> =
  ["platform", "hook_type", "format", "creator_vs_branded"];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function axisLabel(t: TFn, axis: Axis, key: string): string {
  if (axis === "platform") return platformLabel(key);
  if (axis === "creator_vs_branded") {
    const hit = t(`filters.creators.${key.toLowerCase()}`);
    return hit === `filters.creators.${key.toLowerCase()}` ? key : hit;
  }
  if (axis === "hook_type") {
    const hit = t(`filters.hooks.${key}`);
    return hit === `filters.hooks.${key}` ? key : hit;
  }
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function MiniBars({ values, format }: { values: number[]; format: (v: number) => string }) {
  const max = Math.max(1, ...values);
  const colors = ["#2F6FBE", "#0E9F6E", "#7C6BD6"];
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 96, paddingTop: 14 }}>
      {values.map((v, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--shell-navy)" }}>{format(v)}</span>
          <div style={{ width: "70%", height: `${Math.max(4, (v / max) * 72)}px`, borderRadius: "5px 5px 0 0", background: colors[i % colors.length] }} />
        </div>
      ))}
    </div>
  );
}

function BenchmarkViewSub({ view }: { view: SavedView }) {
  const { t, tp } = useLocale();
  const axes = Object.keys(view.state?.filters ?? {}).length;
  const dest = view.state?.view ? (VIEW_ROUTES[view.state.view] ?? view.state.view) : "";
  return (
    <span className="panel-sub">
      {axes ? tp("benchmarks.viewFilters", axes, { count: axes }) : t("benchmarks.savedSetup")}
      {dest ? ` · ${t("benchmarks.opensDest", { dest })}` : ""}
    </span>
  );
}

export function BenchmarksPage() {
  const { filters, setFilter, clearFilters } = useFilters();
  const { t, tp, fmtDate, fmtNum, locale } = useLocale();
  const unavailable = t("common.unavailable");
  const [axis, setAxis] = useState<Axis>("platform");
  const [applied, setApplied] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [views, setViews] = useState<SavedView[] | null>(null);

  const benchmarks = useScopedApi<Record<string, BenchRow>>(`/api/benchmarks?group_by=${axis}`, applied);
  const platCount = useScopedApi<Record<string, BenchRow>>("/api/benchmarks?group_by=platform", applied);
  const vertCount = useScopedApi<Record<string, BenchRow>>("/api/benchmarks?group_by=vertical", applied);
  const metaRows = useCampaignMeta().data?.campaigns ?? [];
  const metaClients = [...new Set(metaRows.map((r) => r.client.trim()).filter(Boolean))].sort();
  const metaVerticals = [...new Set(metaRows.flatMap((r) => r.verticals).map((s) => s.trim()).filter(Boolean))].sort();
  const metaMarkets = [...new Set(metaRows.flatMap((r) => r.markets).map((s) => s.trim()).filter(Boolean))].sort();
  const metaObjectives = [...new Set(metaRows.flatMap((r) => r.objectives).map((s) => s.trim()).filter(Boolean))].sort();

  useEffect(() => {
    let live = true;
    api<SavedView[]>("GET", "/api/views")
      .then((r) => live && setViews(Array.isArray(r) ? r : []))
      .catch(() => live && setViews([]));
    return () => { live = false; };
  }, [applied]);

  const rows = useMemo(() => {
    const list = Object.entries(benchmarks.data ?? {}).map(([key, m]) => ({ key, ...m }));
    return axis === "platform"
      ? list.sort((a, b) => axisLabel(t, axis, a.key).localeCompare(axisLabel(t, axis, b.key)))
      : list.sort((a, b) => num(b.spend) - num(a.spend));
  }, [benchmarks.data, axis, t]);

  const compared = useMemo(
    () => rows.filter((r) => selected.has(r.key)).slice(0, 3),
    [rows, selected],
  );

  /* Preselect the first two rows so Compare Benchmarks opens populated
   * with real mini charts (mirrors Compare's four-way auto-run). Users
   * can clear or change the selection; switching Group By reselects. */
  const autoSel = useRef("");
  useEffect(() => {
    if (autoSel.current !== axis && rows.length >= 2 && selected.size === 0) {
      autoSel.current = axis;
      setSelected(new Set(rows.slice(0, 2).map((r) => r.key)));
    }
  }, [axis, rows, selected.size]);

  const coverage = useMemo(() => {
    const total = Object.values(benchmarks.data ?? {}).reduce((t, g) => t + num(g.n_ads), 0);
    return {
      total,
      platforms: Object.keys(platCount.data ?? {}).length,
      verticals: Object.keys(vertCount.data ?? {}).length,
    };
  }, [benchmarks.data, platCount.data, vertCount.data]);

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else if (next.size < 3) next.add(key);
      else setStatus(t("benchmarks.maxCompare"));
      return next;
    });

  /* Shared restore over SPA navigation (a hard reload would reset
   *  filter state and silently drop the restore). Saved benchmark
   *  group-by axes apply to this page when they name one of its axes;
   *  rank_by/benchmark_scope are report-build settings with no page
   *  control and stay stored on the view. */
  const navigate = useNavigate();
  const applyView = (v: SavedView) => {
    const axis = v.state?.benchmark;
    if (axis && (BENCHMARK_AXES as ReadonlyArray<string>).includes(axis)) {
      setAxis(axis as Axis);
    }
    applySavedView(v, setFilter, navigate);
  };

  const createBenchmark = async () => {
    setSaving(true);
    setStatus("");
    try {
      const params = new URLSearchParams();
      params.set("group_by", axis);
      const data = await api<Record<string, BenchRow>>(
        "GET", scopedPath(`/api/benchmarks?${params.toString()}`, new URLSearchParams()),
      );
      const name = t("benchmarks.savedName", {
        axis: t(`benchmarks.axes.${axis}`),
        date: fmtDate(new Date().toISOString(), { month: "short", day: "numeric", year: "numeric" }),
      });
      await api("POST", "/api/views", { name, state: { filters: {}, kpi: filters.kpi, view: "benchmark" } });
      void data;
      const list = await api<SavedView[]>("GET", "/api/views");
      setViews(Array.isArray(list) ? list : []);
      setStatus(t("benchmarks.savedMsg", { name }));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : t("benchmarks.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const onExport = async () => {
    setExportBusy(true);
    setStatus("");
    try {
      const res = await fetch("/api/exports/benchmarks", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(t("benchmarks.exportFailed"));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "benchmarks.csv";
      a.click();
      URL.revokeObjectURL(url);
      setStatus(tp("benchmarks.exported", rows.length, { count: rows.length }));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : t("benchmarks.exportFailed"));
    } finally {
      setExportBusy(false);
    }
  };

  const metricVal = (r: BenchRow, m: "cpm" | "ctr" | "vtr" | "cpa" | "roas"): number | null => {
    if (m === "ctr") return r.ctr == null ? null : r.ctr * 100;
    if (m === "roas") return r.roas;
    if (m === "cpa") return r.cpa;
    if (m === "cpm") return r.impressions ? (r.spend / r.impressions) * 1000 : null;
    return null;
  };

  return (
    <>
      <PageHeader
        title={t("benchmarks.title")}
        sub={t("benchmarks.sub")}
        actions={(
          <LoadingButton type="button" className="btn-primary" loading={saving} loadingLabel={t("common.saving")} disabled={saving} onClick={() => void createBenchmark()}>
            <Icon name="plus" size={16} /> {t("benchmarks.create")}
          </LoadingButton>
        )}
      />
      <section className="panel" aria-label={t("benchmarks.filtersLabel")}>
        <div className="filter-grid fg-6">
          <MetaSelect id="b-client" label={t("filters.client")} allLabel={t("filters.allClients")}
            values={metaClients} value={filters.client}
            onPick={(v) => setFilter("client", v)} />
          <MetaSelect id="b-vertical" label={t("filters.vertical")} allLabel={t("filters.allVerticals")}
            values={metaVerticals} value={filters.vertical}
            onPick={(v) => setFilter("vertical", v)} />
          <div className="field">
            <label htmlFor="b-platform">{t("filters.platform")}</label>
            <select id="b-platform" aria-label={t("filters.platform")} value={filters.platform === "all" ? "" : filters.platform} onChange={(e) => setFilter("platform", e.target.value)}>
              <option value="">{t("filters.allPlatforms")}</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <MetaSelect id="b-market" label={t("filters.market")} allLabel={t("filters.allMarkets")}
            values={metaMarkets} value={filters.market}
            onPick={(v) => setFilter("market", v)} />
          <MetaSelect id="b-objective" label={t("filters.objective")} allLabel={t("filters.allObjectives")}
            values={metaObjectives} value={filters.objective}
            onPick={(v) => setFilter("objective", v)} />
          <div className="field">
            <label htmlFor="b-funnel">{t("filters.funnel")}</label>
            <select id="b-funnel" aria-label={t("filters.funnel")} value={filters.funnel === "all" ? "" : filters.funnel} onChange={(e) => setFilter("funnel", e.target.value)}>
              <option value="">{t("filters.allStages")}</option>
              <option value="upper">{t("filters.funnels.upper")}</option>
              <option value="mid">{t("filters.funnels.mid")}</option>
              <option value="lower">{t("filters.funnels.lower")}</option>
            </select>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
                {t("filters.apply")}
              </button>
              <button type="button" className="link-teal" onClick={clearFilters}
                style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Icon name="reset" size={15} /> {t("filters.reset")}
              </button>
            </div>
          </div>
        </div>
      </section>
      {status ? <p className="panel-sub" role="status" style={{ margin: "8px 0 0" }}>{status}</p> : null}
      <div className="main-rail">
        <div className="rail-stack">
          <Panel title={t("benchmarks.savedTitle")} sub={t("benchmarks.savedSub")}
            action={<Link className="link-teal" to="/insights">{t("common.viewAll")}</Link>}>
            {views === null ? <Skeleton height={90} /> : (
              views.length ? (
                <div className="cards-4">
                  {views.slice(0, 4).map((v) => (
                    <button key={v.id} type="button" className="cmp-card" onClick={() => applyView(v)}
                      style={{ textAlign: "left", cursor: "pointer", padding: 12 }}>
                      <span className="insight-ico" style={{ background: "var(--shell-teal-soft)", marginBottom: 6 }}>
                        <Icon name="bookmark" size={18} />
                      </span>
                      <strong style={{ display: "block", fontSize: 13 }}>{v.name}</strong>
                      <BenchmarkViewSub view={v} />
                    </button>
                  ))}
                </div>
              ) : <EmptyState compact icon="bookmark" title={t("benchmarks.noSavedTitle")} text={t("benchmarks.noSavedBody")} />
            )}
          </Panel>
          {/* Both left panels share leftover column height so the
            column bottom edge meets Learn More (right rail-stack is
            grid-stretched to the same height; no fixed heights). */}
          <Panel
            title={t("benchmarks.resultsTitle")}
            sub={t("benchmarks.resultsSub")}
            style={{ flex: "1 0 auto" }}
            headClassName="bench-head"
            action={(
              <>
                <OverflowMenu
                  className="hide-desktop"
                  label={t("benchmarks.resultsActions")}
                  items={[{ label: exportBusy ? t("campaigns.exporting") : t("common.export"), icon: "download", disabled: exportBusy, onSelect: () => void onExport() }]}
                />
                <div className="panel-controls bench-controls">
                  <label htmlFor="b-axis" className="panel-sub" style={{ margin: 0 }}>{t("benchmarks.groupBy")}</label>
                  <select id="b-axis" aria-label={t("benchmarks.groupBy")} value={axis}
                    onChange={(e) => { setAxis(e.target.value as Axis); setSelected(new Set()); }}
                    style={{ background: "var(--shell-card)", border: "1px solid var(--shell-line)", borderRadius: 8, padding: "7px 26px 7px 10px", fontSize: 12.5, color: "var(--shell-navy)", fontFamily: "inherit" }}>
                    {AXES.map((a) => <option key={a} value={a}>{t(`benchmarks.axes.${a}`)}</option>)}
                  </select>
                  <LoadingButton type="button" className="btn-outline hide-mobile" loading={exportBusy} loadingLabel={t("campaigns.exporting")} spinnerClass="spinner dark" disabled={exportBusy} onClick={() => void onExport()}>
                    <Icon name="download" size={15} /> {t("common.export")}
                  </LoadingButton>
                </div>
              </>
            )}
          >
            {benchmarks.data ? (
              rows.length ? (
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th scope="col"><input type="checkbox" aria-label={t("benchmarks.selectAll")}
                          checked={rows.length > 0 && rows.every((r) => selected.has(r.key))}
                          onChange={() => setSelected(rows.every((r) => selected.has(r.key)) ? new Set() : new Set(rows.map((r) => r.key)))} /></th>
                        <th scope="col">{t("benchmarks.headers.name")}</th>
                        <th scope="col">{t("benchmarks.headers.coverage")}</th>
                        <th scope="col">{t("benchmarks.headers.platform")}</th>
                        <th scope="col" className="num">{t("filters.kpis.cpm")}</th>
                        <th scope="col" className="num">{t("filters.kpis.ctr")}</th>
                        <th scope="col" className="num">{t("filters.kpis.cpa")}</th>
                        <th scope="col" className="num">{t("filters.kpis.roas")}</th>
                        <th scope="col" className="num">{t("benchmarks.headers.records")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.key}>
                          <td>
                            <input type="checkbox" aria-label={t("benchmarks.selectOne", { name: axisLabel(t, axis, r.key) })}
                              checked={selected.has(r.key)} onChange={() => toggle(r.key)} />
                          </td>
                          <td><span className="cell-main">{axisLabel(t, axis, r.key)}</span></td>
                          <td>{axis === "platform" ? t("filters.allVerticals") : t("filters.allPlatforms")}</td>
                          <td>{axis === "platform" ? axisLabel(t, axis, r.key) : t("filters.allPlatforms")}</td>
                          <td className="num">{fmtCell(metricVal(r, "cpm"), (n) => fmtMoney(n as number, locale), unavailable)}</td>
                          <td className="num">{fmtCell(metricVal(r, "ctr"), (n) => fmtPct(n as number, 1, locale), unavailable)}</td>
                          <td className="num">{fmtCell(metricVal(r, "cpa"), (n) => fmtMoney(n as number, locale), unavailable)}</td>
                          <td className="num">{fmtCell(r.roas, (n) => fmtMult(n, locale), unavailable)}</td>
                          <td className="num">{fmtNum(num(r.n_ads))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState compact icon="bars" title={t("benchmarks.noScopeTitle")} text={t("benchmarks.noScopeBody")} />
            ) : benchmarks.error ? (
              <EmptyState text={benchmarks.error} />
            ) : <Skeleton height={200} />}
          </Panel>
          <Panel title={t("benchmarks.compareTitle")} sub={t("benchmarks.compareSub")}
            style={{ flex: "1 0 auto" }}
            action={selected.size ? (
              <button type="button" className="link-teal" onClick={() => setSelected(new Set())}>{t("benchmarks.clearAll")}</button>
            ) : undefined}>
            {compared.length >= 2 ? (
              <div className="cards-4">
                {(["cpm", "ctr", "cpa", "roas"] as const).map((m) => (
                  <div key={m} className="cmp-card" style={{ padding: 12 }}>
                    <strong style={{ fontSize: 13 }}>{m.toUpperCase()}</strong>
                    <MiniBars
                      values={compared.map((r) => metricVal(r, m) ?? 0)}
                      format={(v) => (m === "ctr" ? fmtPct(v, 1, locale) : m === "roas" ? fmtMult(v, locale) : fmtMoney(v, locale))}
                    />
                    <div className="legend" style={{ justifyContent: "flex-start" }}>
                      {compared.map((r) => <span key={r.key}>{axisLabel(t, axis, r.key)}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            ) : <EmptyState compact icon="compare" title={t("benchmarks.nothingTitle")} text={t("benchmarks.nothingBody")} />}
          </Panel>
        </div>
        <div className="rail-stack">
          <Panel title={t("benchmarks.insightsTitle")} sub={t("benchmarks.insightsSub")}>
            <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 10 }}>
              <span className="insight-ico" style={{ background: "var(--shell-teal-soft)" }}>
                <Icon name="bars" size={22} />
              </span>
              <div>
                <p className="panel-sub" style={{ margin: 0 }}>{t("benchmarks.coverageLabel")}</p>
                <strong style={{ fontSize: 26 }}>{fmtNum(coverage.total)}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>{t("benchmarks.totalRecords")}</p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <div className="cmp-card" style={{ flex: 1, textAlign: "center" }}>
                <strong>{coverage.platforms}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>{tp("benchmarks.platform", coverage.platforms)}</p>
              </div>
              <div className="cmp-card" style={{ flex: 1, textAlign: "center" }}>
                <strong>{metaRows.length}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>{tp("benchmarks.campaign", metaRows.length)}</p>
              </div>
              <div className="cmp-card" style={{ flex: 1, textAlign: "center" }}>
                <strong>{coverage.verticals}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>{tp("benchmarks.vertical", coverage.verticals)}</p>
              </div>
            </div>
          </Panel>
          <Panel title={t("benchmarks.contextTitle")}>
            <p className="panel-sub">
              {t("benchmarks.contextBody")}
            </p>
          </Panel>
          <Panel title={t("benchmarks.tipsTitle")}>
            <ul className="rec-list" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4, fontSize: 13 }}>
              <li>{t("benchmarks.tips.filters")}</li>
              <li>{t("benchmarks.tips.platforms")}</li>
              <li>{t("benchmarks.tips.verticals")}</li>
              <li>{t("benchmarks.tips.save")}</li>
            </ul>
          </Panel>
          <Panel title={t("benchmarks.learnTitle")}>
            <p className="panel-sub" style={{ margin: "0 0 8px" }}>
              {t("benchmarks.learnBody")}
            </p>
            <div style={{ display: "flex", gap: 8 }}>
              <Link className="btn-soft" to="/analyst">{t("benchmarks.openAnalyst")}</Link>
              <Link className="btn-soft" to="/reports">{t("benchmarks.openReports")}</Link>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
