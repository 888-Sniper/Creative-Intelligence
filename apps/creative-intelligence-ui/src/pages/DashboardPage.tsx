import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { useFilters } from "@/state/FilterContext";
import { GroupBars, RetentionCurve, TrendChart } from "@/components/charts";
import { Icon } from "@/components/icons";
import {
  CreativeThumb,
  EmptyState,
  FilterPanel,
  KpiCard,
  PageHeader,
  Panel,
  InsightList,
  Skeleton,
  compareDisplayed,
  fmtCompact,
  fmtMoney,
  fmtMult,
  platformLabel,
  useCompareState,
  useDaily,
  useScopedApi,
  type DayPoint,
} from "@/components/product";

interface CampaignTotals {
  spend?: number | null;
  impressions?: number | null;
  clicks?: number | null;
  conversions?: number | null;
  revenue?: number | null;
  ctr?: number | null;
  cpa?: number | null;
  roas?: number | null;
}

interface BenchGroup {
  spend: number;
  impressions: number;
  clicks: number;
  conversions: number;
  revenue: number;
  ctr: number | null;
  cpc: number | null;
  cpa: number | null;
  roas: number | null;
}

interface CreativeMetrics {
  spend?: number | null;
  impressions?: number | null;
  clicks?: number | null;
  conversions?: number | null;
  ctr?: number | null;
  roas?: number | null;
}

interface CreativeRow {
  creative_key: string;
  name?: string;
  platform?: string;
  duration_s?: number | null;
  campaigns?: string[];
  format?: string;
  metrics?: CreativeMetrics;
  annotation?: {
    duration_s?: number | null;
    hook_type?: string | null;
    creator_vs_branded?: string | null;
  } | null;
}

interface CurveResponse {
  points: Array<{ t: number; p: number }>;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function num(value: unknown): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function shortDay(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`;
}

function downsample(points: DayPoint[], max = 16): DayPoint[] {
  if (points.length <= max) return points;
  const size = Math.ceil(points.length / max);
  const out: DayPoint[] = [];
  for (let i = 0; i < points.length; i += size) {
    const chunk = points.slice(i, i + size);
    out.push({
      date: chunk[0].date,
      impressions: chunk.reduce((t, p) => t + num(p.impressions), 0),
      clicks: chunk.reduce((t, p) => t + num(p.clicks), 0),
      spend: chunk.reduce((t, p) => t + num(p.spend), 0),
      conversions: chunk.reduce((t, p) => t + num(p.conversions), 0),
      revenue: chunk.reduce((t, p) => t + num(p.revenue), 0),
    });
  }
  return out;
}

function titleCase(value: string): string {
  return value.split("_").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

function percentDiff(current: number, base: number): number | null {
  if (!Number.isFinite(current) || !Number.isFinite(base) || base === 0) return null;
  return ((current - base) / Math.abs(base)) * 100;
}

const TREND_METRICS = [
  { value: "impressions", label: "Impressions" },
  { value: "clicks", label: "Clicks" },
  { value: "spend", label: "Spend" },
  { value: "conversions", label: "Conversions" },
] as const;

type TrendMetric = (typeof TREND_METRICS)[number]["value"];

const BENCH_METRICS = [
  { value: "ctr", label: "CTR" },
  { value: "roas", label: "ROAS" },
  { value: "cpa", label: "CPA" },
  { value: "cpc", label: "CPC" },
] as const;

type BenchMetric = (typeof BENCH_METRICS)[number]["value"];

function benchValue(group: BenchGroup, metric: BenchMetric): number | null {
  if (metric === "ctr") return group.ctr == null ? null : group.ctr * 100;
  if (metric === "roas") return group.roas;
  if (metric === "cpa") return group.cpa;
  return group.cpc;
}

function baselineValue(groups: BenchGroup[], metric: BenchMetric): number | null {
  const spend = groups.reduce((t, g) => t + num(g.spend), 0);
  const impr = groups.reduce((t, g) => t + num(g.impressions), 0);
  const clicks = groups.reduce((t, g) => t + num(g.clicks), 0);
  const conv = groups.reduce((t, g) => t + num(g.conversions), 0);
  const revenue = groups.reduce((t, g) => t + num(g.revenue), 0);
  if (metric === "ctr") return impr ? (clicks / impr) * 100 : null;
  if (metric === "roas") return spend ? revenue / spend : null;
  if (metric === "cpa") return conv ? spend / conv : null;
  return clicks ? spend / clicks : null;
}

function formatBench(metric: BenchMetric, value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (metric === "ctr") return `${value.toFixed(1)}%`;
  if (metric === "roas") return `${value.toFixed(1)}x`;
  return `$${value.toFixed(2)}`;
}

export function DashboardPage() {
  const { me } = useAuth();
  const { clearFilters, filters, setFilter } = useFilters();
  const [applied, setApplied] = useState(0);
  const [leftMetric, setLeftMetric] = useState<TrendMetric>("impressions");
  const [rightMetric, setRightMetric] = useState<TrendMetric>("clicks");
  const [benchMetric, setBenchMetric] = useState<BenchMetric>("ctr");
  const [baseline, setBaseline] = useState("Scope Average");
  const [tab, setTab] = useState("retention");
  const [curve, setCurve] = useState<Array<[number, number]> | null>(null);
  const [curveError, setCurveError] = useState("");

  const { data: compare, error: compareError } = useCompareState(applied);
  const daily = useDaily(30, applied);
  const [rangeBooted, setRangeBooted] = useState(false);
  const campaigns = useScopedApi<Record<string, CampaignTotals>>("/api/campaigns", applied);
  const creatives = useScopedApi<CreativeRow[]>("/api/creatives", applied);
  const platforms = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=platform", applied);
  const hooks = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=hook_type", applied);
  const modes = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=creator_vs_branded", applied);

  // Default reporting period: the trailing 30 days present in the data.
  // A blank scope makes the backend compare the whole dataset extent
  // against an empty previous window (honest "none", no percentages),
  // so the dashboard opens on a range with a real previous equivalent.
  // User-chosen dates always win; this runs once per mount.
  useEffect(() => {
    if (rangeBooted) return;
    if (filters.date || filters.date_from || filters.date_to) {
      setRangeBooted(true);
      return;
    }
    if (!daily || daily.length < 2) return;
    const dates = daily.map((p) => p.date).sort();
    setFilter("date_from", dates[0]);
    setFilter("date_to", dates[dates.length - 1]);
    setRangeBooted(true);
  }, [daily, filters.date, filters.date_from, filters.date_to, rangeBooted, setFilter]);

  const hour = new Date().getHours();
  const daypart = hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening";
  const firstName = me?.employee?.first_name?.trim() || "there";

  const trend = useMemo(() => downsample(daily ?? []), [daily]);
  const leftLabel = TREND_METRICS.find((m) => m.value === leftMetric)?.label ?? "Impressions";
  const rightLabel = TREND_METRICS.find((m) => m.value === rightMetric)?.label ?? "Clicks";
  const trendSeries = [
    { label: leftLabel, color: "#00B3A0", soft: "#DDF3F0", points: trend.map((p) => num(p[leftMetric])) },
    { label: rightLabel, color: "#1D3A8F", soft: "#E4EAF7", points: trend.map((p) => num(p[rightMetric])), axis: "right" as const },
  ];

  const platformGroups = useMemo(() => {
    const rows = Object.entries(platforms.data ?? {}).map(([key, g]) => ({ key, ...g }));
    return rows
      .map((g) => ({ ...g, value: benchValue(g, benchMetric) }))
      .filter((g) => g.value != null)
      .sort((a, b) => num((b as { impressions: number }).impressions) - num((a as { impressions: number }).impressions))
      .slice(0, 5);
  }, [platforms.data, benchMetric]);
  const platformBaseline = useMemo(
    () => baselineValue(Object.values(platforms.data ?? {}), benchMetric),
    [platforms.data, benchMetric],
  );

  const topCreatives = useMemo(() => {
    const rows = creatives.data ?? [];
    return rows.slice().sort((a, b) => num(b.metrics?.impressions) - num(a.metrics?.impressions)).slice(0, 4);
  }, [creatives.data]);

  useEffect(() => {
    const key = topCreatives[0]?.creative_key;
    if (!key) {
      setCurve(null);
      return;
    }
    let live = true;
    setCurve(null);
    setCurveError("");
    api<CurveResponse>("GET", `/api/retention/curve?creative_key=${encodeURIComponent(key)}`)
      .then((r) => {
        if (live) setCurve(r.points.map((p) => [num(p.t), num(p.p)]));
      })
      .catch((e) => {
        if (live) setCurveError(e instanceof Error ? e.message : String(e));
      });
    return () => { live = false; };
  }, [topCreatives]);

  const hookRows = useMemo(() => {
    const rows = Object.entries(hooks.data ?? {}).map(([key, g]) => ({
      key,
      ctr: g.ctr == null ? null : g.ctr * 100,
    })).filter((r) => r.ctr != null).sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    return rows;
  }, [hooks.data]);

  const modeRows = useMemo(() => {
    const rows = Object.entries(modes.data ?? {}).map(([key, g]) => ({
      key,
      ctr: g.ctr == null ? null : g.ctr * 100,
      roas: g.roas,
    })).filter((r) => r.ctr != null);
    return rows;
  }, [modes.data]);

  const durationRows = useMemo(() => {
    const buckets = [
      { key: "Under 15s", test: (s: number) => s < 15 },
      { key: "15–30s", test: (s: number) => s >= 15 && s <= 30 },
      { key: "Over 30s", test: (s: number) => s > 30 },
    ].map((b) => ({ ...b, clicks: 0, impr: 0 }));
    for (const c of creatives.data ?? []) {
      const seconds = num(c.annotation?.duration_s ?? c.duration_s);
      if (!seconds) continue;
      const bucket = buckets.find((b) => b.test(seconds));
      if (bucket) {
        bucket.clicks += num(c.metrics?.clicks);
        bucket.impr += num(c.metrics?.impressions);
      }
    }
    return buckets.map((b) => ({ key: b.key, ctr: b.impr ? (b.clicks / b.impr) * 100 : null }));
  }, [creatives.data]);

  const hookBaseline = useMemo(
    () => baselineValue(Object.values(hooks.data ?? {}), "ctr"),
    [hooks.data],
  );
  const hookCompare = useMemo(
    () => hookRows.slice(0, 5).map((r) => ({ label: titleCase(r.key), yours: r.ctr ?? 0, bench: hookBaseline ?? 0 })),
    [hookRows, hookBaseline],
  );
  const lengthCompare = useMemo(
    () => durationRows.filter((r) => r.ctr != null).map((r) => ({ label: r.key, yours: r.ctr ?? 0, bench: r.ctr ?? 0 })),
    [durationRows],
  );
  const formatCompare = useMemo(() => {
    const agg = new Map<string, { clicks: number; impr: number }>();
    for (const c of creatives.data ?? []) {
      const key = (c.format || c.annotation?.hook_type ? (c.format || "Unformatted") : "Unformatted").trim() || "Unformatted";
      const entry = agg.get(key) ?? { clicks: 0, impr: 0 };
      entry.clicks += num(c.metrics?.clicks);
      entry.impr += num(c.metrics?.impressions);
      agg.set(key, entry);
    }
    const scopeCtr = (() => {
      let clicks = 0;
      let impr = 0;
      for (const v of agg.values()) {
        clicks += v.clicks;
        impr += v.impr;
      }
      return impr ? (clicks / impr) * 100 : 0;
    })();
    return [...agg.entries()]
      .map(([label, v]) => ({ label: label.replace(/ video$/i, ""), yours: v.impr ? (v.clicks / v.impr) * 100 : 0, bench: scopeCtr }))
      .sort((a, b) => b.yours - a.yours)
      .slice(0, 5);
  }, [creatives.data]);

  const rail = useMemo(() => {
    const items: Array<{ icon: string; tint: string; title: string; body: string; action: string; href: string }> = [];
    if (hookRows.length > 1 && hookRows[0].ctr != null && hookRows[1].ctr != null) {
      const a = hookRows[0];
      const b = hookRows[1];
      const verdict = compareDisplayed(a.ctr ?? NaN, b.ctr ?? NaN);
      if (verdict !== "unknown") {
        const diff = percentDiff(a.ctr ?? 0, b.ctr ?? 0);
        const tied = verdict === "tie";
        items.push({
          icon: "trend",
          tint: "#DFF5F1",
          title: tied
            ? `${titleCase(a.key)} and ${titleCase(b.key)} Tie on CTR`
            : `${titleCase(a.key)} Hooks Drive Higher CTR`,
          body: tied
            ? `${titleCase(a.key)} and ${titleCase(b.key)} openings both average ${(a.ctr ?? 0).toFixed(1)}% CTR across the current scope.`
            : `${titleCase(a.key)} openings average ${(a.ctr ?? 0).toFixed(1)}% CTR${diff != null ? `, ${diff >= 0 ? "+" : ""}${diff.toFixed(0)}% versus ${titleCase(b.key)}` : ""} across the current scope.`,
          action: "View Creatives",
          href: "/creatives",
        });
      }
    }
    const creator = modeRows.find((r) => r.key === "creator");
    const branded = modeRows.find((r) => r.key === "branded");
    if (creator?.ctr != null && branded?.ctr != null) {
      const verdict = compareDisplayed(creator.ctr, branded.ctr);
      if (verdict !== "unknown") {
        const top = verdict === "trail" ? branded : creator;
        const bottom = top === creator ? branded : creator;
        const topName = top === creator ? "Creator" : "Branded";
        const bottomName = bottom === creator ? "creator" : "branded";
        const topCtr = top.ctr ?? 0;
        const bottomCtr = bottom.ctr ?? 0;
        const diff = percentDiff(topCtr, bottomCtr);
        items.push({
          icon: "users",
          tint: "#DFF5F1",
          title: verdict === "tie"
            ? "Creator and Branded Content Tie on CTR"
            : `${topName} Content Outperforms ${topName === "Creator" ? "Branded" : "Creator"} Content`,
          body: verdict === "tie"
            ? `Creator and branded creatives both average ${topCtr.toFixed(1)}% CTR across the current scope.`
            : `${topName} creatives average ${topCtr.toFixed(1)}% CTR versus ${bottomCtr.toFixed(1)}% for ${bottomName} creatives${diff != null ? ` (${diff >= 0 ? "+" : ""}${diff.toFixed(0)}%)` : ""} across the current scope.`,
          action: "Explore Creatives",
          href: "/creatives",
        });
      }
    }
    const groups = Object.entries(platforms.data ?? {}).map(([key, g]) => ({ key, roas: g.roas ?? null }));
    const tiktok = groups.find((g) => g.key === "tiktok");
    const meta = groups.find((g) => g.key === "meta");
    if (tiktok?.roas != null && meta?.roas != null) {
      const verdict = compareDisplayed(tiktok.roas, meta.roas);
      if (verdict !== "unknown") {
        if (verdict === "tie") {
          items.push({
            icon: "tiktok",
            tint: "#E7F1FB",
            title: "TikTok and Meta Tie on ROAS",
            body: `TikTok and Meta both average ${tiktok.roas.toFixed(1)}x ROAS across the current scope.`,
            action: "View Campaigns",
            href: "/campaigns",
          });
        } else {
          const leader = verdict === "lead" ? tiktok : meta;
          const trailer = leader === tiktok ? meta : tiktok;
          const diff = percentDiff(leader.roas ?? 0, trailer.roas ?? 0);
          items.push({
            icon: "tiktok",
            tint: "#E7F1FB",
            title: `${platformLabel(leader.key)} Leads On ROAS`,
            body: `${platformLabel(leader.key)} averages ${(leader.roas ?? 0).toFixed(1)}x ROAS versus ${(trailer.roas ?? 0).toFixed(1)}x on ${platformLabel(trailer.key)}${diff != null ? ` (${diff >= 0 ? "+" : ""}${diff.toFixed(0)}%)` : ""} across the current scope.`,
            action: "View Campaigns",
            href: "/campaigns",
          });
        }
      }
    }
    const sweet = durationRows.find((r) => r.key === "15–30s");
    const others = durationRows.filter((r) => r.key !== "15–30s" && r.ctr != null);
    if (sweet?.ctr != null && others.length) {
      const base = Math.max(...others.map((r) => r.ctr ?? 0));
      const verdict = compareDisplayed(sweet.ctr, base);
      // A trailing band gets no recommendation card: a false "best"
      // is worse than a missing one.
      if (verdict === "lead") {
        const diff = percentDiff(sweet.ctr, base);
        items.push({
          icon: "play",
          tint: "#E7F1FB",
          title: "15–30 Second Videos Hold Attention Best",
          body: `Videos between 15–30 seconds average ${sweet.ctr.toFixed(1)}% CTR${diff != null ? `, ${diff >= 0 ? "+" : ""}${diff.toFixed(0)}% above the next length bucket` : ""} across the current scope.`,
          action: "See Recommendations",
          href: "/insights",
        });
      } else if (verdict === "tie") {
        items.push({
          icon: "play",
          tint: "#E7F1FB",
          title: "15–30 Second Videos Share the Lead on Attention",
          body: `Videos between 15–30 seconds match the best length bucket at ${sweet.ctr.toFixed(1)}% CTR across the current scope.`,
          action: "See Recommendations",
          href: "/insights",
        });
      }
    }
    return items.slice(0, 4);
  }, [hookRows, modeRows, platforms.data, durationRows]);

  const nearThree = useMemo(() => {
    if (!curve?.length) return null;
    return curve.slice().sort((a, b) => Math.abs(a[0] - 3) - Math.abs(b[0] - 3))[0];
  }, [curve]);

  const kpiConfigs = [
    { label: "Total Impressions", metric: "impressions", display: compare ? fmtCompact(num(compare.metrics.impressions?.current)) : "", icon: "users", tint: "#DFF5F1", color: "#009485" },
    { label: "Total Clicks", metric: "clicks", display: compare ? fmtCompact(num(compare.metrics.clicks?.current)) : "", icon: "click", tint: "#E7F1FB", color: "#2F6FBE" },
    { label: "Total Spend", metric: "spend", display: compare ? fmtMoney(num(compare.metrics.spend?.current)) : "", icon: "coin", tint: "#E4F4ED", color: "#0E7C5B" },
    { label: "Average ROAS", metric: "roas", display: compare ? fmtMult(num(compare.metrics.roas?.current)) : "", icon: "bars", tint: "#E7F1FB", color: "#2F6FBE" },
  ];

  return (
    <div className="dashboard">
      <PageHeader
        title={`Good ${daypart}, ${firstName}`}
        sub="Your creative performance at a glance."
        actions={(
          <>
            <button type="button" className="link-teal" onClick={clearFilters}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> Reset Filters
            </button>
            <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
              Apply Filters
            </button>
          </>
        )}
      />
      {/* Team stays in the global scope but hides on Dashboard only.
        A hidden-yet-active scope is never silent: the chip below names
        it and clears it deliberately. */}
      <FilterPanel actions="none" showTeam={false} />
      {filters.team ? (
        <div className="chip-row" style={{ margin: "10px 0 0" }}>
          <span className="chip-static">Team scope active: {filters.team}</span>
          <button type="button" className="link-teal" onClick={() => setFilter("team", "")}>
            Clear team filter
          </button>
        </div>
      ) : null}
      {/* Approved composition: the Insights rail spans the full right
        side from the KPI row down (KPIs | Insights, Charts | Insights,
        Top Creatives + Retention | Insights). */}
      <div className="main-rail">
        <div className="rail-stack">
      {compare ? (
        <div className="kpi-grid">
          {kpiConfigs.map((k) => (
            <div key={k.metric} style={{ color: k.color }}>
              <KpiCard
                label={k.label}
                display={k.display}
                icon={k.icon}
                tint={k.tint}
                metricLabel={k.metric === "roas" ? "ROAS" : titleCase(k.metric)}
                compare={compare}
              />
            </div>
          ))}
        </div>
      ) : compareError ? (
        <div className="panel"><EmptyState text={compareError} /></div>
      ) : (
        <div className="kpi-grid">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={118} />)}
        </div>
      )}
      <div className="cols-2 dash-charts">
        <Panel
          title="Campaign Performance Trends"
          action={(
            <div className="mini-selects">
              <select aria-label="Left trend metric" value={leftMetric} onChange={(e) => setLeftMetric(e.target.value as TrendMetric)}>
                {TREND_METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
              <span className="mini-vs">vs.</span>
              <select aria-label="Right trend metric" value={rightMetric} onChange={(e) => setRightMetric(e.target.value as TrendMetric)}>
                {TREND_METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>
          )}
        >
          {daily ? (
            <>
              <TrendChart series={trendSeries} labels={trend.map((p) => shortDay(p.date))} height={205} />
              <div className="legend">
                {trendSeries.map((s) => (
                  <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
                ))}
              </div>
            </>
          ) : <Skeleton height={205} />}
        </Panel>
        <Panel
          title="Benchmark Comparison"
          action={(
            <div className="mini-selects">
              <select aria-label="Benchmark metric" value={benchMetric} onChange={(e) => setBenchMetric(e.target.value as BenchMetric)}>
                {BENCH_METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
              <span className="mini-vs">vs.</span>
              <select aria-label="Benchmark baseline" value={baseline} onChange={(e) => setBaseline(e.target.value)}>
                <option value="Scope Average">Scope Average</option>
                <option value="Top Performer">Top Performer</option>
              </select>
            </div>
          )}
        >
          {platforms.data ? (
            platformGroups.length ? (
              <>
                <GroupBars
                  height={205}
                  groups={platformGroups.map((g) => ({
                    label: platformLabel(g.key),
                    yours: g.value ?? 0,
                    bench: baseline === "Top Performer"
                      ? Math.max(...platformGroups.map((x) => x.value ?? 0))
                      : platformBaseline ?? 0,
                  }))}
                  format={(v) => formatBench(benchMetric, v)}
                />
                <div className="legend">
                  <span><i style={{ background: "#0E7C8C", borderRadius: 2 }} />Your Campaigns</span>
                  <span><i style={{ background: "#CBD8E6", borderRadius: 2 }} />{baseline === "Top Performer" ? "Top Performer" : "Scope Average"}</span>
                </div>
              </>
            ) : <EmptyState text="No platform benchmarks in the current scope." />
          ) : <Skeleton height={205} />}
        </Panel>
      </div>
      {/* Approved composition: Top Creatives and Retention sit side by
        side beneath the charts (collapses to stacked under 1180px). */}
      <div className="cols-2 dash-lower">
          <Panel
            title="Top Performing Creatives"
            action={<Link className="link-teal" to="/creatives">See All</Link>}
          >
            {creatives.data ? (
              topCreatives.length ? (
                <div className="tbl-wrap">
                  <table className="tbl dash-table">
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">Creative</th>
                        <th scope="col">Campaign</th>
                        <th scope="col" className="num">Impressions</th>
                        <th scope="col" className="num">CTR</th>
                        <th scope="col" className="num">CVR</th>
                        <th scope="col" className="num">ROAS</th>
                        <th scope="col"><span className="sr-only">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {topCreatives.map((c, i) => {
                        const ctr = c.metrics?.ctr == null ? null : c.metrics.ctr * 100;
                        const clicks = num(c.metrics?.clicks);
                        const conv = num(c.metrics?.conversions);
                        const cvr = clicks ? (conv / clicks) * 100 : null;
                        const roas = c.metrics?.roas ?? null;
                        return (
                          <tr key={c.creative_key}>
                            <td className="idx">{i + 1}</td>
                            <td>
                              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <CreativeThumb
                                  seed={c.creative_key}
                                  duration={c.annotation?.duration_s ?? c.duration_s}
                                  label={c.name || c.creative_key}
                                />
                                <span className="cell-main" title={c.name || c.creative_key}>{c.name || c.creative_key}</span>
                              </span>
                            </td>
                            <td title={c.campaigns?.[0] ?? undefined}>{c.campaigns?.[0] ?? "—"}</td>
                            <td className="num">{fmtCompact(num(c.metrics?.impressions))}</td>
                            <td className="num">{ctr == null ? "—" : `${ctr.toFixed(1)}%`}</td>
                            <td className="num">{cvr == null ? "—" : `${cvr.toFixed(1)}%`}</td>
                            <td className="num">{roas == null ? "—" : `${roas.toFixed(1)}x`}</td>
                            <td>
                              <Link className="icon-btn" to="/creatives" aria-label={`Open ${c.name || c.creative_key} in Creatives`}>
                                <Icon name="dots" size={18} />
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState text="No creatives in the current scope." />
            ) : <Skeleton height={220} />}
          </Panel>
          <Panel title="Retention & Hook Insights">
            <div className="tabs retention-tabs" role="tablist" aria-label="Retention and hook insights">
              {[
                { value: "retention", label: "Audience Retention" },
                { value: "hooks", label: "Hook Analysis" },
                { value: "length", label: "Video Length" },
                { value: "format", label: "Format Comparison" },
              ].map((t) => (
                <button key={t.value} type="button" role="tab" aria-selected={tab === t.value} onClick={() => setTab(t.value)}>
                  {t.label}
                </button>
              ))}
            </div>
            {tab === "retention" ? (
              <div className="retention-split">
                <div>
                  {curve ? (
                    <RetentionCurve
                      points={curve}
                      callout={nearThree ? `${Math.round(nearThree[1])}% at 3s` : undefined}
                      height={170}
                    />
                  ) : curveError ? (
                    <EmptyState text={curveError} />
                  ) : <Skeleton height={170} />}
                </div>
                <div className="takeaways">
                  <h5><Icon name="check" size={15} /> Key Takeaways</h5>
                  <ul>
                    {nearThree ? (
                      <li><Icon name="check" size={13} /><span>{Math.round(nearThree[1])}% of viewers are still watching at 3 seconds for {topCreatives[0]?.name || "the top creative"}.</span></li>
                    ) : null}
                    {hookRows[0]?.ctr != null ? (
                      <li><Icon name="check" size={13} /><span>{titleCase(hookRows[0].key)} hooks lead the current scope at {(hookRows[0].ctr ?? 0).toFixed(1)}% CTR.</span></li>
                    ) : null}
                    {durationRows.find((r) => r.key === "15–30s")?.ctr != null ? (
                      <li><Icon name="check" size={13} /><span>15–30 second creatives average {(durationRows.find((r) => r.key === "15–30s")?.ctr ?? 0).toFixed(1)}% CTR in the current scope.</span></li>
                    ) : null}
                  </ul>
                </div>
              </div>
            ) : null}
            {tab === "hooks" ? (
              hookCompare.length ? (
                <GroupBars height={190} groups={hookCompare} format={(v) => `${v.toFixed(1)}%`} />
              ) : <EmptyState text="No hook benchmarks in the current scope." />
            ) : null}
            {tab === "length" ? (
              lengthCompare.length ? (
                <GroupBars height={190} groups={lengthCompare} format={(v) => `${v.toFixed(1)}%`} />
              ) : <EmptyState text="No duration data in the current scope." />
            ) : null}
            {tab === "format" ? (
              formatCompare.length ? (
                <GroupBars height={190} groups={formatCompare} format={(v) => `${v.toFixed(1)}%`} />
              ) : <EmptyState text="No format data in the current scope." />
            ) : null}
          </Panel>
      </div>
        </div>
        <Panel
          title="Insights & Recommendations"
          action={<Link className="link-teal" to="/insights">See All</Link>}
        >
          {campaigns.data && creatives.data && platforms.data ? (
            rail.length ? (
              <InsightList items={rail.map((r) => ({ icon: r.icon, tint: r.tint, title: r.title, body: r.body, action: r.action, href: r.href }))} />
            ) : <EmptyState text="Not enough scoped data for recommendations yet." />
          ) : <Skeleton height={320} />}
        </Panel>
      </div>
    </div>
  );
}

