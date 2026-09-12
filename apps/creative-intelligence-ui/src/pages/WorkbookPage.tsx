import { useMemo, useState } from "react";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  CreativeThumb,
  EmptyState,
  PageHeader,
  Panel,
  Skeleton,
  fmtCompact,
  fmtMoney,
  fmtMult,
  useCompare,
  useScopedApi,
} from "@/components/product";

interface CreativeRow {
  creative_key: string;
  name?: string;
  campaigns?: string[];
  duration_s?: number | null;
  metrics?: {
    impressions?: number | null;
    ctr?: number | null;
    roas?: number | null;
  };
  annotation?: { duration_s?: number | null } | null;
}

const MODULES = [
  { id: "summary", title: "Campaign Summary", body: "Overview of performance across selected campaigns.", icon: "bars", tint: "#E7F1FB" },
  { id: "breakdown", title: "Creative Breakdown", body: "Detailed performance by creative, with metrics and thumbnails.", icon: "play", tint: "#EFEAFB" },
  { id: "benchmarks", title: "Benchmarks", body: "Compare against industry or custom benchmarks.", icon: "bars", tint: "#E7F1FB" },
  { id: "compare", title: "Compare", body: "Side-by-side comparison of campaigns or creatives.", icon: "compare", tint: "#FBF3E2" },
  { id: "insights", title: "Insights", body: "Key trends, patterns, and takeaways.", icon: "trend", tint: "#FCECEA" },
  { id: "recommendations", title: "Recommendations", body: "AI-powered suggestions to improve performance.", icon: "spark", tint: "#E5F5EC" },
  { id: "export", title: "Data Export", body: "Include raw data tables and export options.", icon: "report", tint: "#EFEAFB" },
];

const KPI_CHOICES = ["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"];

const TEMPLATES = [
  { id: "executive", title: "Executive Summary", body: "High-level overview with key insights and recommendations.", modules: ["summary", "insights", "recommendations"], kpis: ["Impressions", "Clicks", "ROAS"] },
  { id: "deepdive", title: "Creative Performance Deep Dive", body: "Detailed creative analysis with benchmarks and comparisons.", modules: ["breakdown", "benchmarks", "compare", "insights"], kpis: ["Impressions", "CTR", "CVR", "ROAS"] },
  { id: "platform", title: "Platform Comparison", body: "Compare performance across platforms and channels.", modules: ["summary", "benchmarks", "compare"], kpis: ["Impressions", "Clicks", "Spend", "ROAS"] },
  { id: "monthly", title: "Monthly Performance Report", body: "Track trends and performance over time.", modules: ["summary", "breakdown", "insights", "export"], kpis: ["Impressions", "Clicks", "CTR", "Conversions", "Spend"] },
  { id: "custom", title: "Custom Template", body: "Start with a clean workbook and build your own.", modules: [], kpis: ["Impressions"] },
];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export function WorkbookPage() {
  const [modules, setModules] = useState<string[]>(MODULES.map((m) => m.id));
  const [name, setName] = useState("Q1 2024 Creative Performance Report");
  const [description, setDescription] = useState("");
  const [kpis, setKpis] = useState<string[]>(["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"]);
  const [template, setTemplate] = useState("executive");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const compare = useCompare();
  const creatives = useScopedApi<CreativeRow[]>("/api/creatives");

  const top = useMemo(() => {
    const rows = creatives.data ?? [];
    return rows.slice().sort((a, b) => num(b.metrics?.impressions) - num(a.metrics?.impressions)).slice(0, 3);
  }, [creatives.data]);

  const toggleModule = (id: string) =>
    setModules((prev) => (prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]));
  const toggleKpi = (k: string) =>
    setKpis((prev) => (prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k]));

  const applyTemplate = (id: string) => {
    const t = TEMPLATES.find((x) => x.id === id);
    if (!t) return;
    setTemplate(id);
    setModules(t.modules);
    setKpis(t.kpis);
    if (t.id !== "custom") setName("Q1 2024 Creative Performance Report");
  };

  const resetAll = () => {
    setModules(MODULES.map((m) => m.id));
    setName("Q1 2024 Creative Performance Report");
    setDescription("");
    setKpis(["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"]);
    setTemplate("executive");
    setStatus("");
  };

  const createWorkbook = async () => {
    setBusy(true);
    setStatus("");
    try {
      const res = await fetch("/api/analyst/workbook");
      if (!res.ok) throw new Error(`Workbook export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "foap-analyst-workbook.xlsx";
      a.click();
      URL.revokeObjectURL(url);
      setStatus("Workbook downloaded. Module and KPI selections shape the preview above; the export carries the blank analyst template.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Workbook export failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Blank Workbook"
        sub="Create a custom report workbook to analyze, compare, and share your creative performance insights."
        actions={(
          <span className="link-teal" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="info" size={16} /> Learn About Workbooks
          </span>
        )}
      />
      <Panel title="1. Configure Your Workbook" sub="Select the modules and options you want to include in your workbook.">
        <div className="cards-4">
          {MODULES.map((m) => {
            const on = modules.includes(m.id);
            return (
              <button
                key={m.id}
                type="button"
                className="cmp-card"
                aria-pressed={on}
                onClick={() => toggleModule(m.id)}
                style={{ textAlign: "left", cursor: "pointer", borderColor: on ? "var(--shell-teal)" : undefined }}
              >
                <span style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <input type="checkbox" checked={on} readOnly aria-hidden="true" tabIndex={-1} />
                  <span className="insight-ico" style={{ background: m.tint }}>
                    <Icon name={m.icon} size={20} />
                  </span>
                  <span>
                    <strong style={{ display: "block", fontSize: 14 }}>{m.title}</strong>
                    <span className="panel-sub">{m.body}</span>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </Panel>
      <div className="wb-rail">
        <Panel title="2. Workbook Details">
          <div className="field">
            <label htmlFor="wb-name">Workbook Name</label>
            <input id="wb-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field" style={{ marginTop: 12 }}>
            <label htmlFor="wb-desc">Description (Optional)</label>
            <textarea
              id="wb-desc"
              rows={4}
              maxLength={200}
              placeholder="Add a brief description for your workbook…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ width: "100%", boxSizing: "border-box", border: "1px solid var(--shell-line)", borderRadius: 8, padding: "9px 11px", fontFamily: "inherit", fontSize: 13.5 }}
            />
            <p className="panel-sub" style={{ textAlign: "right" }}>{description.length}/200</p>
          </div>
          <p style={{ fontSize: 13, fontWeight: 700, margin: "8px 0" }}>Select KPIs to Include</p>
          <div className="chip-row">
            {kpis.map((k) => (
              <button key={k} type="button" className="chip" aria-pressed="true" onClick={() => toggleKpi(k)}>
                {k} <Icon name="x" size={12} />
              </button>
            ))}
            <select aria-label="Add KPI" value="" onChange={(e) => { if (e.target.value) toggleKpi(e.target.value); }}>
              <option value="">+ Add KPI</option>
              {KPI_CHOICES.filter((c) => !kpis.includes(c)).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </Panel>
        <Panel title="3. Workbook Preview" action={<span className="link-teal">⛶ Full Screen</span>}>
          {compare && creatives.data ? (
            <div>
              <p style={{ fontSize: 13, fontWeight: 700 }}>1. Campaign Summary</p>
              <div className="cards-4" style={{ gap: 8 }}>
                <div className="cmp-card" style={{ padding: 10 }}>
                  <strong>{fmtCompact(num(compare.metrics.impressions?.current))}</strong>
                  <p className="panel-sub">Impressions</p>
                </div>
                <div className="cmp-card" style={{ padding: 10 }}>
                  <strong>{fmtCompact(num(compare.metrics.clicks?.current))}</strong>
                  <p className="panel-sub">Clicks</p>
                </div>
                <div className="cmp-card" style={{ padding: 10 }}>
                  <strong>{fmtMoney(num(compare.metrics.spend?.current))}</strong>
                  <p className="panel-sub">Spend</p>
                </div>
                <div className="cmp-card" style={{ padding: 10 }}>
                  <strong>{fmtMult(num(compare.metrics.roas?.current))}</strong>
                  <p className="panel-sub">ROAS</p>
                </div>
              </div>
              <p style={{ fontSize: 13, fontWeight: 700, marginTop: 12 }}>2. Creative Breakdown</p>
              {top.length ? (
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr><th>#</th><th>Creative</th><th>Campaign</th><th className="num">Impr.</th><th className="num">CTR</th><th className="num">ROAS</th></tr>
                    </thead>
                    <tbody>
                      {top.map((c, i) => (
                        <tr key={c.creative_key}>
                          <td className="idx">{i + 1}</td>
                          <td>
                            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <CreativeThumb seed={c.creative_key} duration={c.annotation?.duration_s ?? c.duration_s} label={c.name} />
                              <span className="cell-main">{c.name || c.creative_key}</span>
                            </span>
                          </td>
                          <td>{c.campaigns?.[0] ?? "—"}</td>
                          <td className="num">{fmtCompact(num(c.metrics?.impressions))}</td>
                          <td className="num">{c.metrics?.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</td>
                          <td className="num">{c.metrics?.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState text="No creatives in the current scope." />}
              <p className="panel-sub" style={{ marginTop: 8 }}>
                Modules: {modules.length ? modules.join(", ") : "none selected"} · KPIs: {kpis.join(", ") || "none"}
              </p>
            </div>
          ) : <Skeleton height={280} />}
        </Panel>
        <Panel title="4. Quick-Start Templates" sub="Start with a pre-built template and customize it.">
          <div className="rail-stack">
            {TEMPLATES.map((t) => (
              <button
                key={t.id}
                type="button"
                className="cmp-card"
                aria-pressed={template === t.id}
                onClick={() => applyTemplate(t.id)}
                style={{ textAlign: "left", cursor: "pointer", borderColor: template === t.id ? "var(--shell-teal)" : undefined }}
              >
                <strong style={{ display: "block", fontSize: 14 }}>{t.title}</strong>
                <span className="panel-sub">{t.body}</span>
              </button>
            ))}
          </div>
        </Panel>
      </div>
      {status ? <p className="panel-sub" role="status" style={{ marginTop: 12 }}>{status}</p> : null}
      <Panel title="Finish Your Workbook">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <button type="button" className="btn-outline" onClick={() => applyTemplate(template)}>
            <Icon name="report" size={16} /> Duplicate from Template
          </button>
          <span style={{ display: "flex", gap: 10 }}>
            <button type="button" className="btn-outline" onClick={resetAll}>Cancel</button>
            <LoadingButton type="button" className="btn-primary" loading={busy} loadingLabel="Creating…" disabled={busy} onClick={() => void createWorkbook()}>
              Create Workbook
            </LoadingButton>
          </span>
        </div>
      </Panel>
    </>
  );
}
