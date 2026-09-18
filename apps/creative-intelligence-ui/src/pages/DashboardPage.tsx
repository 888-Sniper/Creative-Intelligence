import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { VideoUploadCard } from "@/components/VideoUploadCard";
import { monthName } from "@/components/KpiTrend";
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
  fmtMult,
  fmtPct,
  KpiKind,
  kpiDisplay,
  kpiPlaceholderNote,
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

function num(value: unknown): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function shortDay(iso: string, locale: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return `${monthName(Number(m[2]), locale)} ${Number(m[3])}`;
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

// Option values are stable backend ids; display names always go
// through kpiName() (filters.kpis.*) so ES/PL render localized.
const TREND_METRICS = [
  { value: "impressions" },
  { value: "clicks" },
  { value: "spend" },
  { value: "conversions" },
] as const;

type TrendMetric = (typeof TREND_METRICS)[number]["value"];

const BENCH_METRICS = [
  { value: "ctr" },
  { value: "roas" },
  { value: "cpa" },
  { value: "cpc" },
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

function formatBench(metric: BenchMetric, value: number | null, locale = "en"): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (metric === "ctr") return fmtPct(value, 1, locale);
  if (metric === "roas") return fmtMult(value, locale);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency", currency: "USD",
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `$${value.toFixed(2)}`;
  }
}

export function DashboardPage() {
  const { me } = useAuth();
  const { t, locale, fmtNum } = useLocale();
  const unavailable = t("common.unavailable");
  const emptyNote = t("dashboard.emptyKpiNote");
  // Bare decimals for sentence templates (the % / x suffix lives in
  // the template so ES can space it: "{ctr} %").
  const dec1 = (v: number): string =>
    fmtNum(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dec0 = (v: number): string => fmtNum(v, { maximumFractionDigits: 0 });
  const kpiName = (id: string): string => {
    const key = `filters.kpis.${id.toLowerCase()}`;
    const hit = t(key);
    return hit === key ? titleCase(id) : hit;
  };
  const bucketName = (key: string): string => {
    if (key === "Under 15s") return t("dashboard.buckets.under");
    if (key === "Over 30s") return t("dashboard.buckets.over");
    if (key === "15–30s") return t("dashboard.buckets.mid");
    return key;
  };
  const { clearFilters, filters, setFilter } = useFilters();
  const [applied, setApplied] = useState(0);
  const [leftMetric, setLeftMetric] = useState<TrendMetric>("impressions");
  const [rightMetric, setRightMetric] = useState<TrendMetric>("clicks");
  const [benchMetric, setBenchMetric] = useState<BenchMetric>("ctr");
  const [baseline, setBaseline] = useState("Scope Average");
  const [tab, setTab] = useState("retention");
  const [curve, setCurve] = useState<Array<[number, number]> | null>(null);
  const [curveError, setCurveError] = useState("");
  const [curveLoading, setCurveLoading] = useState(true);

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
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  const firstName = me?.employee?.first_name?.trim() || "";
  const greeting = firstName
    ? t(`dashboard.greeting.${part}`, { name: firstName })
    : t(`dashboard.greeting.${part}Anon`);

  const trend = useMemo(() => downsample(daily ?? []), [daily]);
  const leftLabel = kpiName(leftMetric);
  const rightLabel = kpiName(rightMetric);
  const trendSeries = [
    { label: leftLabel, color: "var(--glyph-teal)", soft: "#E5F5F2", points: trend.map((p) => num(p[leftMetric])) },
    { label: rightLabel, color: "var(--glyph-navy)", soft: "#E4EAF7", points: trend.map((p) => num(p[rightMetric])), axis: "right" as const },
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
      // No top creative (still loading, or an honestly empty scope):
      // never leave the retention chart on its shimmer.
      setCurve(null);
      setCurveLoading(false);
      return;
    }
    let live = true;
    setCurve(null);
    setCurveError("");
    setCurveLoading(true);
    api<CurveResponse>("GET", `/api/retention/curve?creative_key=${encodeURIComponent(key)}`)
      .then((r) => {
        if (!live) return;
        const pts = r.points.map((p) => [num(p.t), num(p.p)] as [number, number]);
        setCurve(pts.length ? pts : null);
        if (!pts.length) setCurveError(t("dashboard.retention.noCurve"));
        setCurveLoading(false);
      })
      .catch((e) => {
        if (!live) return;
        setCurveError(e instanceof Error ? e.message : String(e));
        setCurveLoading(false);
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
  const hookName = (key: string) => {
    const hk = `filters.hooks.${key}`;
    const hit = t(hk);
    return hit === hk ? titleCase(key) : hit;
  };
  const hookCompare = useMemo(
    () => hookRows.slice(0, 5).map((r) => ({ label: hookName(r.key), yours: r.ctr ?? 0, bench: hookBaseline ?? 0 })),
    [hookRows, hookBaseline, t],
  );
  const lengthCompare = useMemo(
    () => durationRows.filter((r) => r.ctr != null).map((r) => ({ label: bucketName(r.key), yours: r.ctr ?? 0, bench: r.ctr ?? 0 })),
    [durationRows, t],
  );
  const formatCompare = useMemo(() => {
    const agg = new Map<string, { clicks: number; impr: number }>();
    for (const c of creatives.data ?? []) {
      const key = (c.format || c.annotation?.hook_type ? (c.format || t("dashboard.unformatted")) : t("dashboard.unformatted")).trim() || t("dashboard.unformatted");
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
          tint: "var(--shell-teal-soft)",
          title: tied
            ? t("dashboard.insights.hookTieTitle", { a: hookName(a.key), b: hookName(b.key) })
            : t("dashboard.insights.hookLeadTitle", { a: hookName(a.key) }),
          body: tied
            ? t("dashboard.insights.hookTieBody", { a: hookName(a.key), b: hookName(b.key), ctr: dec1(a.ctr ?? 0) })
            : t("dashboard.insights.hookLeadBody", {
                a: hookName(a.key),
                ctr: dec1(a.ctr ?? 0),
                diff: diff != null
                  ? t("dashboard.insights.vsDiff", { sign: diff >= 0 ? "+" : "", pct: dec0(diff), b: hookName(b.key) })
                  : "",
              }),
          action: t("dashboard.insights.viewCreatives"),
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
        const topIsCreator = top === creator;
        const topName = topIsCreator ? t("filters.creators.creator") : t("filters.creators.branded");
        const bottomName = (topIsCreator ? t("filters.creators.branded") : t("filters.creators.creator")).toLowerCase();
        const topCtr = top.ctr ?? 0;
        const bottomCtr = bottom.ctr ?? 0;
        const diff = percentDiff(topCtr, bottomCtr);
        items.push({
          icon: "users",
          tint: "var(--shell-teal-soft)",
          title: verdict === "tie"
            ? t("dashboard.insights.creatorTieTitle")
            : t("dashboard.insights.creatorLeadTitle", { top: topName, bottom: bottomName }),
          body: verdict === "tie"
            ? t("dashboard.insights.creatorTieBody", { ctr: dec1(topCtr) })
            : t("dashboard.insights.creatorLeadBody", {
                top: topName,
                topCtr: dec1(topCtr),
                bottomCtr: dec1(bottomCtr),
                bottom: bottomName,
                diff: diff != null ? t("dashboard.insights.pctDiff", { sign: diff >= 0 ? "+" : "", pct: dec0(diff) }) : "",
              }),
          action: t("dashboard.insights.exploreCreatives"),
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
            tint: "var(--shell-blue-soft)",
            title: t("dashboard.insights.platformTieTitle"),
            body: t("dashboard.insights.platformTieBody", { roas: dec1(tiktok.roas) }),
            action: t("dashboard.insights.viewCampaigns"),
            href: "/campaigns",
          });
        } else {
          const leader = verdict === "lead" ? tiktok : meta;
          const trailer = leader === tiktok ? meta : tiktok;
          const diff = percentDiff(leader.roas ?? 0, trailer.roas ?? 0);
          items.push({
            icon: "tiktok",
            tint: "var(--shell-blue-soft)",
            title: t("dashboard.insights.platformLeadTitle", { leader: platformLabel(leader.key) }),
            body: t("dashboard.insights.platformLeadBody", {
              leader: platformLabel(leader.key),
              leaderRoas: dec1(leader.roas ?? 0),
              trailerRoas: dec1(trailer.roas ?? 0),
              trailer: platformLabel(trailer.key),
              diff: diff != null ? t("dashboard.insights.pctDiff", { sign: diff >= 0 ? "+" : "", pct: dec0(diff) }) : "",
            }),
            action: t("dashboard.insights.viewCampaigns"),
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
          tint: "var(--shell-blue-soft)",
          title: t("dashboard.insights.durationLeadTitle"),
          body: t("dashboard.insights.durationLeadBody", {
            ctr: dec1(sweet.ctr),
            diff: diff != null ? t("dashboard.insights.aboveNext", { sign: diff >= 0 ? "+" : "", pct: dec0(diff) }) : "",
          }),
          action: t("dashboard.insights.seeRecommendations"),
          href: "/insights",
        });
      } else if (verdict === "tie") {
        items.push({
          icon: "play",
          tint: "var(--shell-blue-soft)",
          title: t("dashboard.insights.durationTieTitle"),
          body: t("dashboard.insights.durationTieBody", { ctr: dec1(sweet.ctr) }),
          action: t("dashboard.insights.seeRecommendations"),
          href: "/insights",
        });
      }
    }
    return items.slice(0, 4);
  }, [hookRows, modeRows, platforms.data, durationRows, t, fmtNum]);

  const nearThree = useMemo(() => {
    if (!curve?.length) return null;
    return curve.slice().sort((a, b) => Math.abs(a[0] - 3) - Math.abs(b[0] - 3))[0];
  }, [curve]);

  // Key Takeaways only renders when at least one takeaway exists; an empty
  // retention scope shows the centered No Retention Data state instead.
  const hasTakeaways = Boolean(nearThree)
    || hookRows[0]?.ctr != null
    || durationRows.find((r) => r.key === "15–30s")?.ctr != null;

  // Empty scope (no current records) shows formatted zero placeholders;
  // a loaded nonempty scope with an uncomputable metric says Unavailable.
  const emptyScope = compare ? compare.current_n_ads === 0 : false;
  const kpi = (kind: KpiKind, value: number | null | undefined) => ({
    display: compare ? kpiDisplay(kind, value, emptyScope, locale, unavailable) : "",
    note: compare && kpiPlaceholderNote(kind, value, emptyScope) ? emptyNote : null,
  });
  const kpiConfigs = [
    { label: t("dashboard.totalImpressions"), metric: "impressions", ...kpi("count", compare?.metrics.impressions?.current), icon: "users", tint: "var(--shell-teal-soft)", color: "var(--glyph-teal)" },
    { label: t("dashboard.totalClicks"), metric: "clicks", ...kpi("count", compare?.metrics.clicks?.current), icon: "click", tint: "var(--shell-blue-soft)", color: "var(--glyph-blue)" },
    { label: t("dashboard.totalSpend"), metric: "spend", ...kpi("money", compare?.metrics.spend?.current), icon: "coin", tint: "var(--shell-green-soft)", color: "var(--glyph-green)" },
    { label: t("dashboard.averageRoas"), metric: "roas", ...kpi("mult", compare?.metrics.roas?.current), icon: "bars", tint: "var(--shell-blue-soft)", color: "var(--glyph-blue)" },
  ];

  return (
    <div className="dashboard">
      <PageHeader
        title={greeting}
        sub={t("dashboard.sub")}
        actions={(
          <>
            <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
              {t("filters.apply")}
            </button>
            <button type="button" className="link-teal" onClick={clearFilters}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> {t("filters.reset")}
            </button>
          </>
        )}
      />
      {/* Guided video upload: compact card plus recent uploads, below
        the greeting and above the filters. Never touches Apply/Reset,
        the greeting, KPIs, charts or layout. */}
      <VideoUploadCard />
      {/* Team stays in the global scope but hides on Dashboard only.
        A hidden-yet-active scope is never silent: the chip below names
        it and clears it deliberately. */}
      <FilterPanel actions="none" showTeam={false} />
      {filters.team ? (
        <div className="chip-row" style={{ margin: "10px 0 0" }}>
          <span className="chip-static">{t("dashboard.teamScope", { team: filters.team })}</span>
          <button type="button" className="link-teal" onClick={() => setFilter("team", "")}>
            {t("dashboard.clearTeam")}
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
                metricLabel={kpiName(k.metric)}
                compare={compare}
                note={k.note}
              />
            </div>
          ))}
        </div>
      ) : compareError ? (
        <div className="panel"><EmptyState text={compareError} /></div>
      ) : (
        <div className="kpi-grid">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={100} />)}
        </div>
      )}
      <div className="cols-2 dash-charts">
        <Panel
          title={t("dashboard.trends.title")}
          action={(
            <div className="mini-selects">
              <select aria-label={t("dashboard.trends.leftAria")} value={leftMetric} onChange={(e) => setLeftMetric(e.target.value as TrendMetric)}>
                {TREND_METRICS.map((m) => <option key={m.value} value={m.value}>{kpiName(m.value)}</option>)}
              </select>
              <span className="mini-vs">{t("dashboard.trends.versus")}</span>
              <select aria-label={t("dashboard.trends.rightAria")} value={rightMetric} onChange={(e) => setRightMetric(e.target.value as TrendMetric)}>
                {TREND_METRICS.map((m) => <option key={m.value} value={m.value}>{kpiName(m.value)}</option>)}
              </select>
            </div>
          )}
        >
          {daily ? (
            trend.length ? (
              <>
                <TrendChart series={trendSeries} labels={trend.map((p) => shortDay(p.date, locale))} height={205} />
                <div className="legend">
                  {trendSeries.map((s) => (
                    <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
                  ))}
                </div>
              </>
            ) : <EmptyState compact verbatim icon="trend" title={t("dashboard.trends.emptyTitle")} text={t("dashboard.trends.emptyBody")} />
          ) : <Skeleton height={205} />}
        </Panel>
        <Panel
          title={t("dashboard.bench.title")}
          action={(
            <div className="mini-selects">
              <select aria-label={t("dashboard.bench.metricAria")} value={benchMetric} onChange={(e) => setBenchMetric(e.target.value as BenchMetric)}>
                {BENCH_METRICS.map((m) => <option key={m.value} value={m.value}>{kpiName(m.value)}</option>)}
              </select>
              <span className="mini-vs">{t("dashboard.trends.versus")}</span>
              <select aria-label={t("dashboard.bench.baselineAria")} value={baseline} onChange={(e) => setBaseline(e.target.value)}>
                <option value="Scope Average">{t("dashboard.bench.scopeAverage")}</option>
                <option value="Top Performer">{t("dashboard.bench.topPerformer")}</option>
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
                  format={(v) => formatBench(benchMetric, v, locale)}
                />
                <div className="legend">
                  <span><i style={{ background: "#0A9183", borderRadius: 2 }} />{t("dashboard.bench.yours")}</span>
                  <span><i style={{ background: "#CBD8E6", borderRadius: 2 }} />{baseline === "Top Performer" ? t("dashboard.bench.topPerformer") : t("dashboard.bench.scopeAverage")}</span>
                </div>
              </>
            ) : <EmptyState compact verbatim icon="bars" title={t("dashboard.bench.emptyTitle")} text={t("dashboard.bench.emptyBody")} />
          ) : <Skeleton height={205} />}
        </Panel>
      </div>
      {/* Approved composition: Top Creatives and Retention sit side by
        side beneath the charts (collapses to stacked under 1180px). */}
      <div className="cols-2 dash-lower">
          <Panel
            title={t("dashboard.topCreatives.title")}
            action={<Link className="link-teal" to="/creatives">{t("dashboard.topCreatives.seeAll")}</Link>}
          >
            {creatives.data ? (
              topCreatives.length ? (
                <div className="tbl-wrap">
                  <table className="tbl dash-table">
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">{t("dashboard.topCreatives.creativeCol")}</th>
                        <th scope="col">{t("dashboard.topCreatives.campaignCol")}</th>
                        <th scope="col" className="num">{kpiName("impressions")}</th>
                        <th scope="col" className="num">{kpiName("ctr")}</th>
                        <th scope="col" className="num">{kpiName("cvr")}</th>
                        <th scope="col" className="num">{kpiName("roas")}</th>
                        <th scope="col"><span className="sr-only">{t("dashboard.topCreatives.actionsCol")}</span></th>
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
                            <td className="num">{fmtCompact(num(c.metrics?.impressions), locale)}</td>
                            <td className="num">{ctr == null ? "—" : fmtPct(ctr, 1, locale)}</td>
                            <td className="num">{cvr == null ? "—" : fmtPct(cvr, 1, locale)}</td>
                            <td className="num">{roas == null ? "—" : fmtMult(roas, locale)}</td>
                            <td>
                              <Link className="icon-btn" to="/creatives" aria-label={t("dashboard.topCreatives.openIn", { name: c.name || c.creative_key })}>
                                <Icon name="dots" size={18} />
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState compact verbatim icon="creatives" title={t("dashboard.topCreatives.emptyTitle")} text={t("dashboard.topCreatives.emptyBody")} />
            ) : <Skeleton height={220} />}
          </Panel>
          <Panel title={t("dashboard.retention.title")}>
            <div className="field" style={{ margin: "0 0 12px" }}>
              <select
                id="dash-insight-type"
                aria-label={t("dashboard.retention.insightType")}
                value={tab}
                onChange={(e) => setTab(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="retention">{t("dashboard.retention.tabRetention")}</option>
                <option value="hooks">{t("dashboard.retention.tabHooks")}</option>
                <option value="length">{t("dashboard.retention.tabLength")}</option>
                <option value="format">{t("dashboard.retention.tabFormat")}</option>
              </select>
            </div>
            {tab === "retention" ? (
              <div className="retention-split">
                <div>
                  {curve ? (
                    <RetentionCurve
                      points={curve}
                      callout={nearThree ? t("dashboard.retention.callout3s", { pct: Math.round(nearThree[1]) }) : undefined}
                      height={170}
                    />
                  ) : curveError ? (
                    <EmptyState text={curveError} />
                  ) : curveLoading || creatives.loading ? (
                    <Skeleton height={170} />
                  ) : (
                    <div className="empty-center">
                      <EmptyState compact verbatim icon="play" title={t("dashboard.retention.emptyTitle")} text={t("dashboard.retention.emptyBody")} />
                    </div>
                  )}
                </div>
                {hasTakeaways ? (
                <div className="takeaways">
                  <h5><Icon name="check" size={15} /> {t("dashboard.retention.takeaways")}</h5>
                  <ul>
                    {nearThree ? (
                      <li><Icon name="check" size={13} /><span>{t("dashboard.retention.watchingAt3", { pct: Math.round(nearThree[1]), name: topCreatives[0]?.name || t("dashboard.retention.topCreative") })}</span></li>
                    ) : null}
                    {hookRows[0]?.ctr != null ? (
                      <li><Icon name="check" size={13} /><span>{t("dashboard.retention.hooksLead", { hook: hookName(hookRows[0].key), ctr: dec1(hookRows[0].ctr ?? 0) })}</span></li>
                    ) : null}
                    {durationRows.find((r) => r.key === "15–30s")?.ctr != null ? (
                      <li><Icon name="check" size={13} /><span>{t("dashboard.retention.sweetLength", { ctr: dec1(durationRows.find((r) => r.key === "15–30s")?.ctr ?? 0) })}</span></li>
                    ) : null}
                  </ul>
                </div>
                ) : null}
              </div>
            ) : null}
            {tab === "hooks" ? (
              hooks.loading ? (
                <Skeleton height={190} />
              ) : hookCompare.length ? (
                <GroupBars height={190} groups={hookCompare} format={(v) => fmtPct(v, 1, locale)} />
              ) : <EmptyState compact verbatim icon="spark" title={t("dashboard.retention.hookEmptyTitle")} text={t("dashboard.retention.hookEmptyBody")} />
            ) : null}
            {tab === "length" ? (
              creatives.loading ? (
                <Skeleton height={190} />
              ) : lengthCompare.length ? (
                <GroupBars height={190} groups={lengthCompare} format={(v) => fmtPct(v, 1, locale)} />
              ) : <EmptyState compact verbatim icon="play" title={t("dashboard.retention.durationEmptyTitle")} text={t("dashboard.retention.durationEmptyBody")} />
            ) : null}
            {tab === "format" ? (
              creatives.loading ? (
                <Skeleton height={190} />
              ) : formatCompare.length ? (
                <GroupBars height={190} groups={formatCompare} format={(v) => fmtPct(v, 1, locale)} />
              ) : <EmptyState compact verbatim icon="grid" title={t("dashboard.retention.formatEmptyTitle")} text={t("dashboard.retention.formatEmptyBody")} />
            ) : null}
          </Panel>
      </div>
        </div>
        <Panel
          title={t("dashboard.recommendations.title")}
          action={<Link className="link-teal" to="/insights">{t("dashboard.recommendations.seeAll")}</Link>}
        >
          {campaigns.data && creatives.data && platforms.data ? (
            rail.length ? (
              <InsightList items={rail.map((r) => ({ icon: r.icon, tint: r.tint, title: r.title, body: r.body, action: r.action, href: r.href }))} />
            ) : <EmptyState verbatim text={t("dashboard.recommendations.emptyBody")} />
          ) : <Skeleton height={320} />}
        </Panel>
      </div>
    </div>
  );
}

