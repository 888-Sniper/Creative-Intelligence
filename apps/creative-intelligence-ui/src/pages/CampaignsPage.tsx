import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
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
  fmtCompact,
  fmtMoney,
  fmtMult,
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
        icon: "trend", tint: "#E5F5F2",
        title: "Scale High-Performing Campaigns",
        body: `${platformLabel(plats[0].key)} campaigns average ${(plats[0].roas ?? 0).toFixed(1)}x ROAS${d != null ? `, ${d >= 0 ? "+" : ""}${d.toFixed(0)}% above the platform average` : ""}. Consider increasing budget allocation.`,
        action: "View Campaigns", href: "/campaigns",
      });
    }
    if (underperformers.length) {
      items.push({
        icon: "users", tint: "#E5F5F2",
        title: "Improve Underperforming Creatives",
        body: `${underperformers.length} campaign${underperformers.length === 1 ? " is" : "s are"} underperforming on CTR versus the ${avgCtr == null ? "" : `${avgCtr.toFixed(1)}% `}scope average. Refresh creative assets to improve engagement.`,
        action: "View Recommendations", href: "/creatives",
      });
    }
    const hookRows = Object.entries(benchHook.data ?? {})
      .map(([key, g]) => ({ key, ctr: g.ctr == null ? null : g.ctr * 100 }))
      .filter((r) => r.ctr != null)
      .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    if (hookRows[0]?.ctr != null) {
      items.push({
        icon: "spark", tint: "#E7F1FB",
        title: "Optimize for Video Content",
        body: `${hookRows[0].key.replace(/_/g, " ")} openings lead the current scope at ${(hookRows[0].ctr ?? 0).toFixed(1)}% CTR. Lead with the strongest hook in the first 3 seconds.`,
        action: "See Insights", href: "/insights",
      });
    }
    const topRoas = rows
      .filter((r) => r.roas != null)
      .sort((a, b) => (b.roas ?? 0) - (a.roas ?? 0))[0];
    if (topRoas?.roas != null) {
      items.push({
        icon: "target", tint: "#E5F5F2",
        title: "Refine Audience Targeting",
        body: `${topRoas.name} leads the current scope at ${topRoas.roas.toFixed(1)}x ROAS. Mirror its audience and hook formula in the next flight.`,
        action: "View Details", href: "/compare",
      });
    }
    return items.slice(0, 4);
  }, [benchPlatform.data, benchHook.data, underperformers, avgCtr, rows]);

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
      setBanner("Select At Least One Campaign To Compare.");
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
      setBanner("Nothing To Export For The Current Filters.");
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
      setBanner(`Exported ${names.length} Campaign${names.length === 1 ? "" : "s"}.`);
    } catch (e) {
      setBanner(e instanceof Error ? e.message : "Export Failed");
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
  const fmtBench = (v: number | null) => {
    if (v == null) return "—";
    const k = kpiKey;
    if (k === "roas") return `${v.toFixed(1)}x`;
    if (k === "spend" || k === "cpa" || k === "cpc") return fmtMoney(v);
    if (k === "ctr") return `${(v * 100).toFixed(1)}%`;
    return fmtCompact(v);
  };

  return (
    <div className="campaigns">
      <PageHeader
        title="Campaigns"
        sub="Plan, monitor, and optimize your creative campaigns with real-time insights."
        actions={(
          <>
            <button type="button" className="link-teal" onClick={resetAll}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> Reset Filters
            </button>
            <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
              Apply Filters
            </button>
          </>
        )}
      />
      {/* Approved composition goes straight into the controls:
        no extra "Campaign Filters" heading. */}
      <section className="panel" aria-label="Campaign Filters">
        <div className="filter-grid">
          <div className="field">
            <label htmlFor="c-client">Client</label>
            <select id="c-client" {...selectProps("client")}>
              <option value="">All Clients</option>
              {metaClients.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field">
            {/* Status stays activity-derived (not the ad platform's own
              status); the explainer lives on an info icon beside the
              short label so the card stays shallow. The icon sits
              outside the label element to keep its accessible name
              exactly "Campaign Status". */}
            <span style={{ display: "flex", alignItems: "center", gap: 6, margin: "0 0 6px" }}>
              <label htmlFor="c-status" style={{ margin: 0 }}>Campaign Status</label>
              <InfoTip label="How Campaign Status Is Determined"
                text="Activity-derived status from recent ad activity — not the ad platform's own campaign status." />
            </span>
            <select id="c-status" value={filters.status || "all"}
              title="Activity-derived status from recent ad activity — not the ad platform's own campaign status."
              onChange={(e) => setFilter("status", e.target.value === "all" ? "" : e.target.value)}>
              <option value="all">All Statuses</option>
              <option value="Active">Active</option>
              <option value="Completed">Completed</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-platform">Platform</label>
            <select id="c-platform" {...selectProps("platform")}>
              <option value="">All Platforms</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-objective">Campaign Objective</label>
            <select id="c-objective" {...selectProps("objective")}>
              <option value="">All Objectives</option>
              {metaObjectives.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-team">Team</label>
            <select id="c-team" {...selectProps("team")}>
              <option value="">All Teams</option>
              {metaTeams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-market">Market</label>
            <select id="c-market" {...selectProps("market")}>
              <option value="">All Markets</option>
              {metaMarkets.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <DateRangeField id="c-date" />
          <div className="field">
            <label htmlFor="c-spend">Spend Range</label>
            <select id="c-spend" value={spendBand} onChange={(e) => setSpendBand(e.target.value)}>
              <option value="all">All Spend Ranges</option>
              <option value="under">Under $25K</option>
              <option value="mid">$25K – $50K</option>
              <option value="over">Over $50K</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-kpi">KPI Focus</label>
            <select id="c-kpi" {...selectProps("kpi")} value={filters.kpi === "all" ? "" : filters.kpi}>
              <option value="">All KPIs</option>
              <option value="impressions">Impressions</option>
              <option value="clicks">Clicks</option>
              <option value="spend">Spend</option>
              <option value="conversions">Conversions</option>
              <option value="ctr">CTR</option>
              <option value="cpa">CPA</option>
              <option value="roas">ROAS</option>
            </select>
          </div>
          <div className="field">
            <span className="field-label" aria-hidden="true">&nbsp;</span>
            <button type="button" className="filter-toggle" onClick={() => setMoreFilters((v) => !v)}
              aria-expanded={moreFilters}>
              {moreFilters ? "Fewer Filters" : "More Filters"}
              <Icon name="chev" size={13} />
            </button>
          </div>
          {moreFilters ? (
            <>
              <div className="field">
                <label htmlFor="c-project">Project</label>
                <select id="c-project" value={filters.project === "all" ? "" : filters.project} onChange={(e) => setFilter("project", e.target.value)}>
                  <option value="">All Projects</option>
                  {metaProjects.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="c-vertical">Vertical</label>
                <select id="c-vertical" value={filters.vertical === "all" ? "" : filters.vertical} onChange={(e) => setFilter("vertical", e.target.value)}>
                  <option value="">All Verticals</option>
                  {metaVerticals.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="c-funnel">Funnel Stage</label>
                <select id="c-funnel" value={filters.funnel === "all" ? "" : filters.funnel} onChange={(e) => setFilter("funnel", e.target.value)}>
                  <option value="">All Stages</option>
                  <option value="upper">Upper</option>
                  <option value="mid">Mid</option>
                  <option value="lower">Lower</option>
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
                <span className="kpi-ico" style={{ background: "#E4F4ED", color: "#0E7C5B" }}>
                  <Icon name="users" size={20} />
                </span>
                <div className="kpi-body">
                  <div className="kpi-label">Total Campaigns</div>
                  <div className="kpi-value">{rows.length}</div>
                </div>
              </div>
              <KpiCard label="Total Impressions" display={fmtCompact(num(compare.metrics.impressions?.current))}
                icon="megaphone" tint="#E5F5F2" metricLabel="Impressions" compare={compare} />
              <KpiCard label="Total Clicks" display={fmtCompact(num(compare.metrics.clicks?.current))}
                icon="click" tint="#E7F1FB" metricLabel="Clicks" compare={compare} />
              <KpiCard label="Average ROAS" display={fmtMult(num(compare.metrics.roas?.current))}
                icon="coin" tint="#E4F4ED" metricLabel="ROAS" compare={compare} />
            </div>
          ) : compareError ? (
            <div className="panel"><EmptyState text={compareError} /></div>
          ) : (
            <div className="kpi-grid">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={118} />)}
            </div>
          )}
          <div className="cols-2">
            <Panel title="Campaign Performance Trends">
              {daily ? (
                <TrendChart
                  height={200}
                  series={[
                    { label: "Impressions", color: "#0A9183", soft: "#E5F5F2", points: daily.map((p) => num(p.impressions)) },
                    { label: "Clicks", color: "#1D3A8F", soft: "#E4EAF7", points: daily.map((p) => num(p.clicks)), axis: "right" },
                  ]}
                  labels={daily.map((p) => p.date.slice(5))}
                />
              ) : <Skeleton height={200} />}
            </Panel>
            <Panel
              title="Campaign Performance by Platform"
              action={(
                <select aria-label="Platform Metric" value={platMetric}
                  onChange={(e) => setPlatMetric(e.target.value as typeof platMetric)}>
                  {PLATFORM_METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              )}
            >
              {benchPlatform.data ? (
                platGroups.length ? (
                  <GroupBars
                    height={200}
                    groups={platGroups}
                    format={(v) => platMetric === "spend" ? fmtMoney(v) : fmtCompact(v)}
                  />
                ) : <EmptyState compact icon="bars" title="No platform data" text="Platform breakdown appears once campaign data is in scope." />
              ) : <Skeleton height={200} />}
            </Panel>
          </div>
          <Panel
            title={`All Campaigns (${rows.length})`}
            action={(
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <input
                  aria-label="Search Campaigns"
                  placeholder="Search Campaigns…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ width: 200 }}
                />
                <button type="button" className="btn-outline" onClick={onCompare}>
                  Compare Selected ({selected.size})
                </button>
                <LoadingButton type="button" className="btn-outline" loading={exportBusy} loadingLabel="Exporting…" spinnerClass="spinner dark" disabled={exportBusy} onClick={() => void onExport()}>
                  <Icon name="download" size={15} /> Export
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
                        <th scope="col"><input type="checkbox" aria-label="Select All Campaigns" checked={allChecked} onChange={toggleAll} /></th>
                        <th scope="col">Campaign</th>
                        <th scope="col">Client</th>
                        <th scope="col">Platform</th>
                        <th scope="col">Status</th>
                        <th scope="col" className="num">Impressions</th>
                        <th scope="col" className="num">Clicks</th>
                        <th scope="col" className="num">CTR</th>
                        <th scope="col" className="num">Spend</th>
                        <th scope="col" className="num">ROAS</th>
                        <th scope="col" className="num">vs. Benchmark</th>
                        <th scope="col"><span className="sr-only">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.name}>
                          <td>
                            <input type="checkbox" aria-label={`Select ${r.name}`}
                              checked={selected.has(r.name)} onChange={() => toggle(r.name)} />
                          </td>
                          <td><span className="cell-main">{r.name}</span></td>
                          <td>{metaMap.get(r.name)?.client || "—"}</td>
                          <td>{(metaMap.get(r.name)?.platforms ?? []).map(platformLabel).join(", ") || "—"}</td>
                          <td>{metaMap.get(r.name)?.status ? (
                            <span className={`badge ${metaMap.get(r.name)?.status === "Active" ? "good" : "bad"}`}>
                              {metaMap.get(r.name)?.status}
                            </span>
                          ) : "—"}</td>
                          <td className="num">{fmtCompact(num(r.impressions))}</td>
                          <td className="num">{fmtCompact(num(r.clicks))}</td>
                          <td className="num">{r.ctr == null ? "—" : `${(r.ctr * 100).toFixed(1)}%`}</td>
                          <td className="num">{fmtMoney(num(r.spend))}</td>
                          <td className="num">{r.roas == null ? "—" : `${r.roas.toFixed(1)}x`}</td>
                          <td className="num">{fmtBench(benchVal)}</td>
                          <td>
                            <button type="button" className="icon-btn" aria-expanded={expanded === r.name}
                              aria-label={`Details for ${r.name}`}
                              onClick={() => setExpanded((cur) => (cur === r.name ? null : r.name))}>
                              <Icon name="dots" size={18} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState compact icon="campaign" title="No campaigns match" text="Try loosening the current filters." />
            ) : campaigns.error ? (
              <EmptyState text={campaigns.error} />
            ) : <Skeleton height={220} />}
          </Panel>
          {expanded ? (
            <Panel title={expanded}>
              {details[expanded] ? (
                <>
                  <div className="detail-grid">
                    <div><span>Impressions</span><strong>{fmtCompact(num(details[expanded]?.totals.impressions))}</strong></div>
                    <div><span>Clicks</span><strong>{fmtCompact(num(details[expanded]?.totals.clicks))}</strong></div>
                    <div><span>Spend</span><strong>{fmtMoney(num(details[expanded]?.totals.spend))}</strong></div>
                    <div><span>ROAS</span><strong>{details[expanded]?.totals.roas == null ? "—" : `${details[expanded]?.totals.roas.toFixed(1)}x`}</strong></div>
                    <div><span>CTR</span><strong>{details[expanded]?.totals.ctr == null ? "—" : `${(details[expanded]?.totals.ctr as number * 100).toFixed(1)}%`}</strong></div>
                    <div><span>Conversions</span><strong>{fmtCompact(num(details[expanded]?.totals.conversions))}</strong></div>
                  </div>
                  <h4 style={{ margin: "14px 0 8px", fontSize: 14 }}>Top Creatives</h4>
                  <div className="tbl-wrap">
                    <table className="tbl">
                      <thead>
                        <tr><th scope="col">Creative</th><th scope="col">Platform</th><th scope="col">Format</th><th scope="col" className="num">Impr.</th><th scope="col" className="num">CTR</th><th scope="col" className="num">ROAS</th></tr>
                      </thead>
                      <tbody>
                        {(details[expanded]?.top_creatives ?? []).map((c) => (
                          <tr key={c.creative_key}>
                            <td><span className="cell-main">{c.creative_key}</span></td>
                            <td>{platformLabel(c.platform)}</td>
                            <td>{c.format}</td>
                            <td className="num">{fmtCompact(num(c.metrics.impressions))}</td>
                            <td className="num">{c.metrics.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</td>
                            <td className="num">{c.metrics.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {(details[expanded]?.recommendations ?? []).length ? (
                    <>
                      <h4 style={{ margin: "14px 0 8px", fontSize: 14 }}>Recommendations</h4>
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
          title="Campaign Insights & Recommendations"
          action={<Link className="link-teal" to="/insights">See All</Link>}
        >
          {campaigns.data && benchPlatform.data ? (
            rail.length ? (
              <InsightList items={rail.map((r) => ({ icon: r.icon, tint: r.tint, title: r.title, body: r.body, action: r.action, href: r.href }))} />
            ) : <EmptyState compact icon="spark" title="No recommendations yet" text="Recommendations appear once campaign data is in scope." />
          ) : <Skeleton height={320} />}
        </Panel>
      </div>
    </div>
  );
}
