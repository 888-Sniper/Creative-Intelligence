import { useEffect, useState } from "react";
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
export function useCompare(refreshKey = 0) {
  const { filters } = useFilters();
  const [data, setData] = useState<CompareResp | null>(null);
  useEffect(() => {
    let live = true;
    api<CompareResp>("GET", scopedPath("/api/kpis/compare", scopeParams(filters)))
      .then((r) => live && setData(r))
      .catch(() => live && setData(null));
    return () => { live = false; };
  }, [filters, refreshKey]);
  return data;
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
  return { data, error };
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
    <span className="thumb-wrap" role="img" aria-label={label ? `${label} thumbnail` : "Creative thumbnail"}>
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
const PLATFORMS = ["All Platforms", "Meta", "TikTok"];
const FUNNELS = ["All Stages", "Upper", "Mid", "Lower"];
const OBJECTIVES = ["All Objectives", "Conversions", "Traffic", "Leads",
  "Awareness", "Video Views", "App Installs"];

function LiveSelect({ label, value, options, onPick, aria }: {
  label: string; value: string; options: string[];
  onPick: (v: string) => void; aria: string;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <select aria-label={aria} value={value}
        onChange={(e) => onPick(e.target.value)}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

const HOOK_TYPES = ["All Hook Types", "Question", "Bold Claim", "Demo Open",
  "Social Proof", "Offer", "Story", "Pattern Interrupt", "Testimonial", "Other"];
const CREATOR_MODES = ["All Creatives", "Creator", "Branded", "Hybrid"];
const FORMATS = ["All Formats", "9:16 Video", "4:5 Video", "1:1 Video", "16:9 Video"];

function titleAxis(v: string, all: string): string {
  if (!v) return all;
  return v.split("_").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

export function FilterPanel({ onApply, kpi = true, creative = false, trailing, actions = "panel" }: {
  onApply?: () => void; kpi?: boolean; creative?: boolean;
  trailing?: React.ReactNode; actions?: "panel" | "none";
}) {
  const { filters, setFilter, clearFilters } = useFilters();
  const pick = (
    key: "platform" | "funnel" | "objective" | "hook_type" | "creator_vs_branded" | "format",
    all: string,
  ) => (v: string) => setFilter(key, v === all ? "" : v.toLowerCase().replace(/ /g, "_"));
  if (creative) {
    return (
      <section className="panel" aria-label="Filters">
        <div className="filter-grid">
          <div className="field">
            <label htmlFor="f-client">Client</label>
            <input id="f-client" placeholder="All Clients" value={filters.client}
              onChange={(e) => setFilter("client", e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="f-campaign">Campaign</label>
            <input id="f-campaign" placeholder="All Campaigns" value={filters.campaign}
              onChange={(e) => setFilter("campaign", e.target.value)} />
          </div>
          <LiveSelect label="Hook Type" aria="Hook Type"
            value={titleAxis(filters.hook_type, "All Hook Types")} options={HOOK_TYPES}
            onPick={pick("hook_type", "All Hook Types")} />
          <LiveSelect label="Format" aria="Format"
            value={filters.format || "All Formats"}
            options={FORMATS} onPick={(v) => setFilter("format", v === "All Formats" ? "" : v)} />
          <LiveSelect label="Creator vs Branded" aria="Creator vs Branded"
            value={titleAxis(filters.creator_vs_branded, "All Creatives")} options={CREATOR_MODES}
            onPick={pick("creator_vs_branded", "All Creatives")} />
          <LiveSelect label="Platform" aria="Platform"
            value={filters.platform || "All Platforms"} options={PLATFORMS}
            onPick={pick("platform", "All Platforms")} />
          <LiveSelect label="Funnel Stage" aria="Funnel Stage"
            value={titleAxis(filters.funnel, "All Stages")} options={FUNNELS}
            onPick={pick("funnel", "All Stages")} />
          {trailing}
          <div className="field">
            <label id="f-date-label">Date Range</label>
            <div className="date-pair" role="group" aria-labelledby="f-date-label">
              <input type="date" aria-label="From date" value={filters.date_from}
                onChange={(e) => setFilter("date_from", e.target.value)} />
              <input type="date" aria-label="To date" value={filters.date_to}
                onChange={(e) => setFilter("date_to", e.target.value)} />
            </div>
          </div>
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
  return (
    <section className="panel" aria-label="Filters">
      <div className="filter-grid">
        <div className="field">
          <label htmlFor="f-client">Client</label>
          <input id="f-client" placeholder="All Clients" value={filters.client}
            onChange={(e) => setFilter("client", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="f-project">Project</label>
          <input id="f-project" placeholder="All Projects" value={filters.project}
            onChange={(e) => setFilter("project", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="f-team">Team</label>
          <input id="f-team" placeholder="All Teams" value={filters.team}
            onChange={(e) => setFilter("team", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="f-campaign">Campaign</label>
          <input id="f-campaign" placeholder="All Campaigns" value={filters.campaign}
            onChange={(e) => setFilter("campaign", e.target.value)} />
        </div>
        <LiveSelect label="Platform" aria="Platform"
          value={filters.platform || "All Platforms"} options={PLATFORMS}
          onPick={pick("platform", "All Platforms")} />
        <div className="field">
          <label htmlFor="f-vertical">Vertical</label>
          <input id="f-vertical" placeholder="All Verticals" value={filters.vertical}
            onChange={(e) => setFilter("vertical", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="f-market">Market</label>
          <input id="f-market" placeholder="All Markets" value={filters.market}
            onChange={(e) => setFilter("market", e.target.value)} />
        </div>
        <LiveSelect label="Funnel Stage" aria="Funnel Stage"
          value={titleAxis(filters.funnel, "All Stages")} options={FUNNELS}
          onPick={pick("funnel", "All Stages")} />
        <LiveSelect label="Campaign Objective" aria="Campaign Objective"
          value={filters.objective || "All Objectives"} options={OBJECTIVES}
          onPick={pick("objective", "All Objectives")} />
        {kpi ? (
          <div className="field">
            <label htmlFor="f-kpi">KPI</label>
            <input id="f-kpi" placeholder="All KPIs" value={filters.kpi}
              onChange={(e) => setFilter("kpi", e.target.value)} />
          </div>
        ) : <div />}
        <div className="field">
          <label id="f-date-label">Date</label>
          <div className="date-pair" role="group" aria-labelledby="f-date-label">
            <input type="date" aria-label="From date" value={filters.date_from}
              onChange={(e) => setFilter("date_from", e.target.value)} />
            <input type="date" aria-label="To date" value={filters.date_to}
              onChange={(e) => setFilter("date_to", e.target.value)} />
          </div>
        </div>
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
  return (
    <div className="kpi-card">
      <span className="kpi-ico" style={{ background: tint }}>
        <Icon name={icon} size={22} />
      </span>
      <div className="kpi-body">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{display}</div>
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

export function Panel({ title, action, sub, children }: {
  title: string; action?: React.ReactNode; sub?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
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

export function EmptyState({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

export function DemoDataBadge() {
  return <span className="badge-demo">Demo Data</span>;
}
