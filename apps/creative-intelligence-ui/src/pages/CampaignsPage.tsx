import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { SampleCampaignDelete } from "@/components/SampleDelete";
import { GroupBars, TrendChart } from "@/components/charts";
import {
  DateRangeField,
  EmptyState,
  InfoTip,
  InsightList,
  KpiCard,
  PageHeader,
  Panel,
  Skeleton,
  fmtCell,
  fmtCompact,
  fmtMoney,
  fmtMult,
  fmtPct,
  kpiDisplay,
  kpiPlaceholderNote,
  platformLabel,
  useCompareState,
  useDaily,
  useScopedApi,
} from "@/components/product";

/* Campaigns keeps every existing backend behavior (scoped summaries,
 * compare handoff, CSV export, detail drawer) and only changes the
 * presentation layer to the approved Campaigns reference. */

interface CampaignRow {
  spend: number; impressions: number; clicks: number; conversions: number;
  revenue: number; ctr: number | null; cpc: number | null; cpa: number | null; roas: number | null;
  campaigns: number;
}

/* Per-campaign display metadata from GET /api/campaigns/meta
 * (unscoped attribute data: client, platforms, derived status). */
interface CampaignMeta {
  name: string; client: string; team: string; platforms: string[]; markets: string[];
  objectives: string[]; verticals: string[]; projects: string[];
  last_date: string; status: string;
}

interface BenchSummary extends CampaignRow {
  n_ads: number;
}

interface CampaignDetail {
  name: string;
  totals: CampaignRow & { vtr?: number | null };
  top_creatives: Array<{
    creative_key: string; campaigns: string[]; platform: string; format: string;
    metrics: CampaignRow & { vtr?: number | null };
    brand_seconds: number[]; product_seconds: number[];
  }>;
  recommendations: string[];
}

interface CompareLike {
  comparison: string | null;
  metrics: Record<string, { current: number | null }>;
}

const PLATFORM_METRICS = [
  { value: "spend", label: "Spend" },
  { value: "impressions", label: "Impressions" },
  { value: "clicks", label: "Clicks" },
] as const;

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function rate(cur: number, base: number): number | null {
  if (!base) return null;
  return ((cur - base) / Math.abs(base)) * 100;
}

export function CampaignsPage() {
  const { t, tp, locale, fmtNum } = useLocale();
  const unavailable = t("common.unavailable");
  // Bare decimals for sentence templates (the % / x suffix lives in
  // the template so ES can space it: "{ctr} %").
  const dec1 = (v: number): string =>
    fmtNum(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dec0 = (v: number): string => fmtNum(v, { maximumFractionDigits: 0 });
  const kpiName = (id: string): string => {
    const key = `filters.kpis.${id.toLowerCase()}`;
    const hit = t(key);
    return hit === key ? id.toUpperCase() : hit;
  };
  const location = useLocation();
  const navigate = useNavigate();
  const { filters, setFilter, clearFilters } = useFilters();
  const [applied, setApplied] = useState(0);
  const [moreFilters, setMoreFilters] = useState(false);
  const [platMetric, setPlatMetric] = useState<(typeof PLATFORM_METRICS)[number]["value"]>("spend");
  /* Global header search deep-links here: ?find= pre-fills the name
   * search so the hit is visible immediately. */
  const [search, setSearch] = useState(
    () => new URLSearchParams(location.search).get("find") ?? "");

  const { data: compare, error: compareError } = useCompareState(applied);
  const [focus, setFocus] = useState<CompareLike | null>(null);
  const daily = useDaily(90, applied);
  const campaigns = useScopedApi<Record<string, CampaignRow>>("/api/campaigns", applied);
  const benchPlatform = useScopedApi<Record<string, BenchSummary>>("/api/benchmarks?group_by=platform", applied);
  const benchHook = useScopedApi<Record<string, BenchSummary>>("/api/benchmarks?group_by=hook_type", applied);
  const meta = useScopedApi<{ campaigns: CampaignMeta[] }>("/api/campaigns/meta", applied);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [details, setDetails] = useState<Record<string, CampaignDetail | null>>({});
  const [detailErr, setDetailErr] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [banner, setBanner] = useState("");

  const initial = (location.state ?? {}) as { name?: string; compare?: CompareLike; kpi?: string };

  useEffect(() => {
    if (initial.compare) {
      setFocus(initial.compare);
      return;
    }
    const name = initial.name;
    if (!name) {
      setFocus(null);
      return;
    }
    let live = true;
    api<CompareLike>("GET", `/api/kpis/compare?campaign=${encodeURIComponent(name)}`)
      .then((r) => live && setFocus(r))
      .catch(() => live && setFocus(null));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.name]);

  useEffect(() => {
    if (initial.kpi) setFilter("kpi", initial.kpi);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.kpi]);

  /* Campaign attribute lookup (client / platforms / derived status
   * labels for the meta panel). Status and spend resolve server-side
   * through the shared scope; only the name search filters here. */
  const metaMap = useMemo(() => {
    const map = new Map<string, CampaignMeta>();
    for (const c of meta.data?.campaigns ?? []) map.set(c.name, c);
    return map;
  }, [meta.data]);
  const metaClients = useMemo(
    () => [...new Set((meta.data?.campaigns ?? []).map((c) => c.client).filter(Boolean))].sort(),
    [meta.data]);
  const metaTeams = useMemo(
    () => [...new Set((meta.data?.campaigns ?? []).map((c) => c.team).filter(Boolean))].sort(),
    [meta.data]);
  const metaMarkets = useMemo(
    () => [...new Set((meta.data?.campaigns ?? []).flatMap((c) => c.markets))].sort(),
    [meta.data]);
  const metaObjectives = useMemo(
    () => [...new Set((meta.data?.campaigns ?? []).flatMap((c) => c.objectives))].sort(),
    [meta.data]);
  const metaProjects = useMemo(
    () => [...new Set((meta.data?.campaigns ?? []).flatMap((c) => c.projects ?? []))].sort(),
    [meta.data]);
  const metaVerticals = useMemo(
    () => [...new Set((meta.data?.campaigns ?? []).flatMap((c) => c.verticals))].sort(),
    [meta.data]);

  /* Table, KPI cards, charts and recommendations all read the same
   * backend scope: status/spend live in the shared filter state and
   * resolve server-side, so every surface agrees. Only the name search
   * stays local (it has no backend axis). */
  const rows = useMemo(() => {
    const list = Object.entries(campaigns.data ?? {}).map(([name, m]) => ({ name, ...m }));
    const q = search.trim().toLowerCase();
    return list
      .filter((r) => (!q || r.name.toLowerCase().includes(q)))
      .sort((a, b) => num(b.spend) - num(a.spend));
  }, [campaigns.data, search]);

  const avgCtr = useMemo(() => {
    const impr = rows.reduce((t, r) => t + num(r.impressions), 0);
    const clicks = rows.reduce((t, r) => t + num(r.clicks), 0);
    return impr ? (clicks / impr) * 100 : null;
  }, [rows]);

  const underperformers = useMemo(
    () => (avgCtr == null ? [] : rows.filter((r) => r.ctr != null && r.ctr * 100 < avgCtr)),
    [rows, avgCtr],
  );

  const platGroups = useMemo(() => {
    const list = Object.entries(benchPlatform.data ?? {}).map(([key, g]) => ({ key, ...g }));
    const val = (g: BenchSummary) =>
      platMetric === "spend" ? num(g.spend) : platMetric === "impressions" ? num(g.impressions) : num(g.clicks);
    const total = list.reduce((t, g) => t + val(g), 0);
    const avg = list.length ? total / list.length : 0;
    return list
      .sort((a, b) => val(b) - val(a))
      .slice(0, 6)
      .map((g) => ({ label: platformLabel(g.key), yours: val(g), bench: avg }));
  }, [benchPlatform.data, platMetric]);

  const rail = useMemo(() => {
    const items: Array<{ icon: string; tint: string; title: string; body: string; action: string; href: string }> = [];
    const plats = Object.entries(benchPlatform.data ?? {})
      .map(([key, g]) => ({ key, roas: g.roas ?? null }))
      .filter((r) => r.roas != null)
      .sort((a, b) => (b.roas ?? 0) - (a.roas ?? 0));
    if (plats.length > 1 && plats[0].roas != null) {
      const avg = plats.reduce((t, p) => t + (p.roas ?? 0), 0) / plats.length;
      const d = rate(plats[0].roas ?? 0, avg);
      items.push({
        icon: "trend", tint: "var(--shell-teal-soft)",
        title: t("campaigns.rail.scaleTitle"),
        body: t("campaigns.rail.scaleBody", {
          platform: platformLabel(plats[0].key),
          roas: dec1(plats[0].roas ?? 0),
          diff: d != null ? t("campaigns.rail.aboveAvg", { sign: d >= 0 ? "+" : "", pct: dec0(d) }) : "",
        }),
        action: t("campaigns.rail.viewCampaigns"), href: "/campaigns",
      });
    }
    if (underperformers.length) {
      const avg = avgCtr == null ? "" : dec1(avgCtr);
      items.push({
        icon: "users", tint: "var(--shell-teal-soft)",
        title: t("campaigns.rail.improveTitle"),
        body: tp("campaigns.rail.improveBody", underperformers.length, { count: underperformers.length, avg }),
        action: t("campaigns.rail.viewRecommendations"), href: "/creatives",
      });
    }
    const hookRows = Object.entries(benchHook.data ?? {})
      .map(([key, g]) => ({ key, ctr: g.ctr == null ? null : g.ctr * 100 }))
      .filter((r) => r.ctr != null)
      .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    if (hookRows[0]?.ctr != null) {
      const hk = `filters.hooks.${hookRows[0].key}`;
      const hookHit = t(hk);
      items.push({
        icon: "spark", tint: "var(--shell-blue-soft)",
        title: t("campaigns.rail.optimizeTitle"),
        body: t("campaigns.rail.optimizeBody", {
          hook: hookHit === hk ? hookRows[0].key.replace(/_/g, " ") : hookHit,
          ctr: dec1(hookRows[0].ctr ?? 0),
        }),
        action: t("campaigns.rail.seeInsights"), href: "/insights",
      });
    }
    const topRoas = rows
      .filter((r) => r.roas != null)
      .sort((a, b) => (b.roas ?? 0) - (a.roas ?? 0))[0];
    if (topRoas?.roas != null) {
      items.push({
        icon: "target", tint: "var(--shell-teal-soft)",
        title: t("campaigns.rail.refineTitle"),
        body: t("campaigns.rail.refineBody", { name: topRoas.name, roas: dec1(topRoas.roas) }),
        action: t("campaigns.rail.viewDetails"), href: "/compare",
      });
    }
    return items.slice(0, 4);
  }, [benchPlatform.data, benchHook.data, underperformers, avgCtr, rows, t, tp]);

  /* Reset clears every active filter: shared scope plus the local
   * name search (status/spend live in shared state since the
   * consistency pass, so clearFilters covers them too). */
  const resetAll = () => {
    clearFilters();
    setSearch("");
  };

  const spendBand = !filters.spend_min && !filters.spend_max ? "all"
    : filters.spend_min === "25000" && filters.spend_max === "50000" ? "mid"
    : filters.spend_min === "50000" ? "over"
    : filters.spend_max === "25000" ? "under" : "all";
  const setSpendBand = (band: string) => {
    if (band === "under") {
      setFilter("spend_min", ""); setFilter("spend_max", "25000");
    } else if (band === "mid") {
      setFilter("spend_min", "25000"); setFilter("spend_max", "50000");
    } else if (band === "over") {
      setFilter("spend_min", "50000"); setFilter("spend_max", "");
    } else {
      setFilter("spend_min", ""); setFilter("spend_max", "");
    }
  };

  const toggle = (name: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.name));
  const toggleAll = () =>
    setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.name)));

  const onCompare = () => {
    const names = [...selected];
    if (!names.length) {
      setBanner(t("campaigns.banner.selectToCompare"));
      return;
    }
    setBanner("");
    navigate("/compare", {
      state: {
        compare: {
          names,
          kind: "campaign" as const,
          kpi: !filters.kpi || filters.kpi === "all" ? "roas" : filters.kpi,
        },
      },
    });
  };

  const onExport = async () => {
    const names = rows.map((r) => r.name);
    if (!names.length) {
      setBanner(t("campaigns.banner.nothingToExport"));
      return;
    }
    setExportBusy(true);
    setBanner("");
    try {
      const res = await fetch("/api/exports/campaigns", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names }),
      });
      if (!res.ok) throw new Error("Export Failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "campaigns.csv";
      a.click();
      URL.revokeObjectURL(url);
      setBanner(tp("campaigns.banner.exported", names.length, { count: names.length }));
    } catch (e) {
      setBanner(e instanceof Error ? e.message : t("campaigns.banner.exportFailed"));
    } finally {
      setExportBusy(false);
    }
  };

  useEffect(() => {
    const name = expanded;
    if (!name || details[name]) return;
    let live = true;
    api<CampaignDetail>("GET", `/api/campaigns/${encodeURIComponent(name)}`)
      .then((r) => live && setDetails((prev) => ({ ...prev, [name]: r })))
      .catch((e: unknown) => {
        if (!live) return;
        const msg = e instanceof ApiError ? e.message : "Could Not Load Campaign Details.";
        setDetailErr((prev) => ({ ...prev, [name]: msg }));
      });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded]);

  const kpiKey = !filters.kpi || filters.kpi === "all" ? "roas" : filters.kpi;
  const benchName = initial.name ?? [...selected][0] ?? rows[0]?.name ?? null;
  const benchVal = focus && benchName
    ? focus.metrics[kpiKey]?.current ?? null
    : null;

  /* Shared FilterPanel stores "no constraint" as ""; the legacy "all"
   *  sentinel normalises to "" here so every controlled select always
   *  holds a value one of its <option>s carries. */
  const selectProps = (key: "client" | "campaign" | "platform" | "objective" | "market" | "team" | "kpi") => ({
    value: filters[key] === "all" ? "" : filters[key],
    onChange: (e: React.ChangeEvent<HTMLSelectElement>) => setFilter(key, e.target.value),
  });
  const fmtBench = (v: number | null) => fmtCell(v, (n) => {
    const k = kpiKey;
    if (k === "roas") return fmtMult(n, locale);
    if (k === "spend" || k === "cpa" || k === "cpc") return fmtMoney(n, locale);
    if (k === "ctr") return fmtPct(n * 100, 1, locale);
    return fmtCompact(n, locale);
  }, unavailable);

  return (
    <div className="campaigns">
      <PageHeader
        title={t("campaigns.title")}
        sub={t("campaigns.sub")}
        actions={(
          <>
            <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
              {t("filters.apply")}
            </button>
            <button type="button" className="link-teal" onClick={resetAll}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> {t("filters.reset")}
            </button>
          </>
        )}
      />
      {/* Approved composition goes straight into the controls:
        no extra "Campaign Filters" heading. */}
      <section className="panel" aria-label={t("campaigns.filtersAria")}>
        <div className="filter-grid">
          <div className="field">
            <label htmlFor="c-client">{t("filters.client")}</label>
            <select id="c-client" {...selectProps("client")}>
              <option value="">{t("filters.allClients")}</option>
              {metaClients.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <DateRangeField id="c-date" />
          <div className="field">
            <label htmlFor="c-spend">{t("campaigns.spendLabel")}</label>
            <select id="c-spend" value={spendBand} onChange={(e) => setSpendBand(e.target.value)}>
              <option value="all">{t("campaigns.spendAll")}</option>
              <option value="under">{t("campaigns.spendUnder")}</option>
              <option value="mid">{t("campaigns.spendMid")}</option>
              <option value="over">{t("campaigns.spendOver")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-kpi">{t("campaigns.kpiFocus")}</label>
            <select id="c-kpi" {...selectProps("kpi")} value={filters.kpi === "all" ? "" : filters.kpi}>
              <option value="">{t("filters.allKpis")}</option>
              <option value="impressions">{kpiName("impressions")}</option>
              <option value="clicks">{kpiName("clicks")}</option>
              <option value="spend">{kpiName("spend")}</option>
              <option value="conversions">{kpiName("conversions")}</option>
              <option value="ctr">{kpiName("ctr")}</option>
              <option value="cpa">{kpiName("cpa")}</option>
              <option value="roas">{kpiName("roas")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-objective">{t("filters.objective")}</label>
            <select id="c-objective" {...selectProps("objective")}>
              <option value="">{t("filters.allObjectives")}</option>
              {metaObjectives.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-team">{t("filters.team")}</label>
            <select id="c-team" {...selectProps("team")}>
              <option value="">{t("filters.allTeams")}</option>
              {metaTeams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-market">{t("filters.market")}</label>
            <select id="c-market" {...selectProps("market")}>
              <option value="">{t("filters.allMarkets")}</option>
              {metaMarkets.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="field">
            {/* Status stays activity-derived (not the ad platform's own
              status); the explainer lives on an info icon beside the
              short label so the card stays shallow. The icon sits
              outside the label element to keep its accessible name
              exactly "Campaign Status". */}
            <span style={{ display: "flex", alignItems: "center", gap: 6, margin: "0 0 6px" }}>
              <label htmlFor="c-status" style={{ margin: 0 }}>{t("campaigns.statusLabel")}</label>
              <InfoTip label={t("campaigns.statusInfoLabel")}
                text={t("campaigns.statusInfoBody")} />
            </span>
            <select id="c-status" value={filters.status || "all"}
              title={t("campaigns.statusInfoBody")}
              onChange={(e) => setFilter("status", e.target.value === "all" ? "" : e.target.value)}>
              <option value="all">{t("campaigns.statusAll")}</option>
              <option value="Active">{t("campaigns.statusNames.Active")}</option>
              <option value="Completed">{t("campaigns.statusNames.Completed")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-platform">{t("filters.platform")}</label>
            <select id="c-platform" {...selectProps("platform")}>
              <option value="">{t("filters.allPlatforms")}</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <div className="field">
            <span className="field-label" aria-hidden="true">&nbsp;</span>
            <button type="button" className="filter-toggle" onClick={() => setMoreFilters((v) => !v)}
              aria-expanded={moreFilters}>
              {moreFilters ? t("campaigns.fewerFilters") : t("campaigns.moreFilters")}
              <Icon name="chev" size={13} />
            </button>
          </div>
          {moreFilters ? (
            <>
              <div className="field">
                <label htmlFor="c-project">{t("filters.project")}</label>
                <select id="c-project" value={filters.project === "all" ? "" : filters.project} onChange={(e) => setFilter("project", e.target.value)}>
                  <option value="">{t("filters.allProjects")}</option>
                  {metaProjects.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="c-vertical">{t("filters.vertical")}</label>
                <select id="c-vertical" value={filters.vertical === "all" ? "" : filters.vertical} onChange={(e) => setFilter("vertical", e.target.value)}>
                  <option value="">{t("filters.allVerticals")}</option>
                  {metaVerticals.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="c-funnel">{t("filters.funnel")}</label>
                <select id="c-funnel" value={filters.funnel === "all" ? "" : filters.funnel} onChange={(e) => setFilter("funnel", e.target.value)}>
                  <option value="">{t("filters.allStages")}</option>
                  <option value="upper">{t("filters.funnels.upper")}</option>
                  <option value="mid">{t("filters.funnels.mid")}</option>
                  <option value="lower">{t("filters.funnels.lower")}</option>
                </select>
              </div>
            </>
          ) : null}
        </div>
      </section>
      {banner ? <p className="panel-sub" role="status" style={{ margin: "12px 0 0" }}>{banner}</p> : null}
      <div className="main-rail" style={{ marginTop: 12 }}>
        <div className="rail-stack">
          {compare ? (
            <div className="kpi-grid">
              <div className="kpi-card">
                <span className="kpi-ico">
                  <Icon name="users" size={20} />
                </span>
                <div className="kpi-body">
                  <div className="kpi-label">{t("campaigns.totalCampaigns")}</div>
                  <div className="kpi-value">{rows.length}</div>
                </div>
              </div>
              <KpiCard label={t("dashboard.totalImpressions")} display={kpiDisplay("count", compare.metrics.impressions?.current, compare.current_n_ads === 0)}
                icon="megaphone" tint="var(--shell-teal-soft)" metricLabel={kpiName("impressions")} compare={compare} />
              <KpiCard label={t("dashboard.totalClicks")} display={kpiDisplay("count", compare.metrics.clicks?.current, compare.current_n_ads === 0)}
                icon="click" tint="var(--shell-blue-soft)" metricLabel={kpiName("clicks")} compare={compare} />
              <KpiCard label={t("dashboard.averageRoas")} display={kpiDisplay("mult", compare.metrics.roas?.current, compare.current_n_ads === 0)}
                icon="coin" tint="var(--shell-green-soft)" metricLabel="ROAS" compare={compare}
                note={kpiPlaceholderNote("mult", compare.metrics.roas?.current, compare.current_n_ads === 0)} />
            </div>
          ) : compareError ? (
            <div className="panel"><EmptyState text={compareError} /></div>
          ) : (
            <div className="kpi-grid">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={118} />)}
            </div>
          )}
          <div className="cols-2">
            <Panel title={t("campaigns.trendsTitle")}>
              {daily ? (
                <TrendChart
                  height={200}
                  series={[
                    { label: kpiName("impressions"), color: "var(--glyph-teal)", soft: "#E5F5F2", points: daily.map((p) => num(p.impressions)) },
                    { label: kpiName("clicks"), color: "var(--glyph-navy)", soft: "#E4EAF7", points: daily.map((p) => num(p.clicks)), axis: "right" },
                  ]}
                  labels={daily.map((p) => p.date.slice(5))}
                />
              ) : <Skeleton height={200} />}
            </Panel>
            <Panel
              title={t("campaigns.platformTitle")}
              action={(
                <select aria-label={t("campaigns.platformMetricAria")} value={platMetric}
                  onChange={(e) => setPlatMetric(e.target.value as typeof platMetric)}>
                  {PLATFORM_METRICS.map((m) => <option key={m.value} value={m.value}>{kpiName(m.value)}</option>)}
                </select>
              )}
            >
              {benchPlatform.data ? (
                platGroups.length ? (
                  <GroupBars
                    height={200}
                    groups={platGroups}
                    format={(v) => platMetric === "spend" ? fmtMoney(v, locale) : fmtCompact(v, locale)}
                  />
                ) : <EmptyState compact verbatim icon="bars" title={t("campaigns.noPlatformTitle")} text={t("campaigns.noPlatformBody")} />
              ) : <Skeleton height={200} />}
            </Panel>
          </div>
          <Panel
            title={t("campaigns.allCampaigns", { count: rows.length })}
            action={(
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <input
                  aria-label={t("campaigns.searchAria")}
                  placeholder={t("campaigns.searchPlaceholder")}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ width: 200 }}
                />
                <button type="button" className="btn-outline" onClick={onCompare}>
                  {t("campaigns.compareSelected", { count: selected.size })}
                </button>
                <LoadingButton type="button" className="btn-outline" loading={exportBusy} loadingLabel={t("campaigns.exporting")} spinnerClass="spinner dark" disabled={exportBusy} onClick={() => void onExport()}>
                  <Icon name="download" size={15} /> {t("campaigns.exportBtn")}
                </LoadingButton>
              </div>
            )}
          >
            {campaigns.data ? (
              rows.length ? (
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th scope="col"><input type="checkbox" aria-label={t("campaigns.selectAll")} checked={allChecked} onChange={toggleAll} /></th>
                        <th scope="col">{t("campaigns.headers.campaign")}</th>
                        <th scope="col">{t("campaigns.headers.client")}</th>
                        <th scope="col">{t("campaigns.headers.platform")}</th>
                        <th scope="col">{t("campaigns.headers.status")}</th>
                        <th scope="col" className="num">{kpiName("impressions")}</th>
                        <th scope="col" className="num">{kpiName("clicks")}</th>
                        <th scope="col" className="num">{kpiName("ctr")}</th>
                        <th scope="col" className="num">{kpiName("spend")}</th>
                        <th scope="col" className="num">{kpiName("roas")}</th>
                        <th scope="col" className="num">{t("campaigns.headers.vsBench")}</th>
                        <th scope="col"><span className="sr-only">{t("campaigns.headers.actions")}</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.name}>
                          <td>
                            <input type="checkbox" aria-label={t("campaigns.selectOne", { name: r.name })}
                              checked={selected.has(r.name)} onChange={() => toggle(r.name)} />
                          </td>
                          <td><span className="cell-main">{r.name}</span></td>
                          <td>{metaMap.get(r.name)?.client || "—"}</td>
                          <td>{(metaMap.get(r.name)?.platforms ?? []).map(platformLabel).join(", ") || "—"}</td>
                          <td>{metaMap.get(r.name)?.status ? (
                            <span className={`badge ${metaMap.get(r.name)?.status === "Active" ? "good" : "bad"}`}>
                              {(() => {
                                const sk = `campaigns.statusNames.${metaMap.get(r.name)?.status}`;
                                const hit = t(sk);
                                return hit === sk ? metaMap.get(r.name)?.status : hit;
                              })()}
                            </span>
                          ) : "—"}</td>
                          <td className="num">{fmtCompact(num(r.impressions), locale)}</td>
                          <td className="num">{fmtCompact(num(r.clicks), locale)}</td>
                          <td className="num">{fmtCell(r.ctr, (n) => fmtPct(n * 100, 1, locale))}</td>
                          <td className="num">{fmtMoney(num(r.spend), locale)}</td>
                          <td className="num">{fmtCell(r.roas, (n) => fmtMult(n, locale))}</td>
                          <td className="num">{fmtBench(benchVal)}</td>
                          <td>
                            <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                              <button type="button" className="icon-btn" aria-expanded={expanded === r.name}
                                aria-label={t("campaigns.detailsFor", { name: r.name })}
                                onClick={() => setExpanded((cur) => (cur === r.name ? null : r.name))}>
                                <Icon name="dots" size={18} />
                              </button>
                              <SampleCampaignDelete campaignName={r.name}
                                onDeleted={() => setApplied((a) => a + 1)} />
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState compact verbatim icon="campaign" title={t("campaigns.noMatchTitle")} text={t("campaigns.noMatchBody")} />
            ) : campaigns.error ? (
              <EmptyState text={campaigns.error} action={(
                <button type="button" className="btn-outline"
                  onClick={() => setApplied((a) => a + 1)}>
                  {t("common.retry")}
                </button>
              )} />
            ) : <Skeleton height={220} />}
          </Panel>
          {expanded ? (
            <Panel title={expanded}>
              {details[expanded] ? (
                <>
                  <div className="detail-grid">
                    <div><span>{kpiName("impressions")}</span><strong>{fmtCompact(num(details[expanded]?.totals.impressions), locale)}</strong></div>
                    <div><span>{kpiName("clicks")}</span><strong>{fmtCompact(num(details[expanded]?.totals.clicks), locale)}</strong></div>
                    <div><span>{kpiName("spend")}</span><strong>{fmtMoney(num(details[expanded]?.totals.spend), locale)}</strong></div>
                    <div><span>{kpiName("roas")}</span><strong>{fmtCell(details[expanded]?.totals.roas, (n) => fmtMult(n, locale))}</strong></div>
                    <div><span>{kpiName("ctr")}</span><strong>{fmtCell(details[expanded]?.totals.ctr, (n) => fmtPct(n * 100, 1, locale))}</strong></div>
                    <div><span>{kpiName("conversions")}</span><strong>{fmtCompact(num(details[expanded]?.totals.conversions), locale)}</strong></div>
                  </div>
                  <h4 style={{ margin: "14px 0 8px", fontSize: 14 }}>{t("dashboard.topCreatives.title")}</h4>
                  <div className="tbl-wrap">
                    <table className="tbl">
                      <thead>
                        <tr><th scope="col">{t("dashboard.topCreatives.creativeCol")}</th><th scope="col">{t("campaigns.headers.platform")}</th><th scope="col">{t("filters.format")}</th><th scope="col" className="num">{t("workbook.previewTable.impressions")}</th><th scope="col" className="num">{kpiName("ctr")}</th><th scope="col" className="num">{kpiName("roas")}</th></tr>
                      </thead>
                      <tbody>
                        {(details[expanded]?.top_creatives ?? []).map((c) => (
                          <tr key={c.creative_key}>
                            <td><span className="cell-main">{c.creative_key}</span></td>
                            <td>{platformLabel(c.platform)}</td>
                            <td>{c.format}</td>
                            <td className="num">{fmtCompact(num(c.metrics.impressions), locale)}</td>
                            <td className="num">{fmtCell(c.metrics.ctr, (n) => fmtPct(n * 100, 1, locale))}</td>
                            <td className="num">{fmtCell(c.metrics.roas, (n) => fmtMult(n, locale))}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {(details[expanded]?.recommendations ?? []).length ? (
                    <>
                      <h4 style={{ margin: "14px 0 8px", fontSize: 14 }}>{t("campaigns.recommendations")}</h4>
                      <ul className="rec-list">
                        {(details[expanded]?.recommendations ?? []).map((r) => <li key={r}>{r}</li>)}
                      </ul>
                    </>
                  ) : null}
                </>
              ) : detailErr[expanded] ? (
                <EmptyState text={detailErr[expanded]} />
              ) : <Skeleton height={160} />}
            </Panel>
          ) : null}
        </div>
        <Panel
          title={t("campaigns.recommendations")}
          action={<Link className="link-teal" to="/insights">{t("campaigns.seeAll")}</Link>}
        >
          {campaigns.data && benchPlatform.data ? (
            rail.length ? (
              <InsightList items={rail.map((r) => ({ icon: r.icon, tint: r.tint, title: r.title, body: r.body, action: r.action, href: r.href }))} />
            ) : <EmptyState compact verbatim icon="spark" title={t("campaigns.noRecsTitle")} text={t("campaigns.noRecsBody")} />
          ) : <Skeleton height={320} />}
        </Panel>
      </div>
    </div>
  );
}
