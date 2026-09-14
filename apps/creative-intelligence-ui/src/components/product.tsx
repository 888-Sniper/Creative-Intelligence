import { useCallback, useEffect, useRef, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { scopeParams, useFilters } from "@/state/FilterContext";
import { KpiTrend, monthName } from "@/components/KpiTrend";
import type { KpiComparison, KpiPeriod } from "@/components/KpiTrend";
import { Icon } from "@/components/icons";
import { useLocale } from "@/i18n";

/* ---------- formatting (display only; calculations stay backend-side) --- */
/* All numeric formatters take the UI locale (§9): Intl renders the
 * decimal separators, grouping and compact suffixes; English output
 * is byte-identical to the previous literals. Calculations stay
 * backend-side — these only shape display strings. */
function decimal(n: number, locale: string, min: number, max: number): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: min, maximumFractionDigits: max,
  }).format(n);
}
export function fmtCompact(n: number, locale = "en"): string {
  const abs = Math.abs(n);
  if (abs >= 1_000) {
    try {
      // Always one decimal ("25.0K"), matching the previous literals.
      return new Intl.NumberFormat(locale, {
        notation: "compact",
        minimumFractionDigits: 1, maximumFractionDigits: 1,
      }).format(n);
    } catch {
      if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
      return `${(n / 1_000).toFixed(1)}K`;
    }
  }
  return `${Math.round(n)}`;
}
export function fmtMoney(n: number, locale = "en"): string {
  const abs = Math.abs(n);
  if (abs >= 1_000) {
    try {
      return new Intl.NumberFormat(locale, {
        style: "currency", currency: "USD",
        notation: "compact",
        minimumFractionDigits: 1, maximumFractionDigits: 1,
      }).format(n);
    } catch {
      if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
      return `$${(n / 1_000).toFixed(1)}K`;
    }
  }
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency", currency: "USD", maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `$${n.toFixed(0)}`;
  }
}
export function fmtMult(n: number, locale = "en"): string {
  try {
    return `${decimal(n, locale, 1, 1)}x`;
  } catch {
    return `${n.toFixed(1)}x`;
  }
}
export function fmtPct(n: number, digits = 1, locale = "en"): string {
  try {
    return `${decimal(n, locale, digits, digits)}%`;
  } catch {
    return `${n.toFixed(digits)}%`;
  }
}

/* ------- numeric KPI data states (shared; §4 empty-vs-unknown) --------
 * A successfully loaded scope with no performance records shows
 * formatted zeros (an empty-state display placeholder, NOT a new
 * calculated fact). A loaded NONEMPTY scope with an uncomputable
 * metric (missing revenue, mixed currencies, undefined denominator)
 * shows "Unavailable". Loading stays skeleton; request failures stay
 * error UI — callers must not feed those states here. */
export type KpiKind = "money" | "mult" | "count" | "pct";
export const KPI_UNAVAILABLE = "Unavailable";
export const EMPTY_KPI_NOTE = "No data yet; displayed zero is a placeholder.";
export function kpiDisplay(
  kind: KpiKind, value: number | null | undefined, empty: boolean,
  locale = "en", unavailable: string = KPI_UNAVAILABLE,
): string {
  if (value == null || !Number.isFinite(value)) {
    if (!empty) return unavailable;
    // Empty-scope zero placeholders render through the UI locale.
    switch (kind) {
      case "money":
        try {
          return new Intl.NumberFormat(locale, {
            style: "currency", currency: "USD",
            minimumFractionDigits: 2, maximumFractionDigits: 2,
          }).format(0);
        } catch {
          return "$0.00";
        }
      case "mult": return fmtMult(0, locale);
      case "pct": return fmtPct(0, 1, locale);
      case "count": return fmtCompact(0, locale);
    }
  }
  switch (kind) {
    case "money": return fmtMoney(value, locale);
    case "mult": return fmtMult(value, locale);
    case "pct": return fmtPct(value, 1, locale);
    case "count": return fmtCompact(value, locale);
  }
}
/** Accessible context for empty ratio/percentage zero placeholders. */
export function kpiPlaceholderNote(
  kind: KpiKind, value: number | null | undefined, empty: boolean,
): string | null {
  if (empty && (value == null || !Number.isFinite(value))
    && (kind === "mult" || kind === "pct")) {
    return EMPTY_KPI_NOTE;
  }
  return null;
}
/** Table numeric cell: a missing or non-finite measure in loaded data
 *  is an honest "Unavailable", never a dash masquerading as zero or
 *  vice versa. Non-numeric display values pass through untouched. */
export function fmtCell<T>(
  value: T | null | undefined, fmt: (v: T) => string,
  unavailable: string = KPI_UNAVAILABLE,
): string {
  if (value == null) return unavailable;
  if (typeof value === "number" && !Number.isFinite(value)) return unavailable;
  return fmt(value);
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
  current_n_ads?: number;
  previous_n_ads?: number;
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
/* Axis values are backend scope tokens; every display label resolves
 * through filters.* (§9) so the selects translate with the UI. */
const PLATFORM_VALUES = ["", "meta", "tiktok"];
const FUNNEL_VALUES = ["", "upper", "mid", "lower"];
const OBJECTIVE_VALUES = ["", "conversions", "traffic", "leads", "awareness", "video_views", "app_installs"];
const HOOK_VALUES = ["", "question", "bold_claim", "demo_open", "social_proof", "offer", "story", "pattern_interrupt", "testimonial", "other"];
const CREATOR_VALUES = ["", "creator", "branded", "hybrid"];
const FORMAT_VALUES = ["", "9:16 Video", "4:5 Video", "1:1 Video", "16:9 Video"];
const KPI_VALUES = ["", "impressions", "clicks", "spend", "conversions", "revenue", "ctr", "cpc", "cpa", "cpm", "roas", "vtr"];

type TFn = (key: string, vars?: Record<string, string | number>) => string;

function axisLabel(t: TFn, group: string, allKey: string, value: string, proper?: Record<string, string>): string {
  if (!value) return t(allKey);
  if (proper && proper[value]) return proper[value];
  const key = `filters.${group}.${value}`;
  const hit = t(key);
  return hit === key ? titleCase(value) : hit;
}

function axisOptions(t: TFn, group: string, allKey: string, values: string[], proper?: Record<string, string>): AxisOption[] {
  return values.map((value) => ({ value, label: axisLabel(t, group, allKey, value, proper) }));
}

const PROPER_NOUNS: Record<string, string> = { meta: "Meta", tiktok: "TikTok" };

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

function fmtShortDate(iso: string, locale = "en-US"): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return "";
  return `${monthName(Number(m[2]), locale)} ${Number(m[3])}, ${m[1]}`;
}

/** ONE compact Date Range field: a single button shows the active range
 *  (or All Time when unbounded) and opens a small popover with the
 *  From/To inputs. Same setFilter writes as the old joined control —
 *  only the presentation collapses to one grid cell. */
export function DateRangeField({ id }: { id: string }) {
  const { t, lang } = useLocale();
  const { filters, setFilter } = useFilters();
  const loc = lang === "pl" ? "pl-PL" : lang === "es" ? "es-ES" : "en-US";
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

  const from = fmtShortDate(filters.date_from, loc);
  const to = fmtShortDate(filters.date_to, loc);
  /* Same-year ranges drop the first year ("Aug 13 – Sep 11, 2026") so
   * the single field fits its grid cell without truncating. */
  const yearOf = (s: string) => /,\s*(\d{4})$/.exec(s)?.[1] ?? "";
  const sameYear = from !== "" && yearOf(from) !== "" && yearOf(from) === yearOf(to);
  const shortFrom = sameYear ? from.replace(/,\s*\d{4}$/, "") : from;
  const label = from || to ? `${shortFrom || "…"} – ${to || "…"}` : t("filters.allTime");
  return (
    <div className="field field-date">
      <label id={`${id}-label`}>{t("filters.dateRange")}</label>
      <div className="daterange" ref={boxRef}>
        <button type="button" className="daterange-btn" aria-labelledby={`${id}-label daterange-val-${id}`}
          aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Icon name="calendar" size={15} />
          <span id={`daterange-val-${id}`}>{label}</span>
        </button>
        {open ? (
          <div className="daterange-pop" role="group" aria-labelledby={`${id}-label`}>
            <div className="field">
              <label htmlFor={`${id}-from`}>{t("filters.from")}</label>
              <input id={`${id}-from`} type="date" aria-label={t("filters.fromDate")} value={filters.date_from}
                onChange={(e) => setFilter("date_from", e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor={`${id}-to`}>{t("filters.to")}</label>
              <input id={`${id}-to`} type="date" aria-label={t("filters.toDate")} value={filters.date_to}
                onChange={(e) => setFilter("date_to", e.target.value)} />
            </div>
            <div className="daterange-actions">
              <button type="button" className="link-teal"
                onClick={() => { setFilter("date_from", ""); setFilter("date_to", ""); }}>
                {t("filters.clear")}
              </button>
              <button type="button" className="btn-primary" onClick={() => setOpen(false)}>
                {t("filters.done")}
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
  const { t } = useLocale();
  const { filters, setFilter, clearFilters } = useFilters();
  const meta = useCampaignMeta();
  const rows = meta.data?.campaigns ?? [];
  const clients = distinct(rows, (r) => [r.client]);
  const campaigns = distinct(rows, (r) => [r.name]);
  const platforms = axisOptions(t, "", "filters.allPlatforms", PLATFORM_VALUES, PROPER_NOUNS);
  const funnels = axisOptions(t, "funnels", "filters.allStages", FUNNEL_VALUES);
  const objectives = axisOptions(t, "objectives", "filters.allObjectives", OBJECTIVE_VALUES);
  const hooks = axisOptions(t, "hooks", "filters.allHooks", HOOK_VALUES);
  const creators = axisOptions(t, "creators", "filters.allCreatives", CREATOR_VALUES);
  const formats = axisOptions(t, "", "filters.allFormats", FORMAT_VALUES);
  const kpis = axisOptions(t, "kpis", "filters.allKpis", KPI_VALUES);
  if (creative) {
    return (
      <section className="panel" aria-label={t("filters.section")}>
        <div className="filter-grid">
          <MetaSelect id="f-client" label={t("filters.client")} allLabel={t("filters.allClients")}
            values={clients} value={filters.client}
            onPick={(v) => setFilter("client", v)} />
          <MetaSelect id="f-campaign" label={t("filters.campaign")} allLabel={t("filters.allCampaigns")}
            values={campaigns} value={filters.campaign}
            onPick={(v) => setFilter("campaign", v)} />
          <LiveSelect id="f-hook" label={t("filters.hook")} aria={t("filters.hook")}
            value={filters.hook_type} options={hooks}
            onPick={(v) => setFilter("hook_type", v)} />
          <LiveSelect id="f-format" label={t("filters.format")} aria={t("filters.format")}
            value={filters.format} options={formats}
            onPick={(v) => setFilter("format", v)} />
          <LiveSelect id="f-creator" label={t("filters.creator")} aria={t("filters.creator")}
            value={filters.creator_vs_branded} options={creators}
            onPick={(v) => setFilter("creator_vs_branded", v)} />
          <LiveSelect id="f-platform" label={t("filters.platform")} aria={t("filters.platform")}
            value={filters.platform} options={platforms}
            onPick={(v) => setFilter("platform", v)} />
          <LiveSelect id="f-funnel" label={t("filters.funnel")} aria={t("filters.funnel")}
            value={filters.funnel} options={funnels}
            onPick={(v) => setFilter("funnel", v)} />
          {trailing}
          <DateRangeField id="f-date" />
        </div>
        {actions === "panel" ? (
          <div className="filter-actions">
            <button type="button" className="btn-primary"
              onClick={() => (onApply ? onApply() : undefined)}>
              {t("filters.apply")}
            </button>
            <button type="button" className="link-teal" onClick={clearFilters}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="reset" size={15} /> {t("filters.reset")}
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
    <section className="panel" aria-label={t("filters.section")}>
      <div className="filter-grid">
        <MetaSelect id="f-client" label={t("filters.client")} allLabel={t("filters.allClients")}
          values={clients} value={filters.client}
          onPick={(v) => setFilter("client", v)} />
        <MetaSelect id="f-project" label={t("filters.project")} allLabel={t("filters.allProjects")}
          values={projects} value={filters.project}
          onPick={(v) => setFilter("project", v)} />
        {showTeam ? (
          <MetaSelect id="f-team" label={t("filters.team")} allLabel={t("filters.allTeams")}
            values={teams} value={filters.team}
            onPick={(v) => setFilter("team", v)} />
        ) : null}
        <MetaSelect id="f-campaign" label={t("filters.campaign")} allLabel={t("filters.allCampaigns")}
          values={campaigns} value={filters.campaign}
          onPick={(v) => setFilter("campaign", v)} />
        <LiveSelect id="f-platform" label={t("filters.platform")} aria={t("filters.platform")}
          value={filters.platform} options={platforms}
          onPick={(v) => setFilter("platform", v)} />
        <MetaSelect id="f-vertical" label={t("filters.vertical")} allLabel={t("filters.allVerticals")}
          values={verticals} value={filters.vertical}
          onPick={(v) => setFilter("vertical", v)} />
        <MetaSelect id="f-market" label={t("filters.market")} allLabel={t("filters.allMarkets")}
          values={markets} value={filters.market}
          onPick={(v) => setFilter("market", v)} />
        <LiveSelect id="f-funnel" label={t("filters.funnel")} aria={t("filters.funnel")}
          value={filters.funnel} options={funnels}
          onPick={(v) => setFilter("funnel", v)} />
        <LiveSelect id="f-objective" label={t("filters.objective")} aria={t("filters.objective")}
          value={filters.objective} options={objectives}
          onPick={(v) => setFilter("objective", v)} />
        {kpi ? (
          <LiveSelect id="f-kpi" label={t("filters.kpi")} aria={t("filters.kpi")}
            value={filters.kpi} options={kpis}
            onPick={(v) => setFilter("kpi", v)} />
        ) : <div />}
        <DateRangeField id="f-date" />
      </div>
      {actions === "panel" ? (
        <div className="filter-actions">
          <button type="button" className="btn-primary"
            onClick={() => (onApply ? onApply() : undefined)}>
            {t("filters.apply")}
          </button>
          <button type="button" className="link-teal" onClick={clearFilters}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="reset" size={15} /> {t("filters.reset")}
          </button>
        </div>
      ) : null}
    </section>
  );
}

/* ------------------------------- KPI card ------------------------------ */
export function KpiCard({ label, display, icon, metricLabel, compare, note }: {
  label: string; display: string; icon: string;
  /** Legacy per-card tint (ignored): icon tiles are uniformly gray
   *  with teal symbols via theme.css (.kpi-ico). Kept optional so
   *  existing callers keep compiling. */
  tint?: string;
  metricLabel: string; compare: CompareResp | null;
  /** Unobtrusive accessible context (e.g. empty zero-placeholder note). */
  note?: string | null;
}) {
  // Backend metric keys are lowercase ("impressions"); pages pass Title
  // Case display labels ("Impressions"). Resolve case-insensitively so a
  // label-casing mismatch can never silently drop the backend trend.
  const metrics = compare?.metrics ?? {};
  const m = metrics[metricLabel] ?? metrics[metricLabel.toLowerCase()]
    ?? metrics[metricLabel.toUpperCase()];
  // KPI hierarchy lives in theme.css (.kpi-label Title Case 13/600,
  // .kpi-value 27/800): one authoritative definition shared by every
  // KpiCard and hand-rolled card. The icon tile is uniformly gray
  // with a teal symbol (.kpi-ico), never a per-card tint.
  return (
    <div className="kpi-card">
      <span className="kpi-ico">
        <Icon name={icon} size={20} />
      </span>
      <div className="kpi-body">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{display}{note ? <span className="sr-only"> ({note})</span> : null}</div>
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
  icon: string;
  /** Legacy per-item tint (ignored): insight tiles are uniformly gray
   *  with teal symbols via theme.css (.insight-ico). */
  tint?: string;
  title: string; body: string;
  action?: string; href?: string;
}
export function InsightList({ items }: { items: Insight[] }) {
  return (
    <div>
      {items.map((it, i) => (
        <div className="insight" key={i}>
          <span className="insight-ico">
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

export function Panel({ title, action, sub, icon, tint, children, style, headClassName }: {
  /** Optional: hero-style cards (§2) render no header at all. */
  title?: string; action?: React.ReactNode; sub?: string;
  icon?: string; tint?: string;
  children: React.ReactNode;
  /** Optional outer-style override (e.g. flex grow inside a rail
   *  stack so row members share a bottom edge). */
  style?: React.CSSProperties;
  /** Optional extra class on the header row (e.g. a responsive
   *  control layout that only applies to one panel). */
  headClassName?: string;
}) {
  const showHead = Boolean(title || sub || icon || action);
  return (
    <section className="panel" style={style}>
      {showHead ? (
      <div className={headClassName ? `panel-head ${headClassName}` : "panel-head"}>
        {icon ? (
          <span className="insight-ico" aria-hidden="true"
            style={{ background: tint ?? "var(--shell-blue-soft)", flex: "0 0 auto", marginRight: 2, alignSelf: "flex-start" }}>
            <Icon name={icon} size={20} />
          </span>
        ) : null}
        {/* Titles start at the head top even beside taller actions:
          row members keep matching title baselines. Beside an icon,
          a short title centres against the 44px icon box instead of
          hugging its top edge. */}
        <div style={{
          flex: "1 1 auto", minWidth: 0, alignSelf: "flex-start",
          ...(icon ? {
            minHeight: 44, display: "flex",
            flexDirection: "column", justifyContent: "center",
          } : null),
        }}>
          {title ? <h2 className="panel-title">{title}</h2> : null}
          {sub ? <p className="panel-sub">{sub}</p> : null}
        </div>
        {action}
      </div>
      ) : null}
      {children}
    </section>
  );
}

/* Shared overflow menu (§8): a ⋯ toggle opening one small
 * theme-aware menu. Escape/outside-click dismiss, focus returns to
 * the toggle, arrows move between items. Callers keep a single
 * implementation behind both the inline control and its menu item. */
export interface OverflowItem {
  label: string; icon?: string; disabled?: boolean; onSelect: () => void;
}
export function OverflowMenu({ label, items, className }: {
  label: string; items: OverflowItem[]; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const toggle = useRef<HTMLButtonElement | null>(null);
  const list = useRef<HTMLDivElement | null>(null);
  /* Position the menu against its trigger (§12). The menu renders in
   * a document.body portal (position:fixed, .ov-menu-portal) so no
   * scrolling table ancestor can clip it; it flips above the trigger
   * when there is no room below and clamps to the viewport width. */
  const place = useCallback(() => {
    const el = toggle.current;
    if (!el || typeof window === "undefined") return;
    const r = el.getBoundingClientRect();
    const width = Math.min(260, window.innerWidth - 16);
    const estH = Math.min(items.length * 46 + 12, window.innerHeight * 0.6);
    const roomBelow = window.innerHeight - r.bottom - 8;
    const top = roomBelow < Math.min(estH, 220) && r.top > estH
      ? Math.max(8, r.top - 8 - estH)
      : r.bottom + 6;
    const left = Math.max(8, Math.min(r.right - width, window.innerWidth - width - 8));
    setPos({ top, left });
  }, [items.length]);
  useEffect(() => {
    if (!open) return;
    place();
    const onDown = (e: PointerEvent) => {
      if (root.current?.contains(e.target as Node)) return;
      if (list.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        toggle.current?.focus();
      }
    };
    // A scroll or resize would strand a fixed menu away from its
    // trigger: dismiss instead of drifting.
    const onScroll = () => setOpen(false);
    const onResize = () => setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    const first = list.current?.querySelector("button:not(:disabled)");
    if (first instanceof HTMLElement) first.focus();
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [open, place]);
  const move = (e: React.KeyboardEvent) => {
    const btns = list.current ? [...list.current.querySelectorAll("button:not(:disabled)")].filter((b): b is HTMLElement => b instanceof HTMLElement) : [];
    if (!btns.length) return;
    const i = btns.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") { e.preventDefault(); btns[(i + 1) % btns.length].focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); btns[(i - 1 + btns.length) % btns.length].focus(); }
    else if (e.key === "Home") { e.preventDefault(); btns[0].focus(); }
    else if (e.key === "End") { e.preventDefault(); btns[btns.length - 1].focus(); }
  };
  const toggleMenu = () => {
    if (!open) place();
    setOpen((o) => !o);
  };
  return (
    <div className={className ? `ov-menu ${className}` : "ov-menu"} ref={root}>
      <button
        ref={toggle}
        type="button"
        className="icon-btn"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggleMenu}
      >
        <Icon name="dots" size={18} />
      </button>
      {open && pos ? (
        <div className="ov-menu-list ov-menu-portal" role="menu" aria-label={label}
          ref={list} onKeyDown={move}
          style={{ top: pos.top, left: pos.left }}>
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              className="ov-menu-item"
              disabled={it.disabled}
              onClick={() => { setOpen(false); toggle.current?.focus(); it.onSelect(); }}
            >
              {it.icon ? <Icon name={it.icon} size={15} /> : null}
              <span>{it.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* Shared preference switch (Settings + Profile §3 rows). Same 40×22
 * control everywhere so row padding and action alignment match. */
export function Toggle({ label, body, checked, onChange }: {
  label: string; body: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  /* Row breathing room (§11): 14px vertical — ~10% over the old 13px. */
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", padding: "14px 0", borderBottom: "1px solid var(--shell-line)" }}>
      <div style={{ minWidth: 0 }}>
        <strong style={{ display: "block", fontSize: 13 }}>{label}</strong>
        <span className="panel-sub" style={{ fontSize: 12 }}>{body}</span>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        style={{
          width: 40, height: 22, borderRadius: 999, border: 0, cursor: "pointer", flex: "none",
          background: checked ? "var(--shell-teal)" : "#CBD5E1", position: "relative",
        }}
      >
        <span style={{
          position: "absolute", top: 2, left: checked ? 20 : 2, width: 18, height: 18,
          borderRadius: "50%", background: "#fff", transition: "left .15s",
        }} />
      </button>
    </div>
  );
}

/** Layout-matched page loading shell (§10): header block plus a
 *  two-column panel arrangement approximating the final page, so the
 *  populated/error/empty state swaps in without a layout shift. The
 *  announcement lives in an sr-only live region — no visible text. */
export function PageSkeleton({ label, panels = 4 }: { label: string; panels?: number }) {
  return (
    <div role="status" aria-label={label}>
      <span className="sr-only">{label}</span>
      <div className="skel" style={{ height: 30, width: "32%", margin: "2px 0 8px" }} aria-hidden="true" />
      <div className="skel" style={{ height: 15, width: "55%", marginBottom: 14 }} aria-hidden="true" />
      <div className="cols-2-even">
        {Array.from({ length: panels }, (_, i) => (
          <div key={i} className="skel" style={{ height: i % 2 ? 190 : 150 }} aria-hidden="true" />
        ))}
      </div>
    </div>
  );
}

/** Brief nonblocking success toast (§8): auto-dismisses, announced
 *  through role=status. Callers show it after a successful save and
 *  return their submit control to its normal state. */
export function Toast({ message, onClose, durationMs = 3200 }: {
  message: string; onClose: () => void; durationMs?: number;
}) {
  useEffect(() => {
    const t = window.setTimeout(onClose, durationMs);
    return () => window.clearTimeout(t);
  }, [onClose, durationMs, message]);
  return (
    <div className="toast-wrap">
      <div className="toast" role="status">
        <Icon name="check" size={16} />
        <span>{message}</span>
      </div>
    </div>
  );
}

export function Skeleton({ height = 120 }: { height?: number }) {
  const { t } = useLocale();
  return <div className="skel" style={{ height }} aria-label={t("common.skeletonLoading")} />;
}

/** Structured empty state: small icon, bold title, one-line explanation,
 *  optional CTA, and significantly less vertical height than a bare panel.
 *  The legacy `text` form keeps rendering for inline error slots. */
export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Backend role/status codes render through the UI locale (never raw
 *  English Title Case). Unknown codes keep the honest as-is form. */
export function codeLabel(
  t: (key: string, vars?: Record<string, string | number>) => string,
  group: "roles" | "statuses",
  code: string,
): string {
  if (!code) return "—";
  const key = `common.${group}.${code}`;
  const hit = t(key);
  return hit === key ? titleCase(code) : hit;
}

/* ---------------- shared employee avatar (§1 avatar consistency) ------
 * Single resolver/component for every employee face in the app: Admin
 * rows, Profile hero, header/account menu, and activity entries that
 * name a known employee. The employee's own photo (custom upload or
 * provider photo — the server fills blanks once and never overwrites
 * a chosen or deliberately cleared avatar) wins; initials render only
 * when there is no URL or the image genuinely fails to load. Every
 * call site passes THAT employee's fields, never the signed-in user's.
 * Cropping comes from the .avatar class (object-fit: cover); a failed
 * load swaps to initials via local state so a retry/reset is instant. */
export function avatarInitials(name: string, email: string): string {
  const init = (name || "")
    .split(/\s+/)
    .map((w) => w.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
  if (init) return init;
  const mail = (email || "").trim().charAt(0).toUpperCase();
  return mail || "?";
}

export function EmployeeAvatar({ url, name, email, size }: {
  url: string; name: string; email: string; size?: number;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => { setFailed(false); }, [url]);
  const label = (name || "").trim() || (email || "").trim() || "Employee";
  if (url && !failed) {
    return (
      <img
        className="avatar"
        src={url}
        alt=""
        referrerPolicy="no-referrer"
        draggable={false}
        style={size ? { width: size, height: size, fontSize: Math.round(size * 0.38) } : undefined}
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <span
      className="avatar"
      role="img"
      aria-label={label}
      style={size ? { width: size, height: size, fontSize: Math.round(size * 0.38) } : undefined}
    >
      {avatarInitials(name, email)}
    </span>
  );
}

export function EmptyState({ text, title, icon, action, compact, lift, verbatim }: {
  text?: string; title?: string; icon?: string; action?: React.ReactNode; compact?: boolean;
  /** Small optical lift (§13): shifts the text/icon group ~8px upward
   *  without touching panel borders, dimensions or grid positions. */
  lift?: boolean;
  /** Render the copy exactly as passed (e.g. brief-fixed wording or a
   *  translated string whose casing must not be Title Cased). */
  verbatim?: boolean;
}) {
  const liftClass = lift ? " empty-lift" : "";
  if (!title && !icon && !action) {
    const body = !verbatim && text && /^\s*No\b/.test(text) ? titleCase(text) : text;
    return <div className={`empty${liftClass}`}>{body}</div>;
  }
  return (
    <div className={`empty-structured${compact ? " empty-compact" : ""}${liftClass}`}>
      {icon ? (
        <span className="empty-ico" aria-hidden="true">
          <Icon name={icon} size={20} />
        </span>
      ) : null}
      <p className="empty-title">{title && !verbatim ? titleCase(title) : (title ?? text)}</p>
      {text && title ? <p className="empty-body">{text}</p> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function DemoDataBadge() {
  const { t } = useLocale();
  return <span className="badge-demo">{t("common.demoData")}</span>;
}
