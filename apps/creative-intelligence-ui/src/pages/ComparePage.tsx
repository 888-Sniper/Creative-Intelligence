import { useEffect, useMemo, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { TrendChart } from "@/components/charts";
import {
  CreativeThumb,
  EmptyState,
  PageHeader,
  Panel,
  Skeleton,
  fmtCompact,
  fmtMoney,
  platformLabel,
  useScopedApi,
} from "@/components/product";

interface CompareAnnotation {
  hook_type?: string | null;
  creator_vs_branded?: string | null;
  edit_style?: string | null;
  status?: string | null;
}

interface CreativeSide {
  spend?: number | null;
  impressions?: number | null;
  clicks?: number | null;
  conversions?: number | null;
  cpm?: number | null;
  vtr?: number | null;
  view_rate?: number | null;
  ctr?: number | null;
  cpc?: number | null;
  cpa?: number | null;
  roas?: number | null;
  annotation?: CompareAnnotation | null;
}

/** A15: VTR is completions-based; the plays-based number reads Play Rate.
 *  UI copy rule: Title Case labels, true acronyms (CPA/CTR/…) stay caps. */
const KPI_LABELS: Record<string, string> = {
  vtr: "VTR (Completed)",
  view_rate: "Play Rate",
  spend: "Spend",
  impressions: "Impressions",
  clicks: "Clicks",
  conversions: "Conversions",
  video_views: "Video Views",
};
const kpiLabel = (k: string): string => KPI_LABELS[k] ?? k.toUpperCase();

interface AttributeRow {
  attribute: string;
  values?: Record<string, string | number | null>;
}

interface CompareResponse {
  keys: string[];
  ranking?: string[];
  winner?: string | null;
  rank_by?: string;
  scope?: string;
  why?: { top?: string | null; differences?: string[] };
  attributes?: AttributeRow[];
  [key: string]: unknown;
}

interface CampaignCompareResponse {
  kpis: Record<string, Record<string, number | null>>;
  ranking: string[];
  winner?: string | null;
  rank_by?: string;
  why?: { top?: string | null; differences?: string[] };
  scope?: string;
}

interface PeriodSide {
  label: string;
  from: string;
  to: string;
  n_ads: number;
  kpis: Record<string, number | null>;
}

interface PeriodResponse {
  a: PeriodSide;
  b: PeriodSide;
  delta: Record<string, number | null>;
  scope?: string;
}

interface DayPoint {
  date: string;
  impressions: number;
  clicks: number;
  spend: number;
  conversions: number;
  revenue: number;
}

interface CreativeMeta {
  creative_key: string;
  name?: string;
  platform?: string;
  campaigns?: string[];
  format?: string;
  duration_s?: number | null;
  annotation?: {
    hook_type?: string | null;
    duration_s?: number | null;
    creator_vs_branded?: string | null;
  } | null;
}

const CREATIVE_RANKS = ["cpa", "cpm", "vtr", "ctr", "cpc", "roas"];
const CAMPAIGN_RANKS = ["cpa", "cpm", "ctr", "vtr", "roas"];
const PERIOD_KPIS = ["spend", "impressions", "clicks", "conversions", "cpm", "vtr", "view_rate", "ctr", "cpc", "cpa", "roas"];
const CARD_KPIS = ["cpm", "ctr", "vtr", "cpa", "roas"] as const;
const DIFF_KPIS = ["cpm", "ctr", "vtr", "cpa", "roas"] as const;
const HIGHER_BETTER = new Set(["ctr", "vtr", "roas", "view_rate"]);
const COLORS = ["#2F6FBE", "#0E9F6E", "#7C6BD6", "#E8734A"];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v > 1 ? v : v * 100).toFixed(1)}%`;
}

function fmtCard(kpi: (typeof CARD_KPIS)[number], v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (kpi === "cpm" || kpi === "cpa") return fmtMoney(v);
  if (kpi === "roas") return `${v.toFixed(1)}x`;
  return fmtPct(v);
}

/* Period table values are formatted by unit — never dumped raw. Deltas
 * are absolute B−A differences with an explicit sign. */
function fmtPeriod(kpi: string, v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (kpi === "spend" || kpi === "cpm" || kpi === "cpc" || kpi === "cpa") return fmtMoney(v);
  if (kpi === "roas") return `${v.toFixed(2)}x`;
  if (kpi === "ctr" || kpi === "vtr" || kpi === "view_rate") return fmtPct(v);
  return fmtCompact(v);
}

function fmtDelta(kpi: string, v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v === 0) return fmtPeriod(kpi, 0);
  const sign = v > 0 ? "+" : "−";
  return `${sign}${fmtPeriod(kpi, Math.abs(v))}`;
}

function sideOf(data: CompareResponse, key: string): CreativeSide {
  const v = data[key];
  if (typeof v === "object" && v !== null) return v as CreativeSide;
  return {};
}

export function GroupedBars({ series, metric }: {
  series: Array<{ label: string; color: string; values: Record<string, number | null> }>;
  metric: string;
}) {
  // One metric, one scale: every bar shows the SELECTED metric for one
  // campaign. The previous renderer drew all five KPIs — currency,
  // percent and ratio values — against the selected metric's scale,
  // which clipped large units and shrank the selected metric to noise.
  const kpi = (DIFF_KPIS as readonly string[]).includes(metric) ? metric : "ctr";
  const vals = series.map((s) => s.values[kpi]).filter((v): v is number => v != null && Number.isFinite(v));
  const max = Math.max(...vals, 0) || 1;
  const W = 560, H = 200, PL = 52, PB = 34, PT = 16;
  const n = series.length || 1;
  const slot = (W - PL - 8) / n;
  const bw = Math.min(72, slot * 0.55);
  const y = (v: number) => PT + (H - PT - PB) * (1 - Math.min(Math.max(v, 0), max) / max);
  const tick = (f: number) => fmtCard(kpi as (typeof CARD_KPIS)[number], max * f);
  const short = (label: string) => {
    const room = Math.max(4, Math.floor(slot / 7.5));
    return label.length > room ? `${label.slice(0, room - 1)}…` : label;
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} role="img" aria-label={`${kpiLabel(kpi)} comparison chart`}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line x1={PL} x2={W - 8} y1={y(max * f)} y2={y(max * f)} stroke="#E3EAF3" strokeWidth={1} />
          <text x={PL - 6} y={y(max * f) + 3.5} textAnchor="end" fontSize={10} fill="#8CA0B5">
            {tick(f)}
          </text>
        </g>
      ))}
      {series.map((s, si) => {
        const v = s.values[kpi];
        const x = PL + si * slot + (slot - bw) / 2;
        return (
          <g key={s.label}>
            {v == null ? (
              <text x={x + bw / 2} y={y(0) - 6} textAnchor="middle" fontSize={11} fill="#8CA0B5">—</text>
            ) : (
              <>
                <rect x={x} y={y(v)} width={bw} height={Math.max(2, y(0) - y(v))}
                  rx={4} fill={s.color} />
                <text x={x + bw / 2} y={y(v) - 6} textAnchor="middle" fontSize={11} fontWeight={700} fill="#33475F">
                  {fmtCard(kpi as (typeof CARD_KPIS)[number], v)}
                </text>
              </>
            )}
            <text x={x + bw / 2} y={H - 8} textAnchor="middle" fontSize={10.5} fill="#8CA0B5">
              {short(s.label)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

interface ItemView {
  key: string;
  title: string;
  sub: string;
  meta: string;
  thumbSeed: string;
  duration: number | null;
  values: Record<string, number | null>;
}

const TEST_IDEAS: Record<string, (name: string) => { title: string; body: string }> = {
  ctr: (n) => ({ title: `Test ${n} With a Stronger Hook`, body: "Try a problem/solution hook and measure lift in CTR and ROAS." }),
  vtr: (n) => ({ title: `Shorten ${n} to 15 Seconds`, body: "Test a tighter edit to improve VTR while keeping key messaging." }),
  cpa: (n) => ({ title: `Refine Targeting for ${n}`, body: "Narrow the audience to lower CPA while protecting volume." }),
  cpm: (n) => ({ title: `Refresh Creative for ${n}`, body: "New opening visuals can lower CPMs by reducing fatigue." }),
  roas: (n) => ({ title: `Scale ${n} Carefully`, body: "Increase budget in steps and watch ROAS stability." }),
};

export function ComparePage() {
  const { scope } = useFilters();
  const [mode, setMode] = useState<"campaigns" | "creatives">("campaigns");
  const [picked, setPicked] = useState<string[]>([]);
  const [campaignRank, setCampaignRank] = useState("roas");
  const [creativeRank, setCreativeRank] = useState("roas");
  const [campaignData, setCampaignData] = useState<CampaignCompareResponse | null>(null);
  const [creativeData, setCreativeData] = useState<CompareResponse | null>(null);
  const [creativeKeys, setCreativeKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [perfMetric, setPerfMetric] = useState("roas");
  const [barMetric, setBarMetric] = useState("ctr");
  const [baseName, setBaseName] = useState("");
  const [dailyMap, setDailyMap] = useState<Record<string, DayPoint[]>>({});
  const [retMap, setRetMap] = useState<Record<string, Array<[number, number]>>>({});

  const [aFrom, setAFrom] = useState("");
  const [aTo, setATo] = useState("");
  const [bFrom, setBFrom] = useState("");
  const [bTo, setBTo] = useState("");
  const [periodData, setPeriodData] = useState<PeriodResponse | null>(null);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [periodError, setPeriodError] = useState("");

  const campaignOptions = useScopedApi<Record<string, Record<string, number>>>("/api/campaigns");
  const creativeOptions = useScopedApi<CreativeMeta[]>("/api/creatives");

  const rank = mode === "campaigns" ? campaignRank : creativeRank;
  const activeKeys = mode === "campaigns"
    ? (campaignData?.ranking ?? picked).slice(0, 4)
    : creativeKeys.slice(0, 4);

  async function runCampaigns(list: string[], rankBy: string): Promise<void> {
    const names = [...new Set(list.filter(Boolean))].slice(0, 4);
    if (names.length < 2) {
      setCampaignData(null);
      setError("Select at least two campaigns to compare.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("rank_by", rankBy);
      params.set("campaigns", names.join(","));
      const r = await api<CampaignCompareResponse>(
        "GET", scopedPath(`/api/compare/campaigns?${params.toString()}`, scope),
      );
      setCampaignData(r);
      setCreativeData(null);
      setBaseName(r.winner ?? r.ranking[0] ?? "");
    } catch (e) {
      setCampaignData(null);
      setError(e instanceof Error ? e.message : "Request Failed");
    } finally {
      setLoading(false);
    }
  }

  async function runCreatives(keys: string[], rankBy: string): Promise<void> {
    const seen = [...new Set(keys.filter(Boolean))].slice(0, 4);
    if (seen.length < 2) {
      setCreativeData(null);
      setCreativeKeys([]);
      setError("Select at least two creatives to compare.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      seen.forEach((k) => params.append("key", k));
      params.set("rank_by", rankBy);
      const r = await api<CompareResponse>("GET", scopedPath(`/api/compare?${params.toString()}`, scope));
      const ranked = Array.isArray(r.ranking) ? r.ranking : [];
      const sameSet = ranked.length === seen.length && ranked.every((k) => seen.includes(k));
      setCreativeKeys(sameSet ? ranked : seen);
      setCreativeData(r);
      setCampaignData(null);
      setBaseName(r.winner ?? (sameSet ? ranked[0] : seen[0]) ?? "");
    } catch (e) {
      setCreativeData(null);
      setError(e instanceof Error ? e.message : "Request Failed");
    } finally {
      setLoading(false);
    }
  }

  async function comparePeriods(): Promise<void> {
    if (!aFrom || !aTo || !bFrom || !bTo) {
      setPeriodError("Fill All Four Period Dates.");
      return;
    }
    setPeriodLoading(true);
    setPeriodError("");
    try {
      const params = new URLSearchParams({ a_from: aFrom, a_to: aTo, b_from: bFrom, b_to: bTo });
      const r = await api<PeriodResponse>(
        "GET", scopedPath(`/api/compare/periods?${params.toString()}`, scope),
      );
      setPeriodData(r);
    } catch (e) {
      setPeriodData(null);
      setPeriodError(e instanceof Error ? e.message : "Request Failed");
    } finally {
      setPeriodLoading(false);
    }
  }

  // Auto-run once the option lists arrive: top 4 campaigns by spend.
  const [booted, setBooted] = useState(false);
  useEffect(() => {
    if (booted || !campaignOptions.data || !creativeOptions.data) return;
    setBooted(true);
    const top = Object.entries(campaignOptions.data)
      .sort((a, b) => num(b[1].spend) - num(a[1].spend))
      .slice(0, 4)
      .map(([n]) => n);
    setPicked(top);
    void runCampaigns(top, "roas");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [booted, campaignOptions.data, creativeOptions.data]);

  // Per-campaign daily series for Performance Over Time.
  useEffect(() => {
    if (mode !== "campaigns" || !campaignData) return;
    const names = (campaignData.ranking ?? []).slice(0, 4);
    let live = true;
    void (async () => {
      const out: Record<string, DayPoint[]> = {};
      for (const name of names) {
        try {
          const params = new URLSearchParams(scope);
          params.delete("campaign");
          params.set("campaign", name);
          params.set("days", "30");
          const r = await api<{ days: DayPoint[] }>("GET", `/api/kpis/daily?${params.toString()}`);
          out[name] = r.days ?? [];
        } catch {
          out[name] = [];
        }
      }
      if (live) setDailyMap(out);
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, campaignData]);

  // Retention curves for creative mode.
  useEffect(() => {
    if (mode !== "creatives" || !creativeData) return;
    const keys = creativeKeys.slice(0, 4);
    let live = true;
    void (async () => {
      const out: Record<string, Array<[number, number]>> = {};
      for (const key of keys) {
        try {
          const r = await api<{ points: Array<{ t: number; p: number }> }>(
            "GET", `/api/retention/curve?creative_key=${encodeURIComponent(key)}`,
          );
          out[key] = (r.points ?? []).map((p) => [num(p.t), num(p.p)] as [number, number]);
        } catch {
          out[key] = [];
        }
      }
      if (live) setRetMap(out);
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, creativeData, creativeKeys]);

  const metaByKey = useMemo(() => {
    const m: Record<string, CreativeMeta> = {};
    for (const c of creativeOptions.data ?? []) m[c.creative_key] = c;
    return m;
  }, [creativeOptions.data]);

  const firstCreativeByCampaign = useMemo(() => {
    const m: Record<string, CreativeMeta> = {};
    for (const c of creativeOptions.data ?? []) {
      for (const camp of c.campaigns ?? []) {
        if (!m[camp]) m[camp] = c;
      }
    }
    return m;
  }, [creativeOptions.data]);

  const items: ItemView[] = useMemo(() => {
    if (mode === "campaigns") {
      if (!campaignData) return [];
      return (campaignData.ranking ?? []).slice(0, 4).map((name) => {
        const k = campaignData.kpis[name] ?? {};
        const rep = firstCreativeByCampaign[name];
        const days = Object.values(dailyMap).flat();
        const dates = days.map((d) => d.date).sort();
        return {
          key: name,
          title: name,
          sub: rep?.name ?? "Top Creative",
          meta: `${platformLabel(rep?.platform)} · ${dates.length ? `${dates[0].slice(5)} – ${dates[dates.length - 1].slice(5)}` : "Last 30 Days"}`,
          thumbSeed: rep?.creative_key ?? name,
          duration: rep?.annotation?.duration_s ?? rep?.duration_s ?? null,
          values: { cpm: k.cpm ?? null, ctr: k.ctr ?? null, vtr: k.vtr ?? null, cpa: k.cpa ?? null, roas: k.roas ?? null },
        };
      });
    }
    if (!creativeData) return [];
    return creativeKeys.slice(0, 4).map((key) => {
      const d = sideOf(creativeData, key);
      const meta = metaByKey[key];
      return {
        key,
        title: meta?.name || key,
        sub: (meta?.campaigns ?? [])[0] ?? "Unassigned",
        meta: `${platformLabel(meta?.platform)} · ${meta?.format ?? "Video"}`,
        thumbSeed: key,
        duration: meta?.annotation?.duration_s ?? meta?.duration_s ?? null,
        values: { cpm: d.cpm ?? null, ctr: d.ctr ?? null, vtr: d.vtr ?? null, cpa: d.cpa ?? null, roas: d.roas ?? null },
      };
    });
  }, [mode, campaignData, creativeData, creativeKeys, firstCreativeByCampaign, metaByKey, dailyMap]);

  const trendSeries = useMemo(() => {
    if (mode !== "campaigns") return [];
    const names = (campaignData?.ranking ?? []).slice(0, 4);
    return names.map((name, i) => ({
      label: name.length > 18 ? `${name.slice(0, 17)}…` : name,
      color: COLORS[i % COLORS.length],
      soft: "#E4EAF7",
      points: (dailyMap[name] ?? []).map((p) => {
        if (perfMetric === "roas") return p.spend ? p.revenue / p.spend : 0;
        if (perfMetric === "ctr") return p.impressions ? (p.clicks / p.impressions) * 100 : 0;
        if (perfMetric === "cpa") return p.conversions ? p.spend / p.conversions : 0;
        if (perfMetric === "cpm") return p.impressions ? (p.spend / p.impressions) * 1000 : 0;
        return num((p as unknown as Record<string, number>)[perfMetric]);
      }),
    }));
  }, [mode, campaignData, dailyMap, perfMetric]);

  const trendLabels = useMemo(() => {
    const names = (campaignData?.ranking ?? []).slice(0, 4);
    const first = names.map((n) => dailyMap[n] ?? []).find((d) => d.length);
    return (first ?? []).map((p) => p.date.slice(5));
  }, [campaignData, dailyMap]);

  const diffs = useMemo(() => {
    const base = items.find((i) => i.key === baseName) ?? items[0];
    if (!base) return [];
    return items
      .filter((i) => i.key !== base.key)
      .map((i) => {
        const rows = DIFF_KPIS.map((k) => {
          const a = i.values[k];
          const b = base.values[k];
          if (a == null || b == null || !b) return null;
          const pct = ((a - b) / Math.abs(b)) * 100;
          const good = HIGHER_BETTER.has(k) ? pct >= 0 : pct <= 0;
          const dir = pct > 0.5 ? "↑" : pct < -0.5 ? "↓" : "→";
          return {
            kpi: k,
            pct,
            dir,
            good,
            text: `${i.title} is ${Math.abs(pct).toFixed(0)}% ${pct >= 0 ? "higher" : "lower"} than ${base.title}`,
          };
        }).filter((r): r is NonNullable<typeof r> => r !== null);
        return { item: i, rows };
      });
  }, [items, baseName]);

  const takeaways = useMemo(() => {
    const data = mode === "campaigns" ? campaignData : creativeData;
    const out: string[] = [];
    if (data?.why?.top) out.push(data.why.top);
    for (const d of data?.why?.differences ?? []) {
      if (out.length >= 4) break;
      if (!out.includes(d)) out.push(d);
    }
    return out.slice(0, 4);
  }, [mode, campaignData, creativeData]);

  const tests = useMemo(() => {
    const base = items.find((i) => i.key === baseName) ?? items[0];
    if (!base) return [];
    return items
      .filter((i) => i.key !== base.key)
      .slice(0, 4)
      .map((i, idx) => {
        let worst: (typeof DIFF_KPIS)[number] = "ctr";
        let worstRatio = Infinity;
        for (const k of DIFF_KPIS) {
          const a = i.values[k];
          const b = base.values[k];
          if (a == null || b == null || !a || !b) continue;
          const ratio = HIGHER_BETTER.has(k) ? a / b : b / a;
          if (ratio < worstRatio) {
            worstRatio = ratio;
            worst = k;
          }
        }
        const idea = TEST_IDEAS[worst](i.title);
        return { n: idx + 1, color: COLORS[idx % COLORS.length], ...idea };
      });
  }, [items, baseName]);

  const attributes = useMemo(() => {
    if (mode === "creatives" && creativeData?.attributes?.length) {
      return creativeData.attributes;
    }
    const rows: AttributeRow[] = [
      { attribute: "Hook Type", values: {} },
      { attribute: "Duration", values: {} },
      { attribute: "Creator vs Branded", values: {} },
      { attribute: "Format", values: {} },
      { attribute: "Platform", values: {} },
    ];
    for (const item of items) {
      const rep = mode === "campaigns" ? firstCreativeByCampaign[item.key] : metaByKey[item.key];
      const vals = [rep?.annotation?.hook_type?.replace(/_/g, " ") ?? "—",
        rep?.annotation?.duration_s ?? rep?.duration_s ? `${rep?.annotation?.duration_s ?? rep?.duration_s}s` : "—",
        rep?.annotation?.creator_vs_branded ?? "—",
        rep?.format ?? "—",
        platformLabel(rep?.platform)];
      rows.forEach((r, i) => {
        r.values = { ...(r.values ?? {}), [item.key]: vals[i] };
      });
    }
    return rows;
  }, [mode, creativeData, items, firstCreativeByCampaign, metaByKey]);

  const addOption = (v: string) => {
    if (!v || picked.includes(v) || picked.length >= 4) return;
    setPicked((p) => [...p, v]);
  };
  const removeOption = (v: string) => setPicked((p) => p.filter((x) => x !== v));

  const apply = () => {
    if (mode === "campaigns") void runCampaigns(picked, campaignRank);
    else void runCreatives(picked, creativeRank);
  };

  const switchMode = (m: "campaigns" | "creatives") => {
    setMode(m);
    setPicked([]);
    setCampaignData(null);
    setCreativeData(null);
    setError("");
  };

  const options = mode === "campaigns"
    ? Object.keys(campaignOptions.data ?? {})
    : (creativeOptions.data ?? []).map((c) => c.creative_key);
  const optionLabel = (v: string) => {
    if (mode === "campaigns") return v;
    return metaByKey[v]?.name || v;
  };

  const barSeries = items.map((item, i) => ({
    label: item.title,
    color: COLORS[i % COLORS.length],
    values: item.values,
  }));

  return (
    <>
      <PageHeader
        title="Compare"
        sub="Compare campaigns or creatives side by side to find what drives the best performance."
      />
      <div className="cmp-setup-bar" role="group" aria-label="Comparison setup">
        <div className="cmp-setup">
          <div className="field">
            <label htmlFor="cmp-mode">Compare By</label>
            <select id="cmp-mode" value={mode} onChange={(e) => switchMode(e.target.value as typeof mode)}>
              <option value="campaigns">Campaigns</option>
              <option value="creatives">Creatives</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="cmp-add">{mode === "campaigns" ? "Select Campaigns" : "Select Creatives"}</label>
            <div className="chip-row" style={{ marginBottom: picked.length ? 8 : 0 }}>
              {picked.map((p, i) => (
                <span key={p} className="chip" style={{ cursor: "default" }}>
                  <i style={{ width: 8, height: 8, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
                  {optionLabel(p)}
                  <button type="button" aria-label={`Remove ${optionLabel(p)}`} onClick={() => removeOption(p)}
                    style={{ background: "none", border: 0, cursor: "pointer", display: "inline-flex", color: "inherit" }}>
                    <Icon name="x" size={12} />
                  </button>
                </span>
              ))}
            </div>
            <select id="cmp-add" value="" onChange={(e) => { addOption(e.target.value); e.target.value = ""; }}>
              <option value="">{mode === "campaigns" ? "Add a campaign…" : "Add a creative…"}</option>
              {options.filter((o) => !picked.includes(o)).map((o) => (
                <option key={o} value={o}>{optionLabel(o)}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="cmp-rank">Rank By KPI</label>
            <select
              id="cmp-rank"
              value={rank}
              onChange={(e) => (mode === "campaigns" ? setCampaignRank(e.target.value) : setCreativeRank(e.target.value))}
            >
              {(mode === "campaigns" ? CAMPAIGN_RANKS : CREATIVE_RANKS).map((r) => (
                <option key={r} value={r}>{kpiLabel(r)}</option>
              ))}
            </select>
          </div>
          <LoadingButton type="button" className="btn-primary" loading={loading} loadingLabel="Comparing…" disabled={loading} onClick={apply}>
            Apply Comparison
          </LoadingButton>
        </div>
      </div>
      {error ? <p className="panel-sub" role="alert" style={{ margin: "12px 0 0" }}>{error}</p> : null}
      {loading && !items.length ? (
        <div className="cmp-grid-4" style={{ marginTop: 16 }}>
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={300} />)}
        </div>
      ) : null}
      {items.length ? (
        <>
          <div className="cmp-grid-4" style={{ marginTop: 12 }}>
            {items.map((item, i) => (
              <div className="cmp-card" key={item.key} style={{ borderTop: `4px solid ${COLORS[i % COLORS.length]}`, padding: 14 }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
                  <CreativeThumb seed={item.thumbSeed} duration={item.duration} label={item.title} />
                  <div>
                    <h4 style={{ margin: 0, fontSize: 14 }}>{item.title}</h4>
                    <p className="panel-sub" style={{ margin: "2px 0" }}>{item.sub}</p>
                    <p className="panel-sub" style={{ margin: 0 }}>{item.meta}</p>
                  </div>
                </div>
                <table className="tbl">
                  <tbody>
                    {CARD_KPIS.map((k) => (
                      <tr key={k}>
                        <th scope="row" style={{ border: 0, padding: "3px 0", textTransform: "none", letterSpacing: 0 }}>{kpiLabel(k)}</th>
                        <td className="num" style={{ border: 0, padding: "3px 0", fontWeight: 700 }}>{fmtCard(k, item.values[k])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <div className="cmp-trio">
            <Panel
              title={mode === "campaigns" ? "Performance Over Time" : "Retention Curves"}
              action={mode === "campaigns" ? (
                <select aria-label="Trend metric" value={perfMetric} onChange={(e) => setPerfMetric(e.target.value)}>
                  {["roas", "ctr", "cpa", "cpm", "spend"].map((m) => <option key={m} value={m}>{kpiLabel(m)}</option>)}
                </select>
              ) : undefined}
            >
              {mode === "campaigns" ? (
                trendSeries.some((s) => s.points.length) ? (
                  <>
                    <TrendChart series={trendSeries} labels={trendLabels} />
                    <div className="legend">
                      {trendSeries.map((s) => (
                        <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
                      ))}
                    </div>
                  </>
                ) : <EmptyState text="No daily data for the selected campaigns." />
              ) : (
                <TrendChart
                  series={activeKeys.map((k, i) => ({
                    label: optionLabel(k),
                    color: COLORS[i % COLORS.length],
                    soft: "#E4EAF7",
                    points: (retMap[k] ?? []).map((p) => p[1]),
                  }))}
                  labels={(retMap[activeKeys[0]] ?? []).map((p) => `${Math.round(p[0])}s`)}
                />
              )}
            </Panel>
            <Panel
              title="KPI Comparison"
              action={(
                <select aria-label="Comparison metric" value={barMetric} onChange={(e) => setBarMetric(e.target.value)}>
                  {DIFF_KPIS.map((m) => <option key={m} value={m}>{kpiLabel(m)}</option>)}
                </select>
              )}
            >
              <GroupedBars series={barSeries} metric={barMetric} />
              <div className="legend">
                {barSeries.map((s) => (
                  <span key={s.label}><i style={{ background: s.color }} />{s.label.length > 16 ? `${s.label.slice(0, 15)}…` : s.label}</span>
                ))}
              </div>
            </Panel>
            <Panel
              title="Difference Summary"
              action={(
                <select aria-label="Comparison baseline" value={baseName} onChange={(e) => setBaseName(e.target.value)}>
                  {items.map((i) => <option key={i.key} value={i.key}>vs. {i.title}</option>)}
                </select>
              )}
            >
              {diffs.length ? (
                <div style={{ display: "grid", gap: 10 }}>
                  {diffs.map((d) => (
                    <div key={d.item.key}>
                      {(["cpm", "ctr", "vtr", "cpa", "roas"] as const).map((k) => {
                        const r = d.rows.find((x) => x.kpi === k);
                        if (!r) return null;
                        return (
                          <div key={k} style={{ display: "flex", gap: 8, alignItems: "baseline", padding: "4px 0" }}>
                            <span className="panel-sub" style={{ width: 44 }}>{kpiLabel(k)}</span>
                            <strong style={{ color: r.good ? "#0E7C5B" : "#C2410C", minWidth: 52 }}>
                              {r.dir} {Math.abs(r.pct).toFixed(0)}%
                            </strong>
                            <span className="panel-sub">{r.text}</span>
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="Select a baseline to compare differences." />}
            </Panel>
          </div>
          <div className="cmp-trio">
            <Panel title="Creative Attributes Comparison">
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th scope="col">Attribute</th>
                      {items.map((i) => <th scope="col" key={i.key}>{i.title}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {attributes.map((row) => (
                      <tr key={row.attribute}>
                        <th scope="row">{row.attribute}</th>
                        {items.map((i) => (
                          <td key={i.key}>{String(row.values?.[i.key] ?? "—")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel title="Key Takeaways">
              {takeaways.length ? (
                <div>
                  {takeaways.map((t) => (
                    <div className="insight" key={t}>
                      <span className="insight-ico" style={{ background: "#E5F5F2" }}>
                        <Icon name="check" size={18} />
                      </span>
                      <div><p style={{ color: "var(--shell-navy)" }}>{t}</p></div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="Run a comparison to generate takeaways." />}
            </Panel>
            <Panel title="Recommended Next Tests">
              {tests.length ? (
                <div>
                  {tests.map((t) => (
                    <div className="insight" key={t.title}>
                      <span className="insight-ico" style={{ background: t.color, color: "#fff", fontWeight: 800 }}>
                        {t.n}
                      </span>
                      <div>
                        <h4>{t.title}</h4>
                        <p>{t.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="Run a comparison to generate test ideas." />}
            </Panel>
          </div>
        </>
      ) : !loading ? (
        <Panel title="No Comparison Yet">
          <EmptyState
            compact
            icon="compare"
            title="Select at least two campaigns to compare"
            text="Pick two to four campaigns or creatives above, then Apply Comparison."
          />
        </Panel>
      ) : null}
      <details className="panel" style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontSize: 16.5, fontWeight: 700, color: "var(--shell-navy)" }}>
          Advanced: Period Comparison
          <span className="panel-sub" style={{ display: "block", fontWeight: 400 }}>
            Period A vs Period B over the identical scoped population.
          </span>
        </summary>
        <div className="filter-grid fg-4" style={{ marginTop: 12 }}>
          <div className="field">
            <label htmlFor="cp-afrom">A From</label>
            <input id="cp-afrom" type="date" value={aFrom} onChange={(e) => setAFrom(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="cp-ato">A To</label>
            <input id="cp-ato" type="date" value={aTo} onChange={(e) => setATo(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="cp-bfrom">B From</label>
            <input id="cp-bfrom" type="date" value={bFrom} onChange={(e) => setBFrom(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="cp-bto">B To</label>
            <input id="cp-bto" type="date" value={bTo} onChange={(e) => setBTo(e.target.value)} />
          </div>
        </div>
        <div className="filter-actions">
          <LoadingButton type="button" className="btn-primary" loading={periodLoading} loadingLabel="Comparing Periods…" disabled={periodLoading} onClick={() => void comparePeriods()}>
            Compare Periods
          </LoadingButton>
        </div>
        <div style={{ marginTop: 8 }}>
          {periodLoading ? <Skeleton height={120} /> : null}
          {periodError && !periodLoading ? <EmptyState text={periodError} /> : null}
          {periodData && !periodLoading ? (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th scope="col">KPI</th>
                    <th scope="col">{periodData.a.label} ({periodData.a.from}…{periodData.a.to}, n={periodData.a.n_ads})</th>
                    <th scope="col">{periodData.b.label} ({periodData.b.from}…{periodData.b.to}, n={periodData.b.n_ads})</th>
                    <th scope="col" className="num">B−A</th>
                  </tr>
                </thead>
                <tbody>
                  {PERIOD_KPIS.map((m) => (
                    <tr key={m}>
                      <th scope="row">{kpiLabel(m)}</th>
                      <td>{fmtPeriod(m, periodData.a.kpis[m])}</td>
                      <td>{fmtPeriod(m, periodData.b.kpis[m])}</td>
                      <td className="num">{fmtDelta(m, periodData.delta[m])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : !periodLoading && !periodError ? (
            <EmptyState text="Fill all four period dates, then Compare Periods." />
          ) : null}
        </div>
      </details>
    </>
  );
}

