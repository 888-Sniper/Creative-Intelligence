import { useCallback, useEffect, useRef, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { scopeParams, useFilters } from "@/state/FilterContext";
import { KpiTrend } from "@/components/KpiTrend";
import type { KpiComparison, KpiPeriod } from "@/components/KpiTrend";
import { Icon } from "@/components/icons";

/* ---------- formatting (display only; calculations stay backend-side) --- */
export function fmtCompact(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return `${Math.round(n)}`;
}
export function fmtMoney(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}
export function fmtMult(n: number): string {
  return `${n.toFixed(1)}x`;
}
export function fmtPct(n: number, digits = 1): string {
  return `${n.toFixed(digits)}%`;
}
/** Count-aware unit: plural(1, "Campaign") is "1 Campaign",
 *  plural(2, "Campaign") is "2 Campaigns". Pass an explicit plural
 *  for irregular nouns (plural(1, "KPI", "KPIs")). */
export function plural(n: number, one: string, many?: string): string {
  const m = many ?? `${one}s`;
  return `${n} ${n === 1 ? one : m}`;
}

/* ------------------------- backend data hooks -------------------------- */
interface CompareMetric extends KpiComparison {
  current: number | null;
  previous: number | null;
  abs_change: number | null;
}
export interface CompareResp {
  current_period: KpiPeriod | null;
  previous_period: KpiPeriod | null;
  comparison: string | null;
  metrics: Record<string, CompareMetric>;
}
export function useCompareState(refreshKey = 0): {
  data: CompareResp | null; error: string; loading: boolean;
} {
  const { filters } = useFilters();
  const [data, setData] = useState<CompareResp | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api<CompareResp>("GET", scopedPath("/api/kpis/compare", scopeParams(filters)))
      .then((r) => {
        if (!live) return;
        setData(r);
        setError("");
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => { live = false; };
  }, [filters, refreshKey]);
  return { data, error, loading: data === null && error === "" };
}

export function useCompare(refreshKey = 0) {
  return useCompareState(refreshKey).data;
}
export interface DayPoint {
  date: string; impressions: number; clicks: number; spend: number;
  conversions: number; revenue: number;
}
export function useDaily(days = 30, refreshKey = 0) {
  const { filters } = useFilters();
  const [points, setPoints] = useState<DayPoint[] | null>(null);
  useEffect(() => {
    let live = true;
    const scope = scopeParams(filters);
    scope.set("days", String(days));
    api<{ days: DayPoint[] }>("GET", scopedPath("/api/kpis/daily", scope))
      .then((r) => live && setPoints(r.days))
      .catch(() => live && setPoints([]));
    return () => { live = false; };
  }, [filters, days, refreshKey]);
  return points;
}

export function scopeBody(scope: URLSearchParams): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const key of new Set(scope.keys())) {
    const vals = scope.getAll(key);
    if (vals.length) out[key] = vals;
  }
  return out;
}

/* Shared fetch states are explicit: loading / ready / empty / error.
 * Hooks return all three signals so pages never render an API failure
 * as a permanent skeleton. */
export function useScopedApi<T>(path: string, refreshKey = 0) {
  const { filters } = useFilters();
  const scopeKey = scopeParams(filters).toString();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    api<T>("GET", scopedPath(path, new URLSearchParams(scopeKey)))
      .then((r) => live && setData(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, scopeKey, refreshKey]);
  return { data, error, loading: data === null && error === "" };
}

export function platformLabel(value: string | null | undefined): string {
  const v = (value ?? "").toString().trim().toLowerCase();
  if (v === "meta") return "Meta";
  if (v === "tiktok") return "TikTok";
  if (!v) return "—";
  return v.split(/[\s_-]+/).map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

/** Honest two-way comparison at display precision: "lead" only when a
 *  is strictly ahead of b as printed, "tie" when the UI shows the same
 *  number, "trail" otherwise, "unknown" when either side is missing.
 *  Headings built from this can never contradict their own numbers. */
export function compareDisplayed(a: number, b: number, digits = 1): "lead" | "tie" | "trail" | "unknown" {
  if (!Number.isFinite(a) || !Number.isFinite(b)) return "unknown";
  if (a.toFixed(digits) === b.toFixed(digits)) return "tie";
  return a > b ? "lead" : "trail";
}

export function formatDuration(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function CreativeThumb({ seed, duration, label }: {
  seed: string; duration?: number | null; label?: string;
}) {
  const [imgOk, setImgOk] = useState(true);
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) % 360;
  const hue = (hash + 360) % 360;
  // Sample thumbnail asset; the gradient stays as the genuine fallback
  // when no image is available (unknown creative, backend error).
  const src = `/api/creatives/${encodeURIComponent(seed)}/thumbnail`;
  return (
    <span className="thumb-wrap" role="img" aria-label={label ? `${label} Thumbnail` : "Creative Thumbnail"}>
      <span
        className="thumb thumb-art"
        aria-hidden="true"
        style={{
          background:
            `linear-gradient(135deg, hsl(${hue}, 42%, 76%) 0%, hsl(${(hue + 48) % 360}, 48%, 55%) 58%, hsl(${(hue + 96) % 360}, 42%, 38%) 100%)`,
        }}
      >
        {imgOk ? (
          <img src={src} alt="" aria-hidden="true" loading="lazy"
            onError={() => setImgOk(false)} />
        ) : null}
      </span>
      {duration != null ? <span className="thumb-dur">{formatDuration(duration)}</span> : null}
    </span>
  );
}

/* ------------------------------ page head ------------------------------ */
export function PageHeader({ title, sub, actions }: {
  title: string; sub?: string; actions?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub ? <p className="sub">{sub}</p> : null}
      </div>
      {actions ? <div className="head-actions">{actions}</div> : null}
    </div>
  );
}

/* ----------------------------- filter panel ---------------------------- */
/* Explicit {value,label} pairs for every selector axis. Machine values
 * are the backend-compatible scope tokens; labels are display only.
 * Never derive one from the other by case-folding (that produced the
 * Meta/meta class of mismatch where the controlled select held a value
 * no <option> carried). An empty value always means "All". */
export interface AxisOption { value: string; label: string; }
const PLATFORMS: AxisOption[] = [
  { value: "", label: "All Platforms" },
  { value: "meta", label: "Meta" },
  { value: "tiktok", label: "TikTok" },
];
const FUNNELS: AxisOption[] = [
  { value: "", label: "All Stages" },
  { value: "upper", label: "Upper" },
  { value: "mid", label: "Mid" },
  { value: "lower", label: "Lower" },
];
const OBJECTIVES: AxisOption[] = [
  { value: "", label: "All Objectives" },
  { value: "conversions", label: "Conversions" },
  { value: "traffic", label: "Traffic" },
  { value: "leads", label: "Leads" },
  { value: "awareness", label: "Awareness" },
  { value: "video_views", label: "Video Views" },
  { value: "app_installs", label: "App Installs" },
];
const HOOK_TYPES: AxisOption[] = [
  { value: "", label: "All Hook Types" },
  { value: "question", label: "Question" },
  { value: "bold_claim", label: "Bold Claim" },
  { value: "demo_open", label: "Demo Open" },
  { value: "social_proof", label: "Social Proof" },
  { value: "offer", label: "Offer" },
  { value: "story", label: "Story" },
  { value: "pattern_interrupt", label: "Pattern Interrupt" },
  { value: "testimonial", label: "Testimonial" },
  { value: "other", label: "Other" },
];
const CREATOR_MODES: AxisOption[] = [
  { value: "", label: "All Creatives" },
  { value: "creator", label: "Creator" },
  { value: "branded", label: "Branded" },
  { value: "hybrid", label: "Hybrid" },
];
const FORMATS: AxisOption[] = [
  { value: "", label: "All Formats" },
  { value: "9:16 Video", label: "9:16 Video" },
  { value: "4:5 Video", label: "4:5 Video" },
  { value: "1:1 Video", label: "1:1 Video" },
  { value: "16:9 Video", label: "16:9 Video" },
];
const KPI_OPTIONS: AxisOption[] = [
  { value: "", label: "All KPIs" },
  { value: "impressions", label: "Impressions" },
  { value: "clicks", label: "Clicks" },
  { value: "spend", label: "Spend" },
  { value: "conversions", label: "Conversions" },
  { value: "revenue", label: "Revenue" },
  { value: "ctr", label: "CTR" },
  { value: "cpc", label: "CPC" },
  { value: "cpa", label: "CPA" },
  { value: "cpm", label: "CPM" },
  { value: "roas", label: "ROAS" },
  { value: "vtr", label: "VTR" },
];

/** Legacy "all" sentinel normalises to "" (no constraint) so the
 *  controlled select always holds a value an <option> carries. */
function normAll(v: string): string {
  return v === "all" ? "" : v;
}

function LiveSelect({ label, value, options, onPick, aria, id }: {
  label: string; value: string; options: AxisOption[];
  onPick: (v: string) => void; aria: string; id?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} aria-label={aria} value={normAll(value)}
        onChange={(e) => onPick(e.target.value)}>
        {options.map((o) => <option key={o.label} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

/** Selector populated from real /api/campaigns/meta attribute data.
 *  A stored value missing from the list (stale scope, fresh data) is
 *  appended so the control never silently drops an active filter. */
export function MetaSelect({ id, label, allLabel, values, value, onPick }: {
  id: string; label: string; allLabel: string; values: string[];
  value: string; onPick: (v: string) => void;
}) {
  const v = normAll(value);
  const opts = v && !values.includes(v) ? [...values, v] : values;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} aria-label={label} value={v}
        onChange={(e) => onPick(e.target.value)}>
        <option value="">{allLabel}</option>
        {opts.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

export interface CampaignMetaRow {
  name: string; client: string; team: string; platforms: string[];
  markets: string[]; objectives: string[]; verticals: string[];
  projects: string[]; last_date: string; status: string;
}

export interface CampaignMeta {
  campaigns: CampaignMetaRow[];
  demo: boolean;
}

let metaPromise: Promise<CampaignMeta> | null = null;
/** Test hook: drop the cached metadata so each test fetches fresh. */
export function __resetCampaignMetaCache(): void {
  metaPromise = null;
}
function fetchMeta(): Promise<CampaignMeta> {
  if (!metaPromise) {
    // A failed fetch must never be cached for the app lifetime: clear
    // so the next caller retries, and surface the error to the hook.
    metaPromise = api<CampaignMeta>("GET", "/api/campaigns/meta")
      .catch((e: unknown) => {
        metaPromise = null;
        throw e;
      });
  }
  return metaPromise;
}

/** Drop the cached metadata and tell every mounted hook to refetch
 *  (call after import, rename, deletion or removal). Nulling the
 *  promise alone leaves components already showing old data stale,
 *  so the version broadcast drives them to reload. */
let metaVersion = 0;
const metaListeners = new Set<() => void>();
export function refreshCampaignMeta(): void {
  metaPromise = null;
  metaVersion += 1;
  metaListeners.forEach((fn) => {
    try { fn(); } catch { /* a dead listener must not break others */ }
  });
}
/** Test hook: current metadata generation (broadcasts bump it). */
export function __campaignMetaVersion(): number {
  return metaVersion;
}

/** Shared campaign-attribute metadata (clients, projects, teams,
 *  campaigns, verticals, markets) plus the demo-workspace flag. */
export function useCampaignMeta(): {
  data: CampaignMeta | null;
  error: string; loading: boolean; refresh: () => void;
} {
  const [data, setData] = useState<CampaignMeta | null>(null);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => {
    refreshCampaignMeta();
  }, []);
  useEffect(() => {
    const onBroadcast = () => {
      setData(null);
      setError("");
      setNonce((n) => n + 1);
    };
    metaListeners.add(onBroadcast);
    return () => { metaListeners.delete(onBroadcast); };
  }, []);
  useEffect(() => {
    let live = true;
    fetchMeta()
      .then((r) => live && setData(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => { live = false; };
  }, [nonce]);
  return { data, error, loading: data === null && error === "", refresh };
}

function distinct(rows: CampaignMetaRow[], pick: (r: CampaignMetaRow) => string[]): string[] {
  return [...new Set(rows.flatMap(pick).map((s) => s.trim()).filter(Boolean))].sort();
}

export function titleAxis(v: string, all: string): string {
  if (!v) return all;
  return v.split("_").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

function fmtShortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return "";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1] ?? m[2]} ${Number(m[3])}, ${m[1]}`;
}

/** ONE compact Date Range field: a single button shows the active range
 *  (or All Time when unbounded) and opens a small popover with the
 *  From/To inputs. Same setFilter writes as the old joined control —
 *  only the presentation collapses to one grid cell. */
export function DateRangeField({ id }: { id: string }) {
  const { filters, setFilter } = useFilters();
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open ]);

  const from = fmtShortDate(filters.date_from);
  const to = fmtShortDate(filters.date_to);
  /* Same-year ranges drop the first year ("Aug 13 – Sep 11, 2026") so
   * the single field fits its grid cell without truncating. */
  const yearOf = (s: string) => /,\s*(\d{4})$/.exec(s)?.[1] ?? "";
  const sameYear = from !== "" && yearOf(from) !== "" && yearOf(from) === yearOf(to);
  const shortFrom = sameYear ? from.replace(/,\s*\d{4}$/, "") : from;
  const label = from || to ? `${shortFrom || "…"} – ${to || "…"}` : "All Time";
  return (
    <div className="field">
      <label id={`${id}-label`}>Date Range</label>
      <div className="daterange" ref={boxRef}>
        <button type="button" className="daterange-btn" aria-labelledby={`${id}-label daterange-val-${id}`}
          aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Icon name="calendar" size={15} />
          <span id={`daterange-val-${id}`}>{label}</span>
        </button>
        {open ? (
          <div className="daterange-pop" role="group" aria-labelledby={`${id}-label`}>
            <div className="field">
              <label htmlFor={`${id}-from`}>From</label>
              <input id={`${id}-from`} type="date" aria-label="From Date" value={filters.date_from}
                onChange={(e) => setFilter("date_from", e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor={`${id}-to`}>To</label>
              <input id={`${id}-to`} type="date" aria-label="To Date" value={filters.date_to}
                onChange={(e) => setFilter("date_to", e.target.value)} />
            </div>
            <div className="daterange-actions">
              <button type="button" className="link-teal"
                onClick={() => { setFilter("date_from", ""); setFilter("date_to", ""); }}>
                Clear
              </button>
              <button type="button" className="btn-primary" onClick={() => setOpen(false)}>
                Done
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function FilterPanel({ onApply, kpi = true, creative = false, trailing, actions = "panel", showTeam = true }: {
  onApply?: () => void; kpi?: boolean; creative?: boolean;
  trailing?: React.ReactNode; actions?: "panel" | "none";
  /** Dashboard hides Team (opt-out); it stays visible everywhere else
   *  and keeps filtering through the shared global scope when set. */
  showTeam?: boolean;
}) {
  const { filters, setFilter, clearFilters } = useFilters();
  const meta = useCampaignMeta();
  const rows = meta.data?.campaigns ?? [];
  const clients = distinct(rows, (r) => [r.client]);
  const campaigns = distinct(rows, (r) => [r.name]);
  if (creative) {
    return (
      <section className="panel" aria-label="Filters">
        <div className="filter-grid">
          <MetaSelect id="f-client" label="Client" allLabel="All Clients"
            values={clients} value={filters.client}
            onPick={(v) => setFilter("client", v)} />
          <MetaSelect id="f-campaign" label="Campaign" allLabel="All Campaigns"
            values={campaigns} value={filters.campaign}
            onPick={(v) => setFilter("campaign", v)} />
          <LiveSelect id="f-hook" label="Hook Type" aria="Hook Type"
            value={filters.hook_type} options={HOOK_TYPES}
            onPick={(v) => setFilter("hook_type", v)} />
          <LiveSelect id="f-format" label="Format" aria="Format"
            value={filters.format} options={FORMATS}
            onPick={(v) => setFilter("format", v)} />
          <LiveSelect id="f-creator" label="Creator vs Branded" aria="Creator vs Branded"
            value={filters.creator_vs_branded} options={CREATOR_MODES}
            onPick={(v) => setFilter("creator_vs_branded", v)} />
          <LiveSelect id="f-platform" label="Platform" aria="Platform"
            value={filters.platform} options={PLATFORMS}
            onPick={(v) => setFilter("platform", v)} />
          <LiveSelect id="f-funnel" label="Funnel Stage" aria="Funnel Stage"
            value={filters.funnel} options={FUNNELS}
            onPick={(v) => setFilter("funnel", v)} />
          {trailing}
          <DateRangeField id="f-date" />
        </div>
        {actions === "panel" ? (
          <div className="filter-actions">
            <button type="button" className="link-teal" onClick={clearFilters}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> Reset Filters
            </button>
            <button type="button" className="btn-primary"
              onClick={() => (onApply ? onApply() : undefined)}>
              Apply Filters
            </button>
          </div>
        ) : null}
      </section>
    );
  }
  const projects = distinct(rows, (r) => r.projects ?? []);
  const teams = distinct(rows, (r) => [r.team]);
  const verticals = distinct(rows, (r) => r.verticals ?? []);
  const markets = distinct(rows, (r) => r.markets ?? []);
  return (
    <section className="panel" aria-label="Filters">
      <div className="filter-grid">
        <MetaSelect id="f-client" label="Client" allLabel="All Clients"
          values={clients} value={filters.client}
          onPick={(v) => setFilter("client", v)} />
        <MetaSelect id="f-project" label="Project" allLabel="All Projects"
          values={projects} value={filters.project}
          onPick={(v) => setFilter("project", v)} />
        {showTeam ? (
          <MetaSelect id="f-team" label="Team" allLabel="All Teams"
            values={teams} value={filters.team}
            onPick={(v) => setFilter("team", v)} />
        ) : null}
        <MetaSelect id="f-campaign" label="Campaign" allLabel="All Campaigns"
          values={campaigns} value={filters.campaign}
          onPick={(v) => setFilter("campaign", v)} />
        <LiveSelect id="f-platform" label="Platform" aria="Platform"
          value={filters.platform} options={PLATFORMS}
          onPick={(v) => setFilter("platform", v)} />
        <MetaSelect id="f-vertical" label="Vertical" allLabel="All Verticals"
          values={verticals} value={filters.vertical}
          onPick={(v) => setFilter("vertical", v)} />
        <MetaSelect id="f-market" label="Market" allLabel="All Markets"
          values={markets} value={filters.market}
          onPick={(v) => setFilter("market", v)} />
        <LiveSelect id="f-funnel" label="Funnel Stage" aria="Funnel Stage"
          value={filters.funnel} options={FUNNELS}
          onPick={(v) => setFilter("funnel", v)} />
        <LiveSelect id="f-objective" label="Campaign Objective" aria="Campaign Objective"
          value={filters.objective} options={OBJECTIVES}
          onPick={(v) => setFilter("objective", v)} />
        {kpi ? (
          <LiveSelect id="f-kpi" label="KPI" aria="KPI"
            value={filters.kpi} options={KPI_OPTIONS}
            onPick={(v) => setFilter("kpi", v)} />
        ) : <div />}
        <DateRangeField id="f-date" />
      </div>
      {actions === "panel" ? (
        <div className="filter-actions">
          <button type="button" className="link-teal" onClick={clearFilters}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="reset" size={15} /> Reset Filters
          </button>
          <button type="button" className="btn-primary"
            onClick={() => (onApply ? onApply() : undefined)}>
            Apply Filters
          </button>
        </div>
      ) : null}
    </section>
  );
}

/* ------------------------------- KPI card ------------------------------ */
export function KpiCard({ label, display, icon, tint, metricLabel, compare }: {
  label: string; display: string; icon: string; tint: string;
  metricLabel: string; compare: CompareResp | null;
}) {
  // Backend metric keys are lowercase ("impressions"); pages pass Title
  // Case display labels ("Impressions"). Resolve case-insensitively so a
  // label-casing mismatch can never silently drop the backend trend.
  const metrics = compare?.metrics ?? {};
  const m = metrics[metricLabel] ?? metrics[metricLabel.toLowerCase()]
    ?? metrics[metricLabel.toUpperCase()];
  // KPI hierarchy lives in theme.css (.kpi-label Title Case 13/600,
  // .kpi-value 27/800): one authoritative definition shared by every
  // KpiCard and hand-rolled card. Only the per-card icon tint stays
  // inline because it is data, not system.
  return (
    <div className="kpi-card">
      <span className="kpi-ico" style={{ background: tint }}>
        <Icon name={icon} size={20} />
      </span>
      <div className="kpi-body">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{display}</div>
        <div className="kpi-trend-slot">
          {m && compare ? (
            <KpiTrend metricLabel={metricLabel}
              comparison={{
                state: m.state, direction: m.direction, sentiment: m.sentiment,
                percent_change: m.percent_change,
              }}
              previous={compare.previous_period} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

/* --------------------------- insights / misc --------------------------- */
export interface Insight {
  icon: string; tint: string; title: string; body: string;
  action?: string; href?: string;
}
export function InsightList({ items }: { items: Insight[] }) {
  return (
    <div>
      {items.map((it, i) => (
        <div className="insight" key={i}>
          <span className="insight-ico" style={{ background: it.tint }}>
            <Icon name={it.icon} size={21} />
          </span>
          <div style={{ minWidth: 0 }}>
            <h4>{it.title}</h4>
            <p>{it.body}</p>
            {it.action ? (
              it.href ? <a className="btn-soft" href={it.href}>{it.action}</a>
                : <span className="btn-soft">{it.action}</span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

/* Accessible info explainer: hover, focus, keyboard, touch/click,
 * Escape and outside-click all work. Never rely on the browser
 * `title` attribute alone for meaning. */
export function InfoTip({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [open ]);
  return (
    <span className="trend-tooltip-anchor" ref={ref}>
      <button type="button" className="trend-info" style={{ width: 18, height: 18, fontSize: 10 }}
        aria-label={label} aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
        <span aria-hidden="true">i</span>
      </button>
      {open ? <span className="kpi-tip" role="status">{text}</span> : null}
    </span>
  );
}

export function Panel({ title, action, sub, icon, tint, children }: {
  title: string; action?: React.ReactNode; sub?: string;
  icon?: string; tint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        {icon ? (
          <span className="insight-ico" aria-hidden="true"
            style={{ background: tint ?? "#E7F1FB", flex: "0 0 auto", marginRight: 2, alignSelf: "flex-start" }}>
            <Icon name={icon} size={20} />
          </span>
        ) : null}
        {/* Titles start at the head top even beside taller actions:
          row members keep matching title baselines. */}
        <div style={{ flex: "1 1 auto", minWidth: 0, alignSelf: "flex-start" }}>
          <h2 className="panel-title">{title}</h2>
          {sub ? <p className="panel-sub">{sub}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className="skel" style={{ height }} aria-label="Loading" />;
}

/** Structured empty state: small icon, bold title, one-line explanation,
 *  optional CTA, and significantly less vertical height than a bare panel.
 *  The legacy `text` form keeps rendering for inline error slots. */
export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function EmptyState({ text, title, icon, action, compact }: {
  text?: string; title?: string; icon?: string; action?: React.ReactNode; compact?: boolean;
}) {
  if (!title && !icon && !action) {
    const body = text && /^\s*No\b/.test(text) ? titleCase(text) : text;
    return <div className="empty">{body}</div>;
  }
  return (
    <div className={`empty-structured${compact ? " empty-compact" : ""}`}>
      {icon ? (
        <span className="empty-ico" aria-hidden="true">
          <Icon name={icon} size={20} />
        </span>
      ) : null}
      <p className="empty-title">{title ? titleCase(title) : text}</p>
      {text && title ? <p className="empty-body">{text}</p> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function DemoDataBadge() {
  return <span className="badge-demo">Demo Data</span>;
}
