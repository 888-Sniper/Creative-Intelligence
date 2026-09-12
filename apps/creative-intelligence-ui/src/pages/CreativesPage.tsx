import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
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
  fmtCompact,
  formatDuration,
  platformLabel,
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

const SORTS: Array<{ value: SortKey; label: string }> = [
  { value: "top", label: "Top Performing" },
  { value: "ctr", label: "Highest CTR" },
  { value: "roas", label: "Highest ROAS" },
  { value: "impressions", label: "Most Impressions" },
];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function secondsOf(c: CreativeRowDatum): number {
  return num(c.annotation?.duration_s ?? c.duration_s);
}

function shortHook(hook: string | null | undefined): string {
  const h = (hook ?? "").trim();
  if (!h) return "—";
  const map: Record<string, string> = {
    problem_solution: "Problem/Solution",
    hook_statement: "Hook Statement",
    product_demo: "Product Demo",
  };
  return map[h] ?? h.split("_").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

function perfLabel(roas: number | null, base: number | null): { text: string; tone: string } {
  if (roas == null || base == null || !base) return { text: "Unranked", tone: "#64748B" };
  const r = roas / base;
  if (r >= 1.2) return { text: "Top Performer", tone: "#0E7C5B" };
  if (r >= 0.9) return { text: "High Performer", tone: "#2F6FBE" };
  if (r >= 0.65) return { text: "Good Performer", tone: "#7C6BD6" };
  return { text: "Needs Work", tone: "#C2410C" };
}

function CreativeDetail({ datum }: { datum: CreativeRowDatum }) {
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
    ["Hook Type", shortHook(a.hook_type)],
    ["Duration", secondsOf(datum) ? `${secondsOf(datum)}s` : "—"],
    ["Creator vs Branded", a.creator_vs_branded ?? "—"],
    ["Format", datum.format ?? "—"],
    ["Platform", platformLabel(datum.platform)],
    ["Funnel Stage", a.funnel_stage ?? "—"],
    ["Objective", a.objective ?? "—"],
    ["Campaigns", (datum.campaigns ?? []).join(", ") || "—"],
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
        <h4 style={{ margin: "0 0 8px", fontSize: 14 }}>Audience Retention</h4>
        {curve ? (
          curve.length ? <RetentionCurve points={curve} /> : <EmptyState text="No retention curve for this creative." />
        ) : <Skeleton height={190} />}
      </div>
    </div>
  );
}

function RetentionSpark({ creativeKey }: { creativeKey: string }) {
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
  if (!points) return <span className="spark" aria-label="Loading retention curve" />;
  if (!points.length) return <span className="muted">No Curve</span>;
  const W = 110, H = 34;
  const d = points.map(([t, p], i) =>
    `${i ? "L" : "M"}${((t / Math.max(30, points[points.length - 1][0])) * W).toFixed(1)},${(H - (p / 100) * H).toFixed(1)}`,
  ).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Retention curve">
      <path d={d} fill="none" stroke="#0E7C8C" strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}

export function CreativesPage() {
  const { clearFilters } = useFilters();
  const [applied, setApplied] = useState(0);
  const [sort, setSort] = useState<SortKey>("top");
  const [view, setView] = useState<"list" | "grid">("list");
  const [length, setLength] = useState<LengthKey>("all");
  const [benchmark, setBenchmark] = useState("Scope Average");
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
    return benchmark === "Top Performer" ? Math.max(...list) : list.reduce((t, r) => t + r, 0) / list.length;
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
        out.push(verdict === "tie" ? {
          icon: "spark",
          title: `${shortHook(a.key)} and ${shortHook(b.key)} Tie on CTR`,
          body: `${shortHook(a.key)} and ${shortHook(b.key)} openings both average ${(a.ctr ?? 0).toFixed(1)}% CTR across the current scope.`,
        } : {
          icon: "spark",
          title: `${shortHook(a.key)} Hooks Lead CTR`,
          body: `${shortHook(a.key)} openings average ${(a.ctr ?? 0).toFixed(1)}% CTR versus ${(b.ctr ?? 0).toFixed(1)}% for ${shortHook(b.key)} across the current scope.`,
        });
      }
    } else if (hookRows.length === 1 && hookRows[0].ctr != null) {
      out.push({
        icon: "spark",
        title: `${shortHook(hookRows[0].key)} Openings Snapshot`,
        body: `${shortHook(hookRows[0].key)} openings average ${(hookRows[0].ctr ?? 0).toFixed(1)}% CTR across the current scope.`,
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
        const liftTxt = lift != null ? ` (${lift >= 0 ? "+" : ""}${lift.toFixed(0)}%)` : "";
        out.push(verdict === "tie" ? {
          icon: "users",
          title: "Creator and Branded Hooks Tie on CTR",
          body: `Creatives with creator intros and branded openings both average ${creatorCtr.toFixed(1)}% CTR across the current scope.`,
        } : verdict === "lead" ? {
          icon: "users",
          title: "Creator-Led Hooks Perform Best",
          body: `Creatives with creator intros see ${creatorCtr.toFixed(1)}% CTR versus ${brandedCtr.toFixed(1)}% for branded content${liftTxt}.`,
        } : {
          icon: "users",
          title: "Branded Hooks Perform Best",
          body: `Creatives with branded openings see ${brandedCtr.toFixed(1)}% CTR versus ${creatorCtr.toFixed(1)}% for creator intros${liftTxt}.`,
        });
      }
    }
    const buckets = [
      { key: "Under 15s", test: (s: number) => s > 0 && s < 15 },
      { key: "15–30s", test: (s: number) => s >= 15 && s <= 30 },
      { key: "Over 30s", test: (s: number) => s > 30 },
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
          title: `${ranked[0].key} Shares the Length Lead`,
          body: `Videos in the ${ranked[0].key} bucket match the best band at ${(ranked[0].ctr ?? 0).toFixed(1)}% CTR in the current scope.`,
        });
      } else if (verdict !== "unknown") {
        out.push({
          icon: "bars",
          title: `${ranked[0].key} Videos Lead on CTR`,
          body: `Videos in the ${ranked[0].key} bucket average ${(ranked[0].ctr ?? 0).toFixed(1)}% CTR versus ${(ranked[1].ctr ?? 0).toFixed(1)}% for ${ranked[1].key} in the current scope.`,
        });
      }
    } else if (ranked.length === 1 && ranked[0].ctr != null) {
      out.push({
        icon: "bars",
        title: `${ranked[0].key} Videos Snapshot`,
        body: `Videos in the ${ranked[0].key} bucket average ${(ranked[0].ctr ?? 0).toFixed(1)}% CTR in the current scope.`,
      });
    }
    return out.slice(0, 5);
  }, [lengthRows]);

  const tests = useMemo(() => [
    { icon: "spark", title: "Test Creator vs. Branded Intros", body: "Compare performance of creator-led vs. branded openings." },
    { icon: "play", title: "Try Shorter Video Lengths", body: "Test 15s vs. 30s videos to validate impact on CTR and ROAS." },
    { icon: "users", title: "Experiment With New Hook Types", body: "Test problem/solution vs. testimonial hooks for top campaigns." },
  ], []);

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
      setBanner("Nothing To Export For The Current Filters.");
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
      if (!res.ok) throw new Error("Export Failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "creatives.csv";
      a.click();
      URL.revokeObjectURL(url);
      setBanner(`Exported ${keys.length} Creative${keys.length === 1 ? "" : "s"}.`);
    } catch (e) {
      setBanner(e instanceof Error ? e.message : "Export Failed");
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="creatives">
      <PageHeader
        title="Creatives"
        sub="Explore top performing creatives, analyze what works, and get AI-powered recommendations."
        actions={(
          <>
            {/* Reset restores local view state too: a stale length/sort
              selection after reset would keep sections disagreeing. */}
            <button type="button" className="link-teal" onClick={() => {
              clearFilters();
              setApplied((n) => n + 1);
              setSort("top");
              setView("list");
              setLength("all");
              setBenchmark("Scope Average");
              setSelected(new Set());
              setExpandedKey(null);
              setBanner("");
            }}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> Reset Filters
            </button>
            <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
              Apply Filters
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
              <label htmlFor="cr-length">Video Length</label>
              <select id="cr-length" value={length} onChange={(e) => setLength(e.target.value as LengthKey)}>
                <option value="all">All Lengths</option>
                <option value="short">Under 15s</option>
                <option value="sweet">15–30s</option>
                <option value="long">Over 30s</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="cr-bench">Benchmark</label>
              <select id="cr-bench" value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
                <option>Scope Average</option>
                <option>Top Performer</option>
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
                  {`Showing ${length === "short" ? "under-15s" : length === "sweet" ? "15–30s" : "over-30s"} creatives only.`}
                </p>
              ) : null}
              <div className="kpi-grid">
                <div className="kpi-card">
                  <span className="kpi-ico" style={{ background: "#DFF5F1", color: "#009485" }}>
                    <Icon name="play" size={20} />
                  </span>
                  <div className="kpi-body">
                    <div className="kpi-label">Total Creatives</div>
                    <div className="kpi-value">{fmtCompact(rows.length)}</div>
                  </div>
                </div>
                {length === "all" && compare ? (
                  <>
                    <KpiCard label="Total Impressions" display={fmtCompact(num(compare.metrics.impressions?.current))}
                      icon="bars" tint="#E7F1FB" metricLabel="Impressions" compare={compare} />
                    <KpiCard label="Total Clicks" display={fmtCompact(num(compare.metrics.clicks?.current))}
                      icon="click" tint="#E7F1FB" metricLabel="Clicks" compare={compare} />
                    <KpiCard label="Average ROAS" display={`${num(compare.metrics.roas?.current).toFixed(1)}x`}
                      icon="users" tint="#DFF5F1" metricLabel="ROAS" compare={compare} />
                  </>
                ) : (
                  <>
                    <KpiCard label="Total Impressions" display={fmtCompact(pooled.impr)}
                      icon="bars" tint="#E7F1FB" metricLabel="Impressions" compare={null} />
                    <KpiCard label="Total Clicks" display={fmtCompact(pooled.clicks)}
                      icon="click" tint="#E7F1FB" metricLabel="Clicks" compare={null} />
                    <KpiCard label="Average ROAS" display={pooled.roas == null ? "—" : `${pooled.roas.toFixed(1)}x`}
                      icon="users" tint="#DFF5F1" metricLabel="ROAS" compare={null} />
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
            title="Top Performing Creatives"
            action={<Link className="link-teal" to="/creatives">See All</Link>}
          >
            {creatives.data ? (
              topCards.length ? (
                <div className="creative-cards">
                  {topCards.map((c) => {
                    const s = secondsOf(c);
                    const badge = c.annotation?.creator_vs_branded
                      ? c.annotation.creator_vs_branded[0].toUpperCase() + c.annotation.creator_vs_branded.slice(1)
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
                          <span><Icon name="click" size={12} /> {c.metrics.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</span>
                          <span><Icon name="coin" size={12} /> {c.metrics.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : <EmptyState text="No creatives in the current scope." />
            ) : <Skeleton height={190} />}
          </Panel>
          <Panel
            title={`All Creatives (${fmtCompact(rows.length)})`}
            action={(
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <label htmlFor="cr-sort" className="panel-sub">Sort By</label>
                <select id="cr-sort" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
                <div role="group" aria-label="Table layout" style={{ display: "flex", gap: 4 }}>
                  <button type="button" className="icon-btn" aria-pressed={view === "list"} aria-label="List view"
                    style={{ width: 32, height: 32, background: view === "list" ? "#E7F1FB" : undefined }}
                    onClick={() => setView("list")}>
                    <Icon name="list" size={16} />
                  </button>
                  <button type="button" className="icon-btn" aria-pressed={view === "grid"} aria-label="Grid view"
                    style={{ width: 32, height: 32, background: view === "grid" ? "#E7F1FB" : undefined }}
                    onClick={() => setView("grid")}>
                    <Icon name="grid" size={16} />
                  </button>
                </div>
                <LoadingButton type="button" className="btn-outline" loading={exportBusy} loadingLabel="Exporting…" spinnerClass="spinner dark" disabled={exportBusy} onClick={() => void onExport()}>
                  <Icon name="download" size={15} /> Export
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
                            <input type="checkbox" aria-label="Select all creatives" checked={allChecked}
                              onChange={() => setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.creative_key)))} />
                          </th>
                          <th scope="col">Creative</th>
                          <th scope="col">Campaign</th>
                          <th scope="col">Format</th>
                          <th scope="col">Hook Type</th>
                          <th scope="col">Length</th>
                          <th scope="col">Platform</th>
                          <th scope="col" className="num">Impressions</th>
                          <th scope="col" className="num">CTR</th>
                          <th scope="col" className="num">ROAS</th>
                          <th scope="col">Retention</th>
                          <th scope="col">Performance</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((c) => {
                          const s = secondsOf(c);
                          const perf = perfLabel(c.metrics.roas, roasBase);
                          return (
                            <tr key={c.creative_key}>
                              <td>
                                <input type="checkbox" aria-label={`Select ${c.name || c.creative_key}`}
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
                              <td>{shortHook(c.annotation?.hook_type)}</td>
                              <td>{s ? `${s}s` : "—"}</td>
                              <td>{platformLabel(c.platform)}</td>
                              <td className="num">{fmtCompact(num(c.metrics.impressions))}</td>
                              <td className="num">{c.metrics.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</td>
                              <td className="num">{c.metrics.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</td>
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
                            <span>{c.metrics.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</span>
                            <span>{c.metrics.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )
              ) : <EmptyState text="No creatives match the current filters." />
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
          <Panel title="Top Learnings" action={<Link className="link-teal" to="/insights">See All</Link>}>
            {creatives.data ? (
              learnings.length ? (
                <div>
                  {learnings.map((l) => (
                    <div className="insight" key={l.title}>
                      <span className="insight-ico" style={{ background: "#DFF5F1" }}>
                        <Icon name={l.icon} size={20} />
                      </span>
                      <div>
                        <h4>{l.title}</h4>
                        <p>{l.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="Not enough data for learnings yet." />
            ) : <Skeleton height={220} />}
          </Panel>
          {/* With zero creatives in the scoped group there is no
            evidence for test ideas: show an empty state, not ideas. */}
          <Panel title="Recommended Tests" action={<Link className="link-teal" to="/insights">See All</Link>}>
            {creatives.data ? (
              lengthRows.length ? (
                <div>
                  {tests.map((t) => (
                    <div className="insight" key={t.title}>
                      <span className="insight-ico" style={{ background: "#E7F1FB" }}>
                        <Icon name={t.icon} size={20} />
                      </span>
                      <div>
                        <h4>{t.title}</h4>
                        <p>{t.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="Not enough data for recommendations yet." />
            ) : <Skeleton height={220} />}
          </Panel>
        </div>
      </div>
    </div>
  );
}
