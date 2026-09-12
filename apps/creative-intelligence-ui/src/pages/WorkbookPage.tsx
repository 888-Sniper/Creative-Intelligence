import { useEffect, useMemo, useState } from "react";
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

// Brand single-source: served by the backend from Web/assets
// (GET /foap-logo.png); never duplicated into the frontend tree.
const FOAP_LOGO = "/foap-logo.png";

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
  { id: "summary", title: "Campaign Summary", body: "Performance overview across selected campaigns.", icon: "bars", tint: "#DFF3F0" },
  { id: "breakdown", title: "Creative Breakdown", body: "Per-creative metrics with thumbnails.", icon: "play", tint: "#EFEAFB" },
  { id: "benchmarks", title: "Benchmarks", body: "Compare against industry or custom benchmarks.", icon: "bars", tint: "#E7F1FB" },
  { id: "compare", title: "Compare", body: "Side-by-side campaigns or creatives.", icon: "compare", tint: "#FBF3E2" },
  { id: "insights", title: "Insights", body: "Key trends, patterns, and takeaways.", icon: "trend", tint: "#FCECEA" },
  { id: "recommendations", title: "Recommendations", body: "AI-powered suggestions to improve performance.", icon: "spark", tint: "#E5F5EC" },
  { id: "export", title: "Data Export", body: "Raw data tables and export options.", icon: "report", tint: "#F0E9FA" },
];

const KPI_CHOICES = ["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"];

const TEMPLATES = [
  { id: "executive", title: "Executive Summary", body: "High-level overview with key insights and recommendations.", icon: "bars", tint: "#DFF3F0", modules: ["summary", "insights", "recommendations"], kpis: ["Impressions", "Clicks", "ROAS"] },
  { id: "deepdive", title: "Creative Performance Deep Dive", body: "Detailed creative analysis with benchmarks and comparisons.", icon: "play", tint: "#EFEAFB", modules: ["breakdown", "benchmarks", "compare", "insights"], kpis: ["Impressions", "CTR", "CVR", "ROAS"] },
  { id: "platform", title: "Platform Comparison", body: "Compare performance across platforms and channels.", icon: "compare", tint: "#E7F1FB", modules: ["summary", "benchmarks", "compare"], kpis: ["Impressions", "Clicks", "Spend", "ROAS"] },
  { id: "monthly", title: "Monthly Performance Report", body: "Track trends and performance over time.", icon: "trend", tint: "#E5F5EC", modules: ["summary", "breakdown", "insights", "export"], kpis: ["Impressions", "Clicks", "CTR", "Conversions", "Spend"] },
  { id: "custom", title: "Custom Template", body: "Start with a clean workbook and build your own.", icon: "report", tint: "#F0E9FA", modules: [], kpis: ["Impressions"] },
];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/* Finished-report miniature shared by the inline preview and the
 * fullscreen dialog. Blocks hide/show with the selected modules:
 * Campaign Summary owns the KPI block, Creative Breakdown owns the
 * creative table. */
function PreviewDoc({ name, today, modules, kpis, previewKpis, top }: {
  name: string | null | undefined; today: string; modules: string[]; kpis: string[];
  previewKpis: { label: string; value: string }[];
  top: { creative_key: string; name?: string | null; metrics?: Record<string, number | null> | null;
    annotation?: { duration_s?: number | null } | null; duration_s?: number | null }[];
}) {
  const showSummary = modules.includes("summary");
  const showBreakdown = modules.includes("breakdown");
  return (
    <div className="wb-doc">
      <div className="wb-doc-head">
        <img src={FOAP_LOGO} alt="Foap" style={{ height: 22, width: "auto" }} />
        <div style={{ minWidth: 0 }}>
          <strong style={{ display: "block", fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {name || "Untitled Workbook"}
          </strong>
          <span className="panel-sub" style={{ fontSize: 11.5 }}>{today} · Finished-report preview from live workspace data</span>
        </div>
      </div>
      <div className="wb-doc-body">
        {showSummary ? (
          previewKpis.length ? (
            <div className="wb-kpis-auto">
              {previewKpis.map((k) => (
                <div key={k.label} style={{ background: "var(--shell-bg)", border: "1px solid var(--shell-line)", borderRadius: 8, padding: "8px 10px" }}>
                  <strong style={{ display: "block", fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{k.value}</strong>
                  <span className="panel-sub" style={{ fontSize: 11 }}>{k.label}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState text="Select KPIs to preview the summary block." />
        ) : null}
        {showBreakdown ? (
          top.length ? (
            <div className="tbl-wrap" style={{ marginTop: 8 }}>
              <table className="tbl" style={{ fontSize: 12.5 }}>
                <thead>
                  <tr><th>#</th><th>Creative</th><th className="num">Impr.</th><th className="num">CTR</th><th className="num">ROAS</th></tr>
                </thead>
                <tbody>
                  {top.map((c, i) => (
                    <tr key={c.creative_key}>
                      <td className="idx">{i + 1}</td>
                      <td>
                        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <CreativeThumb seed={c.creative_key} duration={c.annotation?.duration_s ?? c.duration_s} label={c.name ?? undefined} />
                          <span className="cell-main" style={{ fontSize: 12.5 }}>{c.name || c.creative_key}</span>
                        </span>
                      </td>
                      <td className="num">{fmtCompact(num(c.metrics?.impressions))}</td>
                      <td className="num">{c.metrics?.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</td>
                      <td className="num">{c.metrics?.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState text="No creatives in the current scope." />
        ) : null}
        {!showSummary && !showBreakdown ? (
          <EmptyState text="Enable Campaign Summary or Creative Breakdown to preview workbook content." />
        ) : null}
        <p className="panel-sub" style={{ marginTop: 8, fontSize: 11.5 }}>
          Modules: {modules.length ? modules.map((id) => MODULES.find((m) => m.id === id)?.title ?? id).join(", ") : "none selected"} · KPIs: {kpis.join(", ") || "none"}
        </p>
      </div>
    </div>
  );
}

export function WorkbookPage() {
  const [modules, setModules] = useState<string[]>(MODULES.map((m) => m.id));
  const [name, setName] = useState("Q1 2024 Creative Performance Report");
  const [description, setDescription] = useState("");
  const [kpis, setKpis] = useState<string[]>(["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"]);
  const [template, setTemplate] = useState("executive");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [learnOpen, setLearnOpen] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);

  const compare = useCompare();
  const creatives = useScopedApi<CreativeRow[]>("/api/creatives");

  useEffect(() => {
    if (!fullScreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullScreen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [fullScreen]);

  const top = useMemo(() => {
    const rows = creatives.data ?? [];
    return rows.slice().sort((a, b) => num(b.metrics?.impressions) - num(a.metrics?.impressions)).slice(0, 4);
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

  /* The export carries the user's configuration: name, description,
   *  modules and KPIs travel as query params and land on a cover
   *  sheet (backend build_blank_workbook cover=...). */
  const createWorkbook = async () => {
    setBusy(true);
    setStatus("");
    try {
      const params = new URLSearchParams();
      if (name.trim()) params.set("name", name.trim());
      if (description.trim()) params.set("description", description.trim());
      if (modules.length) params.set("modules", modules.join(","));
      if (kpis.length) params.set("kpis", kpis.join(","));
      const res = await fetch(`/api/analyst/workbook?${params.toString()}`, {
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error(`Workbook export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "foap-analyst-workbook.xlsx";
      a.click();
      URL.revokeObjectURL(url);
      setStatus(`Workbook downloaded: ${modules.length} module${modules.length === 1 ? "" : "s"} and ${kpis.length} KPI${kpis.length === 1 ? "" : "s"} recorded on the cover sheet.`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Workbook export failed.");
    } finally {
      setBusy(false);
    }
  };

  const today = new Date().toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
  /* Preview KPIs follow the SELECTED KPI list (not a fixed four), so
   * the preview always agrees with the chips above and the export. */
  const previewKpis = useMemo(() => {
    if (!compare) return [];
    const m = compare.metrics;
    const get = (label: string): string => {
      switch (label) {
        case "Impressions": return fmtCompact(num(m.impressions?.current));
        case "Clicks": return fmtCompact(num(m.clicks?.current));
        case "CTR": {
          const v = m.ctr?.current;
          return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
        }
        case "CVR": {
          const conv = num(m.conversions?.current);
          const cl = num(m.clicks?.current);
          return cl ? `${((conv / cl) * 100).toFixed(1)}%` : "—";
        }
        case "ROAS": {
          const v = m.roas?.current;
          return v == null ? "—" : fmtMult(v);
        }
        case "CPA": {
          const v = m.cpa?.current;
          return v == null ? "—" : fmtMoney(v);
        }
        case "Spend": return fmtMoney(num(m.spend?.current));
        case "Conversions": return fmtCompact(num(m.conversions?.current));
        default: return "—";
      }
    };
    return kpis.map((k) => ({ label: k, value: get(k) }));
  }, [compare, kpis]);

  return (
    <>
      <PageHeader
        title="Blank Workbook"
        sub="Create a custom report workbook to analyze, compare, and share your creative performance insights."
        actions={(
          <button type="button" className="link-teal" aria-expanded={learnOpen}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            onClick={() => setLearnOpen((v) => !v)}>
            <Icon name="info" size={16} /> Learn About Workbooks
          </button>
        )}
      />
      {learnOpen ? (
        <div className="panel" style={{ marginBottom: 12 }}>
          <p className="panel-sub" style={{ margin: 0 }}>
            A workbook bundles the modules and KPIs you pick into a reusable XLSX file:
            seven blank analysis sheets plus a cover sheet recording this workbook&apos;s
            name and selections. Fill the Input sheet with creative data and the
            formulas recalculate offline.
          </p>
        </div>
      ) : null}
      <Panel title="1. Configure Your Workbook" sub="Select the modules and options you want to include in your workbook.">
        <div className="cards-4" style={{ gap: 10 }}>
          {MODULES.map((m) => {
            const on = modules.includes(m.id);
            return (
              <button
                key={m.id}
                type="button"
                className="cmp-card"
                aria-pressed={on}
                onClick={() => toggleModule(m.id)}
                style={{ textAlign: "left", cursor: "pointer", padding: 12, overflow: "hidden", background: m.tint, borderColor: on ? "var(--shell-teal)" : "var(--shell-line)", opacity: on ? 1 : 0.6 }}
              >
                <span style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <input type="checkbox" checked={on} readOnly aria-hidden="true" tabIndex={-1} style={{ marginTop: 3 }} />
                  <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 42, height: 42, borderRadius: 12, background: "rgba(255,255,255,.75)", flex: "0 0 auto" }}>
                    <Icon name={m.icon} size={22} />
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", fontSize: 13 }}>{m.title}</strong>
                    <span className="panel-sub" style={{ fontSize: 12 }}>{m.body}</span>
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
          <div className="field" style={{ marginTop: 10 }}>
            <label htmlFor="wb-desc">Description (Optional)</label>
            <textarea
              id="wb-desc"
              rows={3}
              maxLength={200}
              placeholder="Add a brief description for your workbook…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ width: "100%", boxSizing: "border-box", border: "1px solid var(--shell-line)", borderRadius: 8, padding: "9px 11px", fontFamily: "inherit", fontSize: 13.5 }}
            />
            <p className="panel-sub" style={{ textAlign: "right" }}>{description.length}/200</p>
          </div>
          <p style={{ fontSize: 13, fontWeight: 700, margin: "6px 0" }}>Select KPIs to Include</p>
          <div className="chip-row">
            {kpis.map((k) => (
              <button key={k} type="button" className="chip" aria-label={`Remove ${k} from workbook`} onClick={() => toggleKpi(k)}>
                {k} <Icon name="x" size={12} />
              </button>
            ))}
            <select aria-label="Add KPI" value="" onChange={(e) => { if (e.target.value) toggleKpi(e.target.value); }}>
              <option value="">+ Add KPI</option>
              {KPI_CHOICES.filter((c) => !kpis.includes(c)).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </Panel>
        <Panel
          title="3. Workbook Preview"
          action={(
            <button type="button" className="link-teal" onClick={() => setFullScreen(true)}>
              ⛶ Full Screen
            </button>
          )}
        >
          {compare && creatives.data ? (
            <PreviewDoc name={name} today={today} modules={modules} kpis={kpis}
              previewKpis={previewKpis} top={top} />
          ) : <Skeleton height={280} />}
        </Panel>
        <Panel title="4. Quick-Start Templates" sub="Start with a pre-built template and customize it.">
          <div className="rail-stack" style={{ gap: 8 }}>
            {TEMPLATES.map((t) => (
              <button
                key={t.id}
                type="button"
                className="cmp-card"
                aria-pressed={template === t.id}
                onClick={() => applyTemplate(t.id)}
                style={{ textAlign: "left", cursor: "pointer", padding: "10px 12px", borderColor: template === t.id ? "var(--shell-teal)" : undefined }}
              >
                <span style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span className="insight-ico" aria-hidden="true" style={{ background: t.tint, flex: "0 0 auto" }}>
                    <Icon name={t.icon} size={18} />
                  </span>
                  <span>
                    <strong style={{ display: "block", fontSize: 13 }}>{t.title}</strong>
                    <span className="panel-sub" style={{ fontSize: 12 }}>{t.body}</span>
                  </span>
                </span>
              </button>
            ))}
          </div>
        </Panel>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 8, padding: "8px 4px", borderTop: "1px solid var(--shell-line)" }}>
        <strong style={{ fontSize: 13.5 }}>Finish Your Workbook</strong>
        {status ? <span className="panel-sub" role="status" style={{ margin: 0, flex: "1 1 auto", minWidth: 200 }}>{status}</span> : <span style={{ flex: "1 1 auto" }} />}
        <button type="button" className="btn-outline" onClick={() => applyTemplate(template)}>
          <Icon name="report" size={16} /> Duplicate from Template
        </button>
        <button type="button" className="btn-outline" onClick={resetAll}>Cancel</button>
        <LoadingButton type="button" className="btn-primary" loading={busy} loadingLabel="Creating…" disabled={busy} onClick={() => void createWorkbook()}>
          Create Workbook
        </LoadingButton>
      </div>
      {fullScreen ? (
        <div className="modal-overlay" onClick={() => setFullScreen(false)}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-label="Workbook preview"
            onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <strong style={{ fontSize: 14 }}>{name || "Untitled Workbook"}</strong>
              <span style={{ flex: "1 1 auto" }} />
              <button type="button" className="btn-outline" onClick={() => setFullScreen(false)}>
                Close
              </button>
            </div>
            {compare && creatives.data ? (
              <PreviewDoc name={name} today={today} modules={modules} kpis={kpis}
                previewKpis={previewKpis} top={top} />
            ) : <Skeleton height={280} />}
          </div>
        </div>
      ) : null}
    </>
  );
}
