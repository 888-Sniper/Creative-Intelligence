import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { RetentionCurve } from "@/components/charts";
import {
  CreativeThumb,
  EmptyState,
  FilterPanel,
  KpiCard,
  PageHeader,
  Panel,
  Skeleton,
  compareDisplayed,
  fmtCell,
  fmtCompact,
  formatDuration,
  kpiDisplay,
  kpiPlaceholderNote,
  platformLabel,
  titleCase,
  useCompareState,
  useScopedApi,
} from "@/components/product";

/* Creatives keeps every existing backend behavior (scoped rows, sort,
 * search, compare handoff, CSV export, per-row retention curves) and only
 * changes the presentation layer to the approved Creatives reference. */

interface CreativeMetrics {
  spend: number; impressions: number; clicks: number; conversions: number;
  revenue: number; ctr: number | null; cpc: number | null; cpa: number | null; roas: number | null;
}

interface CreativeAnnotation {
  hook_type?: string | null;
  duration_s?: number | null;
  creator_vs_branded?: string | null;
  funnel_stage?: string | null;
  objective?: string | null;
}

export interface CreativeRowDatum {
  creative_key: string;
  name?: string;
  platform?: string;
  format?: string;
  duration_s?: number | null;
  campaigns?: string[];
  metrics: CreativeMetrics;
  annotation?: CreativeAnnotation | null;
}

type SortKey = "top" | "ctr" | "roas" | "impressions";
type LengthKey = "all" | "short" | "sweet" | "long";

const SORTS: Array<SortKey> = ["top", "ctr", "roas", "impressions"];

type TFn = (key: string, vars?: Record<string, string | number>) => string;

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function secondsOf(c: CreativeRowDatum): number {
  return num(c.annotation?.duration_s ?? c.duration_s);
}

function shortHook(t: TFn, hook: string | null | undefined): string {
  const h = (hook ?? "").trim();
  if (!h) return "—";
  const direct = t(`filters.hooks.${h}`);
  if (direct !== `filters.hooks.${h}`) return direct;
  const extra = t(`creatives.shortHooks.${h}`);
  if (extra !== `creatives.shortHooks.${h}`) return extra;
  return titleCase(h);
}

/** Backend annotation codes render through the UI locale; unknown
 *  codes keep the honest Title Case form. */
function codeVia(t: TFn, group: string, code: string | null | undefined): string {
  const v = (code ?? "").trim();
  if (!v) return "—";
  const key = `${group}.${v.toLowerCase()}`;
  const hit = t(key);
  return hit === key ? titleCase(v) : hit;
}

function perfLabel(t: TFn, roas: number | null, base: number | null): { text: string; tone: string } {
  if (roas == null || base == null || !base) return { text: t("creatives.ranks.unranked"), tone: "#64748B" };
  const r = roas / base;
  if (r >= 1.2) return { text: t("creatives.ranks.top"), tone: "#0E7C5B" };
  if (r >= 0.9) return { text: t("creatives.ranks.high"), tone: "#2F6FBE" };
  if (r >= 0.65) return { text: t("creatives.ranks.good"), tone: "#7C6BD6" };
  return { text: t("creatives.ranks.needsWork"), tone: "#C2410C" };
}

function CreativeDetail({ datum }: { datum: CreativeRowDatum }) {
  const { t } = useLocale();
  const [curve, setCurve] = useState<Array<[number, number]> | null>(null);
  useEffect(() => {
    let live = true;
    api<{ points: Array<{ t: number; p: number }> }>(
      "GET", `/api/retention/curve?creative_key=${encodeURIComponent(datum.creative_key)}`,
    )
      .then((r) => live && setCurve(r.points.map((p) => [num(p.t), num(p.p)] as [number, number])))
      .catch(() => live && setCurve([]));
    return () => { live = false; };
  }, [datum.creative_key]);
  const a = datum.annotation ?? {};
  const facts: Array<[string, string]> = [
    [t("filters.hook"), shortHook(t, a.hook_type)],
    [t("creatives.detail.duration"), secondsOf(datum) ? `${secondsOf(datum)}s` : "—"],
    [t("filters.creator"), codeVia(t, "filters.creators", a.creator_vs_branded)],
    [t("filters.format"), datum.format ?? "—"],
    [t("filters.platform"), platformLabel(datum.platform)],
    [t("filters.funnel"), codeVia(t, "filters.funnels", a.funnel_stage)],
    [t("creatives.detail.objective"), codeVia(t, "filters.objectives", a.objective)],
    [t("creatives.detail.campaigns"), (datum.campaigns ?? []).join(", ") || "—"],
  ];
  return (
    <div className="detail-cols-2">
      <dl className="detail-list">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <div>
        <h4 style={{ margin: "0 0 8px", fontSize: 14 }}>{t("creatives.detail.retention")}</h4>
        {curve ? (
          curve.length ? <RetentionCurve points={curve} /> : <EmptyState verbatim text={t("creatives.noCurveFor")} />
        ) : <Skeleton height={190} />}
      </div>
    </div>
  );
}

function RetentionSpark({ creativeKey }: { creativeKey: string }) {
  const { t } = useLocale();
  const [points, setPoints] = useState<Array<[number, number]> | null>(null);
  useEffect(() => {
    let live = true;
    api<{ points: Array<{ t: number; p: number }> }>(
      "GET", `/api/retention/curve?creative_key=${encodeURIComponent(creativeKey)}`,
    )
      .then((r) => live && setPoints(r.points.map((p) => [num(p.t), num(p.p)] as [number, number])))
      .catch(() => live && setPoints([]));
    return () => { live = false; };
  }, [creativeKey]);
  if (!points) return <span className="spark" aria-label={t("creatives.loadingCurve")} />;
  if (!points.length) return <span className="muted">{t("creatives.noCurve")}</span>;
  const W = 110, H = 34;
  const d = points.map(([t, p], i) =>
    `${i ? "L" : "M"}${((t / Math.max(30, points[points.length - 1][0])) * W).toFixed(1)},${(H - (p / 100) * H).toFixed(1)}`,
  ).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("creatives.curveLabel")}>
      <path d={d} fill="none" stroke="#0A9183" strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}

export function CreativesPage() {
  const { clearFilters } = useFilters();
  const { t, tp } = useLocale();
  const [applied, setApplied] = useState(0);
  const [sort, setSort] = useState<SortKey>("top");
  const [view, setView] = useState<"list" | "grid">("list");
  const [length, setLength] = useState<LengthKey>("all");
  const [benchmark, setBenchmark] = useState("average");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [banner, setBanner] = useState("");

  const { data: compare, error: compareError } = useCompareState(applied);
  const creatives = useScopedApi<CreativeRowDatum[]>("/api/creatives", applied);
  const location = useLocation();

  /* Global header search deep-links here: ?find= opens the matching
   * creative's detail (by key or name) once rows load, and scrolls it
   * into view. Cleared by collapsing the detail. */
  useEffect(() => {
    const needle = new URLSearchParams(location.search).get("find")?.trim().toLowerCase();
    if (!needle || !creatives.data) return;
    const hit = creatives.data.find((c) =>
      c.creative_key.toLowerCase() === needle
      || (c.name ?? "").toLowerCase().includes(needle));
    if (hit) {
      setExpandedKey(hit.creative_key);
      requestAnimationFrame(() => {
        document.getElementById("creative-detail")?.scrollIntoView?.({ block: "nearest" });
      });
    }
  }, [location.search, creatives.data]);

  // Every section below reads lengthRows: the Video Length filter is a
  // page-level scope, so top cards, KPIs, baseline and learnings all
  // describe the same filtered group as the table.
  const lengthRows = useMemo(() => (creatives.data ?? []).filter((c) => {
    const s = secondsOf(c);
    if (length === "short" && !(s > 0 && s < 15)) return false;
    if (length === "sweet" && !(s >= 15 && s <= 30)) return false;
    if (length === "long" && !(s > 30)) return false;
    return true;
  }), [creatives.data, length]);

  const rows = useMemo(() => {
    const by = {
      top: (c: CreativeRowDatum) => num(c.metrics.roas),
      ctr: (c: CreativeRowDatum) => num(c.metrics.ctr),
      roas: (c: CreativeRowDatum) => num(c.metrics.roas),
      impressions: (c: CreativeRowDatum) => num(c.metrics.impressions),
    }[sort];
    return lengthRows.slice().sort((a, b) => by(b) - by(a));
  }, [lengthRows, sort]);

  const topCards = useMemo(
    () => lengthRows.slice()
      .sort((a, b) => num(b.metrics.impressions) - num(a.metrics.impressions)).slice(0, 5),
    [lengthRows],
  );

  // Pooled KPIs for the filtered group. With no length filter these
  // equal the scope totals and the compare-driven cards (with trends)
  // render instead; with a filter active the cards show pooled values
  // with no trend (no previous-period data exists for the subgroup).
  const pooled = useMemo(() => {
    const impr = lengthRows.reduce((t, c) => t + num(c.metrics.impressions), 0);
    const clicks = lengthRows.reduce((t, c) => t + num(c.metrics.clicks), 0);
    const spend = lengthRows.reduce((t, c) => t + num(c.metrics.spend), 0);
    const revenue = lengthRows.reduce((t, c) => t + num(c.metrics.revenue), 0);
    return { impr, clicks, roas: spend > 0 ? revenue / spend : null };
  }, [lengthRows]);

  const roasBase = useMemo(() => {
    const list = lengthRows.map((c) => c.metrics.roas).filter((r): r is number => r != null);
    if (!list.length) return null;
    return benchmark === "top" ? Math.max(...list) : list.reduce((t, r) => t + r, 0) / list.length;
  }, [lengthRows, benchmark]);

  // Learnings aggregate the LENGTH-FILTERED rows client-side, so they
  // describe the same group as the table and cards. Headings follow
  // the displayed numbers (ties, reversed leaders, single groups).
  const learnings = useMemo(() => {
    const out: Array<{ icon: string; title: string; body: string }> = [];
    const byHook = new Map<string, { clicks: number; impr: number }>();
    const byMode = new Map<string, { clicks: number; impr: number }>();
    for (const c of lengthRows) {
      const key = (c.annotation?.hook_type ?? "").trim() || "unannotated";
      const h = byHook.get(key) ?? { clicks: 0, impr: 0 };
      h.clicks += num(c.metrics.clicks);
      h.impr += num(c.metrics.impressions);
      byHook.set(key, h);
      const mode = (c.annotation?.creator_vs_branded ?? "").trim().toLowerCase();
      if (mode === "creator" || mode === "branded") {
        const m = byMode.get(mode) ?? { clicks: 0, impr: 0 };
        m.clicks += num(c.metrics.clicks);
        m.impr += num(c.metrics.impressions);
        byMode.set(mode, m);
      }
    }
    const ctrOf = (g: { clicks: number; impr: number }) => (g.impr > 0 ? (g.clicks / g.impr) * 100 : null);
    const hookRows = [...byHook.entries()]
      .map(([key, g]) => ({ key, ctr: ctrOf(g) }))
      .filter((r) => r.ctr != null)
      .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    if (hookRows.length > 1 && hookRows[0].ctr != null && hookRows[1].ctr != null) {
      const a = hookRows[0];
      const b = hookRows[1];
      const verdict = compareDisplayed(a.ctr ?? NaN, b.ctr ?? NaN);
      if (verdict !== "unknown") {
        const ha = shortHook(t, a.key);
        const hb = shortHook(t, b.key);
        out.push(verdict === "tie" ? {
          icon: "spark",
          title: t("creatives.learn.hookTieTitle", { a: ha, b: hb }),
          body: t("creatives.learn.hookTieBody", { a: ha, b: hb, ctr: (a.ctr ?? 0).toFixed(1) }),
        } : {
          icon: "spark",
          title: t("creatives.learn.hookLeadTitle", { a: ha }),
          body: t("creatives.learn.hookLeadBody", { a: ha, ctr: (a.ctr ?? 0).toFixed(1), bCtr: (b.ctr ?? 0).toFixed(1), b: hb }),
        });
      }
    } else if (hookRows.length === 1 && hookRows[0].ctr != null) {
      const hs = shortHook(t, hookRows[0].key);
      out.push({
        icon: "spark",
        title: t("creatives.learn.hookSnapTitle", { a: hs }),
        body: t("creatives.learn.hookSnapBody", { a: hs, ctr: (hookRows[0].ctr ?? 0).toFixed(1) }),
      });
    }
    const creatorG = byMode.get("creator");
    const brandedG = byMode.get("branded");
    const creatorCtr = creatorG ? ctrOf(creatorG) : null;
    const brandedCtr = brandedG ? ctrOf(brandedG) : null;
    if (creatorCtr != null && brandedCtr != null) {
      const verdict = compareDisplayed(creatorCtr, brandedCtr);
      if (verdict !== "unknown") {
        const lift = brandedCtr !== 0 ? ((creatorCtr - brandedCtr) / Math.abs(brandedCtr)) * 100 : null;
        const liftTxt = lift != null ? t("creatives.learn.liftDiff", { sign: lift >= 0 ? "+" : "", pct: lift.toFixed(0) }) : "";
        out.push(verdict === "tie" ? {
          icon: "users",
          title: t("creatives.learn.creatorTieTitle"),
          body: t("creatives.learn.creatorTieBody", { ctr: creatorCtr.toFixed(1) }),
        } : verdict === "lead" ? {
          icon: "users",
          title: t("creatives.learn.creatorLeadTitle"),
          body: t("creatives.learn.creatorLeadBody", { ctr: creatorCtr.toFixed(1), bCtr: brandedCtr.toFixed(1), diff: liftTxt }),
        } : {
          icon: "users",
          title: t("creatives.learn.brandedLeadTitle"),
          body: t("creatives.learn.brandedLeadBody", { ctr: brandedCtr.toFixed(1), bCtr: creatorCtr.toFixed(1), diff: liftTxt }),
        });
      }
    }
    const buckets = [
      { key: t("creatives.lengthShort"), test: (s: number) => s > 0 && s < 15 },
      { key: t("creatives.lengthSweet"), test: (s: number) => s >= 15 && s <= 30 },
      { key: t("creatives.lengthLong"), test: (s: number) => s > 30 },
    ].map((b) => ({ ...b, clicks: 0, impr: 0 }));
    for (const c of lengthRows) {
      const s = secondsOf(c);
      const b = buckets.find((x) => x.test(s));
      if (b) {
        b.clicks += num(c.metrics.clicks);
        b.impr += num(c.metrics.impressions);
      }
    }
    const ranked = buckets
      .map((b) => ({ key: b.key, ctr: b.impr ? (b.clicks / b.impr) * 100 : null }))
      .filter((b) => b.ctr != null)
      .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    if (ranked.length > 1 && ranked[0].ctr != null && ranked[1].ctr != null) {
      const verdict = compareDisplayed(ranked[0].ctr ?? NaN, ranked[1].ctr ?? NaN);
      if (verdict === "tie") {
        out.push({
          icon: "bars",
          title: t("creatives.learn.lenTieTitle", { a: ranked[0].key }),
          body: t("creatives.learn.lenTieBody", { a: ranked[0].key, ctr: (ranked[0].ctr ?? 0).toFixed(1) }),
        });
      } else if (verdict !== "unknown") {
        out.push({
          icon: "bars",
          title: t("creatives.learn.lenLeadTitle", { a: ranked[0].key }),
          body: t("creatives.learn.lenLeadBody", { a: ranked[0].key, ctr: (ranked[0].ctr ?? 0).toFixed(1), bCtr: (ranked[1].ctr ?? 0).toFixed(1), b: ranked[1].key }),
        });
      }
    } else if (ranked.length === 1 && ranked[0].ctr != null) {
      out.push({
        icon: "bars",
        title: t("creatives.learn.lenSnapTitle", { a: ranked[0].key }),
        body: t("creatives.learn.lenSnapBody", { a: ranked[0].key, ctr: (ranked[0].ctr ?? 0).toFixed(1) }),
      });
    }
    return out.slice(0, 5);
  }, [lengthRows, t]);

  const tests = useMemo(() => [
    { icon: "spark", title: t("creatives.tests.creatorTitle"), body: t("creatives.tests.creatorBody") },
    { icon: "play", title: t("creatives.tests.shorterTitle"), body: t("creatives.tests.shorterBody") },
    { icon: "users", title: t("creatives.tests.hooksTitle"), body: t("creatives.tests.hooksBody") },
  ], [t]);

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.creative_key));

  const onExport = async () => {
    const keys = rows.map((r) => r.creative_key);
    if (!keys.length) {
      setBanner(t("creatives.banner.nothingToExport"));
      return;
    }
    setExportBusy(true);
    setBanner("");
    try {
      const res = await fetch("/api/exports/creatives", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ creative_keys: keys }),
      });
      if (!res.ok) throw new Error(t("creatives.banner.exportFailed"));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "creatives.csv";
      a.click();
      URL.revokeObjectURL(url);
      setBanner(tp("creatives.banner.exported", keys.length, { count: keys.length }));
    } catch (e) {
      setBanner(e instanceof Error ? e.message : t("creatives.banner.exportFailed"));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="creatives">
      <PageHeader
        title={t("creatives.title")}
        sub={t("creatives.sub")}
        actions={(
          <>
            {/* Reset restores local view state too: a stale length/sort
              selection after reset would keep sections disagreeing. */}
            <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
              {t("filters.apply")}
            </button>
            <button type="button" className="link-teal" onClick={() => {
              clearFilters();
              setApplied((n) => n + 1);
              setSort("top");
              setView("list");
              setLength("all");
              setBenchmark("average");
              setSelected(new Set());
              setExpandedKey(null);
              setBanner("");
            }}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> {t("filters.reset")}
            </button>
          </>
        )}
      />
      <FilterPanel
        creative
        actions="none"
        trailing={(
          <>
            <div className="field">
              <label htmlFor="cr-length">{t("creatives.videoLength")}</label>
              <select id="cr-length" value={length} onChange={(e) => setLength(e.target.value as LengthKey)}>
                <option value="all">{t("creatives.lengthAll")}</option>
                <option value="short">{t("creatives.lengthShort")}</option>
                <option value="sweet">{t("creatives.lengthSweet")}</option>
                <option value="long">{t("creatives.lengthLong")}</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="cr-bench">{t("creatives.benchmarkLabel")}</label>
              <select id="cr-bench" value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
                <option value="average">{t("creatives.scopeAverage")}</option>
                <option value="top">{t("creatives.ranks.top")}</option>
              </select>
            </div>
          </>
        )}
      />
      {banner ? <p className="panel-sub" role="status" style={{ margin: "12px 0 0" }}>{banner}</p> : null}
      <div className="main-rail" style={{ marginTop: 12 }}>
        <div className="rail-stack">
          {creatives.data && (length === "all" ? compare : true) ? (
            <>
              {length !== "all" ? (
                <p className="panel-sub" style={{ margin: "0 0 8px" }}>
                  {t("creatives.showingOnly", { range: t(length === "short" ? "creatives.rangeShort" : length === "sweet" ? "creatives.rangeSweet" : "creatives.rangeLong") })}
                </p>
              ) : null}
              <div className="kpi-grid">
                <div className="kpi-card">
                  <span className="kpi-ico" style={{ background: "var(--shell-teal-soft)", color: "var(--glyph-teal)" }}>
                    <Icon name="play" size={20} />
                  </span>
                  <div className="kpi-body">
                    <div className="kpi-label">{t("creatives.totalCreatives")}</div>
                    <div className="kpi-value">{fmtCompact(rows.length)}</div>
                  </div>
                </div>
                {length === "all" && compare ? (
                  <>
                    <KpiCard label={t("dashboard.totalImpressions")} display={kpiDisplay("count", compare.metrics.impressions?.current, compare.current_n_ads === 0)}
                      icon="bars" tint="var(--shell-blue-soft)" metricLabel={t("filters.kpis.impressions")} compare={compare} />
                    <KpiCard label={t("dashboard.totalClicks")} display={kpiDisplay("count", compare.metrics.clicks?.current, compare.current_n_ads === 0)}
                      icon="click" tint="var(--shell-blue-soft)" metricLabel={t("filters.kpis.clicks")} compare={compare} />
                    <KpiCard label={t("dashboard.averageRoas")} display={kpiDisplay("mult", compare.metrics.roas?.current, compare.current_n_ads === 0)}
                      icon="users" tint="var(--shell-teal-soft)" metricLabel={t("filters.kpis.roas")} compare={compare}
                      note={kpiPlaceholderNote("mult", compare.metrics.roas?.current, compare.current_n_ads === 0)} />
                  </>
                ) : (
                  <>
                    <KpiCard label={t("dashboard.totalImpressions")} display={fmtCompact(pooled.impr)}
                      icon="bars" tint="var(--shell-blue-soft)" metricLabel={t("filters.kpis.impressions")} compare={null} />
                    <KpiCard label={t("dashboard.totalClicks")} display={fmtCompact(pooled.clicks)}
                      icon="click" tint="var(--shell-blue-soft)" metricLabel={t("filters.kpis.clicks")} compare={null} />
                    <KpiCard label={t("dashboard.averageRoas")} display={kpiDisplay("mult", pooled.roas, lengthRows.length === 0)}
                      icon="users" tint="var(--shell-teal-soft)" metricLabel={t("filters.kpis.roas")} compare={null}
                      note={kpiPlaceholderNote("mult", pooled.roas, lengthRows.length === 0)} />
                  </>
                )}
              </div>
            </>
          ) : compareError ? (
            <div className="panel"><EmptyState text={compareError} /></div>
          ) : (
            <div className="kpi-grid">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={118} />)}
            </div>
          )}
          <Panel
            title={t("creatives.topCreatives")}
            action={<Link className="link-teal" to="/creatives">{t("creatives.seeAll")}</Link>}
          >
            {creatives.data ? (
              topCards.length ? (
                <div className="creative-cards">
                  {topCards.map((c) => {
                    const s = secondsOf(c);
                    const badge = c.annotation?.creator_vs_branded
                      ? codeVia(t, "filters.creators", c.annotation.creator_vs_branded)
                      : (c.format ?? "Video").replace(/ video$/i, "");
                    return (
                      <div className="creative-card" key={c.creative_key}>
                        <div className="creative-thumb-lg">
                          <CreativeThumb seed={c.creative_key} label={c.name || c.creative_key} />
                          <span className="creative-badge">{badge}</span>
                          {s ? <span className="thumb-dur">{formatDuration(s)}</span> : null}
                          <span className="creative-scrim">{c.name || c.creative_key}</span>
                        </div>
                        <p className="creative-name">{[(c.campaigns ?? [])[0], c.format].filter(Boolean).join(" • ") || "—"}</p>
                        <div className="creative-stats">
                          <span><Icon name="play" size={12} /> {fmtCompact(num(c.metrics.impressions))}</span>
                          <span><Icon name="click" size={12} /> {fmtCell(c.metrics.ctr, (n) => `${(n * 100).toFixed(1)}%`)}</span>
                          <span><Icon name="coin" size={12} /> {fmtCell(c.metrics.roas, (n) => `${n.toFixed(1)}x`)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : <EmptyState icon="creatives" title={t("creatives.noTopTitle")} text={t("creatives.noTopBody")} />
            ) : <Skeleton height={190} />}
          </Panel>
          <Panel
            title={t("creatives.allCreatives", { count: fmtCompact(rows.length) })}
            style={{ flex: "1 0 auto" }}
            action={(
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <label htmlFor="cr-sort" className="panel-sub">{t("creatives.sortBy")}</label>
                <select id="cr-sort" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  {SORTS.map((v) => <option key={v} value={v}>{t(`creatives.sorts.${v}`)}</option>)}
                </select>
                <div role="group" aria-label={t("creatives.layoutGroup")} style={{ display: "flex", gap: 4 }}>
                  <button type="button" className="icon-btn view-btn" aria-pressed={view === "list"} aria-label={t("creatives.listView")}
                    style={{ width: 32, height: 32 }}
                    onClick={() => setView("list")}>
                    <Icon name="list" size={16} />
                  </button>
                  <button type="button" className="icon-btn view-btn" aria-pressed={view === "grid"} aria-label={t("creatives.gridView")}
                    style={{ width: 32, height: 32 }}
                    onClick={() => setView("grid")}>
                    <Icon name="grid" size={16} />
                  </button>
                </div>
                <LoadingButton type="button" className="btn-outline" loading={exportBusy} loadingLabel={t("creatives.exporting")} spinnerClass="spinner dark" disabled={exportBusy} onClick={() => void onExport()}>
                  <Icon name="download" size={15} /> {t("common.export")}
                </LoadingButton>
              </div>
            )}
          >
            {creatives.data ? (
              rows.length ? (
                view === "list" ? (
                  <div className="tbl-wrap">
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th scope="col">
                            <input type="checkbox" aria-label={t("creatives.selectAll")} checked={allChecked}
                              onChange={() => setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.creative_key)))} />
                          </th>
                          <th scope="col">{t("creatives.headers.creative")}</th>
                          <th scope="col">{t("creatives.headers.campaign")}</th>
                          <th scope="col">{t("creatives.headers.format")}</th>
                          <th scope="col">{t("creatives.headers.hook")}</th>
                          <th scope="col">{t("creatives.headers.length")}</th>
                          <th scope="col">{t("creatives.headers.platform")}</th>
                          <th scope="col" className="num">{t("filters.kpis.impressions")}</th>
                          <th scope="col" className="num">{t("filters.kpis.ctr")}</th>
                          <th scope="col" className="num">{t("filters.kpis.roas")}</th>
                          <th scope="col">{t("creatives.headers.retention")}</th>
                          <th scope="col">{t("creatives.headers.performance")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((c) => {
                          const s = secondsOf(c);
                          const perf = perfLabel(t, c.metrics.roas, roasBase);
                          return (
                            <tr key={c.creative_key}>
                              <td>
                                <input type="checkbox" aria-label={t("creatives.selectOne", { name: c.name || c.creative_key })}
                                  checked={selected.has(c.creative_key)} onChange={() => toggle(c.creative_key)} />
                              </td>
                              <td>
                                <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                  <CreativeThumb seed={c.creative_key} duration={s || null} label={c.name || c.creative_key} />
                                  <button
                                    type="button"
                                    className="link-teal cell-main"
                                    aria-expanded={expandedKey === c.creative_key}
                                    onClick={() => setExpandedKey((cur) => (cur === c.creative_key ? null : c.creative_key))}
                                  >
                                    {c.name || c.creative_key}
                                  </button>
                                </span>
                              </td>
                              <td>{(c.campaigns ?? [])[0] ?? "—"}</td>
                              <td>{c.format ?? "—"}</td>
                              <td>{shortHook(t, c.annotation?.hook_type)}</td>
                              <td>{s ? `${s}s` : "—"}</td>
                              <td>{platformLabel(c.platform)}</td>
                              <td className="num">{fmtCompact(num(c.metrics.impressions))}</td>
                              <td className="num">{fmtCell(c.metrics.ctr, (n) => `${(n * 100).toFixed(1)}%`)}</td>
                              <td className="num">{fmtCell(c.metrics.roas, (n) => `${n.toFixed(1)}x`)}</td>
                              <td><RetentionSpark creativeKey={c.creative_key} /></td>
                              <td><span className="badge-demo" style={{ color: perf.tone }}>{perf.text}</span></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="creative-cards">
                    {rows.map((c) => {
                      const s = secondsOf(c);
                      return (
                        <div className="creative-card" key={c.creative_key}>
                          <div className="creative-thumb-lg">
                            <CreativeThumb seed={c.creative_key} label={c.name || c.creative_key} />
                            {s ? <span className="thumb-dur">{formatDuration(s)}</span> : null}
                            <span className="creative-scrim">{c.name || c.creative_key}</span>
                          </div>
                          <p className="creative-name">{[(c.campaigns ?? [])[0], c.format].filter(Boolean).join(" • ") || "—"}</p>
                          <div className="creative-stats">
                            <span>{fmtCompact(num(c.metrics.impressions))}</span>
                            <span>{fmtCell(c.metrics.ctr, (n) => `${(n * 100).toFixed(1)}%`)}</span>
                            <span>{fmtCell(c.metrics.roas, (n) => `${n.toFixed(1)}x`)}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )
              ) : <EmptyState compact icon="creatives" title={t("creatives.noMatchTitle")} text={t("creatives.noMatchBody")} />
            ) : creatives.error ? (
              <EmptyState text={creatives.error} />
            ) : <Skeleton height={220} />}
          </Panel>
          {expandedKey && rows.find((r) => r.creative_key === expandedKey) ? (
            <div id="creative-detail">
              <Panel title={rows.find((r) => r.creative_key === expandedKey)?.name || expandedKey}>
                <CreativeDetail datum={rows.find((r) => r.creative_key === expandedKey) as CreativeRowDatum} />
              </Panel>
            </div>
          ) : null}
        </div>
        <div className="rail-stack">
          <Panel title={t("creatives.learnings")} action={<Link className="link-teal" to="/insights">{t("creatives.seeAll")}</Link>}>
            {creatives.data ? (
              learnings.length ? (
                <div>
                  {learnings.map((l) => (
                    <div className="insight" key={l.title}>
                      <span className="insight-ico" style={{ background: "var(--shell-teal-soft)" }}>
                        <Icon name={l.icon} size={20} />
                      </span>
                      <div>
                        <h4>{l.title}</h4>
                        <p>{l.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState compact icon="spark" title={t("creatives.noLearningsTitle")} text={t("creatives.noLearningsBody")} />
            ) : <Skeleton height={220} />}
          </Panel>
          {/* With zero creatives in the scoped group there is no
            evidence for test ideas: show an empty state, not ideas. */}
          <Panel title={t("creatives.nextTests")} action={<Link className="link-teal" to="/insights">{t("creatives.seeAll")}</Link>} style={{ flex: "1 0 auto" }}>
            {creatives.data ? (
              lengthRows.length ? (
                <div>
                  {tests.map((idea) => (
                    <div className="insight" key={idea.title}>
                      <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                        <Icon name={idea.icon} size={20} />
                      </span>
                      <div>
                        <h4>{idea.title}</h4>
                        <p>{idea.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState compact icon="target" title={t("creatives.noTestsTitle")} text={t("creatives.noTestsBody")} />
            ) : <Skeleton height={220} />}
          </Panel>
        </div>
      </div>
    </div>
  );
}
