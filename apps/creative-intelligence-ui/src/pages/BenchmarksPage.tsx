import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  EmptyState,
  PageHeader,
  Panel,
  Skeleton,
  fmtMoney,
  platformLabel,
  useScopedApi,
} from "@/components/product";

/* Benchmarks Library keeps every existing backend behavior (axis-grouped
 * benchmark rows, three-way compare, CSV export) and only changes the
 * presentation layer to the approved reference. "Saved Benchmarks" are
 * the backend-backed saved views, applied on click. */

type Axis = "platform" | "hook_type" | "format" | "creator_vs_branded";

const AXES: Array<{ value: Axis; label: string }> = [
  { value: "platform", label: "Platform" },
  { value: "hook_type", label: "Hook Type" },
  { value: "format", label: "Format" },
  { value: "creator_vs_branded", label: "Creator vs Branded" },
];

interface BenchRow {
  spend: number; impressions: number; clicks: number; conversions: number;
  revenue: number; ctr: number | null; cpc: number | null; cpa: number | null;
  roas: number | null; n_ads: number;
}

interface SavedView {
  id: number;
  name: string;
  state: { filters?: Record<string, string[]>; kpi?: string; view?: string };
}

const VIEW_ROUTES: Record<string, string> = {
  main: "/", campaign: "/campaigns", creative: "/creatives", compare: "/compare",
  benchmark: "/benchmarks", report: "/reports", profile: "/profile", admin: "/admin",
};

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function axisLabel(axis: Axis, key: string): string {
  if (axis === "platform") return platformLabel(key);
  if (axis === "creator_vs_branded") return key === "creator" ? "Creator" : key === "branded" ? "Branded" : key;
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function MiniBars({ values, format }: { values: number[]; format: (v: number) => string }) {
  const max = Math.max(1, ...values);
  const colors = ["#2F6FBE", "#0E9F6E", "#7C6BD6"];
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 110, paddingTop: 18 }}>
      {values.map((v, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--shell-navy)" }}>{format(v)}</span>
          <div style={{ width: "70%", height: `${Math.max(4, (v / max) * 72)}px`, borderRadius: "5px 5px 0 0", background: colors[i % colors.length] }} />
        </div>
      ))}
    </div>
  );
}

export function BenchmarksPage() {
  const { filters, setFilter, clearFilters } = useFilters();
  const [axis, setAxis] = useState<Axis>("platform");
  const [applied, setApplied] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [views, setViews] = useState<SavedView[] | null>(null);

  const benchmarks = useScopedApi<Record<string, BenchRow>>(`/api/benchmarks?group_by=${axis}`, applied);
  const platCount = useScopedApi<Record<string, BenchRow>>("/api/benchmarks?group_by=platform", applied);
  const vertCount = useScopedApi<Record<string, BenchRow>>("/api/benchmarks?group_by=vertical", applied);

  useEffect(() => {
    let live = true;
    api<SavedView[]>("GET", "/api/views")
      .then((r) => live && setViews(Array.isArray(r) ? r : []))
      .catch(() => live && setViews([]));
    return () => { live = false; };
  }, [applied]);

  const rows = useMemo(() => {
    const list = Object.entries(benchmarks.data ?? {}).map(([key, m]) => ({ key, ...m }));
    return axis === "platform"
      ? list.sort((a, b) => axisLabel(axis, a.key).localeCompare(axisLabel(axis, b.key)))
      : list.sort((a, b) => num(b.spend) - num(a.spend));
  }, [benchmarks.data, axis]);

  const compared = useMemo(
    () => rows.filter((r) => selected.has(r.key)).slice(0, 3),
    [rows, selected],
  );

  const coverage = useMemo(() => {
    const total = Object.values(benchmarks.data ?? {}).reduce((t, g) => t + num(g.n_ads), 0);
    return {
      total,
      platforms: Object.keys(platCount.data ?? {}).length,
      verticals: Object.keys(vertCount.data ?? {}).length,
    };
  }, [benchmarks.data, platCount.data, vertCount.data]);

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else if (next.size < 3) next.add(key);
      else setStatus("Compare up to 3 benchmarks at a time.");
      return next;
    });

  const applyView = (v: SavedView) => {
    const f = v.state?.filters ?? {};
    for (const k of ["client", "project", "campaign", "platform", "vertical", "market", "objective", "date", "date_from", "date_to"] as const) {
      setFilter(k, (f[k] ?? [])[0] ?? "");
    }
    window.location.assign(v.state?.view ? (VIEW_ROUTES[v.state.view] ?? "/") : "/");
  };

  const createBenchmark = async () => {
    setSaving(true);
    setStatus("");
    try {
      const params = new URLSearchParams();
      params.set("group_by", axis);
      const data = await api<Record<string, BenchRow>>(
        "GET", scopedPath(`/api/benchmarks?${params.toString()}`, new URLSearchParams()),
      );
      const name = `Benchmark — ${AXES.find((a) => a.value === axis)?.label} ${new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`;
      await api("POST", "/api/views", { name, state: { filters: {}, kpi: filters.kpi, view: "benchmark" } });
      void data;
      const list = await api<SavedView[]>("GET", "/api/views");
      setViews(Array.isArray(list) ? list : []);
      setStatus(`Saved ${name}.`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Could not save benchmark.");
    } finally {
      setSaving(false);
    }
  };

  const onExport = async () => {
    setExportBusy(true);
    setStatus("");
    try {
      const res = await fetch("/api/exports/benchmarks", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error("Export Failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "benchmarks.csv";
      a.click();
      URL.revokeObjectURL(url);
      setStatus(`Exported ${rows.length} benchmark group${rows.length === 1 ? "" : "s"}.`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Export Failed");
    } finally {
      setExportBusy(false);
    }
  };

  const metricVal = (r: BenchRow, m: "cpm" | "ctr" | "vtr" | "cpa" | "roas"): number | null => {
    if (m === "ctr") return r.ctr == null ? null : r.ctr * 100;
    if (m === "roas") return r.roas;
    if (m === "cpa") return r.cpa;
    if (m === "cpm") return r.impressions ? (r.spend / r.impressions) * 1000 : null;
    return null;
  };

  return (
    <>
      <PageHeader
        title="Benchmarks Library"
        sub="Discover, save, and manage benchmarks to guide stronger creative decisions."
        actions={(
          <LoadingButton type="button" className="btn-primary" loading={saving} loadingLabel="Saving…" disabled={saving} onClick={() => void createBenchmark()}>
            <Icon name="plus" size={16} /> Create Benchmark
          </LoadingButton>
        )}
      />
      <Panel title="Benchmark Filters">
        <div className="filter-grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
          <div className="field">
            <label htmlFor="b-client">Client</label>
            <select id="b-client" value={filters.client} onChange={(e) => setFilter("client", e.target.value)}>
              <option value="all">All Clients</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="b-vertical">Vertical</label>
            <select id="b-vertical" value={filters.vertical} onChange={(e) => setFilter("vertical", e.target.value)}>
              <option value="all">All Verticals</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="b-platform">Platform</label>
            <select id="b-platform" value={filters.platform} onChange={(e) => setFilter("platform", e.target.value)}>
              <option value="all">All Platforms</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="b-market">Market</label>
            <select id="b-market" value={filters.market} onChange={(e) => setFilter("market", e.target.value)}>
              <option value="all">All Markets</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="b-objective">Campaign Objective</label>
            <select id="b-objective" value={filters.objective} onChange={(e) => setFilter("objective", e.target.value)}>
              <option value="all">All Objectives</option>
              <option value="awareness">Awareness</option>
              <option value="conversions">Conversions</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="b-funnel">Funnel Stage</label>
            <select id="b-funnel" value={filters.funnel} onChange={(e) => setFilter("funnel", e.target.value)}>
              <option value="all">All Stages</option>
              <option value="upper">Upper</option>
              <option value="mid">Mid</option>
              <option value="lower">Lower</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="b-axis">Group By</label>
            <select id="b-axis" value={axis} onChange={(e) => { setAxis(e.target.value as Axis); setSelected(new Set()); }}>
              {AXES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
          </div>
          <div className="field">
            <span className="field-label" aria-hidden="true">&nbsp;</span>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button type="button" className="link-teal" onClick={clearFilters}
                style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Icon name="reset" size={15} /> Reset Filters
              </button>
              <button type="button" className="btn-primary" onClick={() => setApplied((n) => n + 1)}>
                Apply Filters
              </button>
            </div>
          </div>
        </div>
      </Panel>
      {status ? <p className="panel-sub" role="status" style={{ margin: "12px 0 0" }}>{status}</p> : null}
      <div className="main-rail" style={{ marginTop: 16 }}>
        <div className="rail-stack">
          <Panel title="Saved Benchmarks" sub="Quick access to your saved benchmark sets."
            action={<Link className="link-teal" to="/insights">View All</Link>}>
            {views === null ? <Skeleton height={90} /> : (
              views.length ? (
                <div className="cards-4" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
                  {views.slice(0, 4).map((v) => (
                    <button key={v.id} type="button" className="cmp-card" onClick={() => applyView(v)}
                      style={{ textAlign: "left", cursor: "pointer" }}>
                      <span className="insight-ico" style={{ background: "#DFF5F1", marginBottom: 8 }}>
                        <Icon name="bookmark" size={20} />
                      </span>
                      <strong style={{ display: "block", fontSize: 13.5 }}>{v.name}</strong>
                      <span className="panel-sub">{Object.keys(v.state?.filters ?? {}).length} filter axes · Opens {(VIEW_ROUTES[v.state?.view ?? ""] ?? "/")}</span>
                    </button>
                  ))}
                </div>
              ) : <EmptyState text="No saved benchmarks yet. Use Create Benchmark to save the current setup." />
            )}
          </Panel>
          <Panel
            title="Benchmark Results"
            sub="Benchmarks computed from available campaign performance in the current scope."
            action={(
              <div style={{ display: "flex", gap: 8 }}>
                <LoadingButton type="button" className="btn-outline" loading={exportBusy} loadingLabel="Exporting…" spinnerClass="spinner dark" disabled={exportBusy} onClick={() => void onExport()}>
                  <Icon name="download" size={15} /> Export
                </LoadingButton>
              </div>
            )}
          >
            {benchmarks.data ? (
              rows.length ? (
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th scope="col"><input type="checkbox" aria-label="Select all benchmarks"
                          checked={rows.length > 0 && rows.every((r) => selected.has(r.key))}
                          onChange={() => setSelected(rows.every((r) => selected.has(r.key)) ? new Set() : new Set(rows.map((r) => r.key)))} /></th>
                        <th scope="col">Benchmark Name</th>
                        <th scope="col">Coverage</th>
                        <th scope="col">Platform</th>
                        <th scope="col" className="num">CPM</th>
                        <th scope="col" className="num">CTR</th>
                        <th scope="col" className="num">CPA</th>
                        <th scope="col" className="num">ROAS</th>
                        <th scope="col" className="num">Records</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.key}>
                          <td>
                            <input type="checkbox" aria-label={`Select ${axisLabel(axis, r.key)}`}
                              checked={selected.has(r.key)} onChange={() => toggle(r.key)} />
                          </td>
                          <td><span className="cell-main">{axisLabel(axis, r.key)}</span></td>
                          <td>All {axis === "platform" ? "Verticals" : "Platforms"}</td>
                          <td>{axis === "platform" ? axisLabel(axis, r.key) : "All Platforms"}</td>
                          <td className="num">{metricVal(r, "cpm") == null ? "—" : fmtMoney(metricVal(r, "cpm") as number)}</td>
                          <td className="num">{metricVal(r, "ctr") == null ? "—" : `${(metricVal(r, "ctr") as number).toFixed(1)}%`}</td>
                          <td className="num">{metricVal(r, "cpa") == null ? "—" : fmtMoney(metricVal(r, "cpa") as number)}</td>
                          <td className="num">{r.roas == null ? "—" : `${r.roas.toFixed(1)}x`}</td>
                          <td className="num">{num(r.n_ads).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState text="No benchmarks in the current scope." />
            ) : benchmarks.error ? (
              <EmptyState text={benchmarks.error} />
            ) : <Skeleton height={200} />}
          </Panel>
          <Panel title="Compare Benchmarks" sub="Select up to 3 benchmarks to compare key metrics."
            action={selected.size ? (
              <button type="button" className="link-teal" onClick={() => setSelected(new Set())}>Clear All</button>
            ) : undefined}>
            {compared.length >= 2 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 12 }}>
                {(["cpm", "ctr", "cpa", "roas"] as const).map((m) => (
                  <div key={m} className="cmp-card" style={{ padding: 12 }}>
                    <strong style={{ fontSize: 13 }}>{m.toUpperCase()}</strong>
                    <MiniBars
                      values={compared.map((r) => metricVal(r, m) ?? 0)}
                      format={(v) => (m === "ctr" ? `${v.toFixed(1)}%` : m === "roas" ? `${v.toFixed(1)}x` : fmtMoney(v))}
                    />
                    <div className="legend" style={{ justifyContent: "flex-start" }}>
                      {compared.map((r) => <span key={r.key}>{axisLabel(axis, r.key)}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            ) : <EmptyState text="Tick at least two benchmark rows above to compare them here." />}
          </Panel>
        </div>
        <div className="rail-stack">
          <Panel title="Benchmark Insights" sub="Understand the data behind these benchmarks.">
            <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 10 }}>
              <span className="insight-ico" style={{ background: "#DFF5F1" }}>
                <Icon name="bars" size={22} />
              </span>
              <div>
                <p className="panel-sub" style={{ margin: 0 }}>Benchmark Coverage</p>
                <strong style={{ fontSize: 26 }}>{coverage.total.toLocaleString()}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>Total Records</p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <div className="cmp-card" style={{ flex: 1, textAlign: "center" }}>
                <strong>{coverage.platforms}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>Platforms</p>
              </div>
              <div className="cmp-card" style={{ flex: 1, textAlign: "center" }}>
                <strong>{coverage.verticals}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>Verticals</p>
              </div>
              <div className="cmp-card" style={{ flex: 1, textAlign: "center" }}>
                <strong>{AXES.length}</strong>
                <p className="panel-sub" style={{ margin: 0 }}>Groupings</p>
              </div>
            </div>
          </Panel>
          <Panel title="Performance Context">
            <p className="panel-sub">
              These benchmarks are computed from the campaigns in your current scope — use them as a
              starting point and consider your unique goals, audience, and creative strategy.
            </p>
          </Panel>
          <Panel title="Tips for Better Benchmarks">
            <ul className="rec-list">
              <li>Use relevant filters to narrow the dataset</li>
              <li>Include multiple platforms for broader insights</li>
              <li>Compare against similar verticals and objectives</li>
              <li>Save custom benchmarks for future use</li>
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
