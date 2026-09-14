import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Icon } from "@/components/icons";
import { useLocale } from "@/i18n";
import { LoadingButton } from "@/components/LoadingButton";
import {
  CreativeThumb,
  EmptyState,
  Panel,
  Skeleton,
  fmtCell,
  fmtCompact,
  fmtMult,
  fmtPct,
  kpiDisplay,
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

/* Module/template titles and bodies render through the UI locale
 *  (§9): ids stay stable (selection state, export params) while the
 *  display copy follows workbook.modules.* / workbook.templates.*. */
const MODULES = [
  { id: "summary", icon: "bars", tint: "#E3F2EF" },
  { id: "breakdown", icon: "play", tint: "#ECEAF6" },
  { id: "benchmarks", icon: "bars", tint: "#E6EFF7" },
  { id: "compare", icon: "compare", tint: "#F6F1E4" },
  { id: "insights", icon: "trend", tint: "#F7ECEA" },
  { id: "recommendations", icon: "spark", tint: "#E6F2EA" },
  { id: "export", icon: "report", tint: "#ECE8F4" },
];

const KPI_CHOICES = ["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"];

const TEMPLATES = [
  { id: "executive", icon: "bars", tint: "#E3F2EF", modules: ["summary", "insights", "recommendations"], kpis: ["Impressions", "Clicks", "ROAS"] },
  { id: "deepdive", icon: "play", tint: "#ECEAF6", modules: ["breakdown", "benchmarks", "compare", "insights"], kpis: ["Impressions", "CTR", "CVR", "ROAS"] },
  { id: "platform", icon: "compare", tint: "#E6EFF7", modules: ["summary", "benchmarks", "compare"], kpis: ["Impressions", "Clicks", "Spend", "ROAS"] },
  { id: "monthly", icon: "trend", tint: "#E6F2EA", modules: ["summary", "breakdown", "insights", "export"], kpis: ["Impressions", "Clicks", "CTR", "Conversions", "Spend"] },
  { id: "custom", icon: "report", tint: "#ECE8F4", modules: [], kpis: ["Impressions"] },
];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** Explicit keyboard-focus (and hover) tooltip (§15): the explanation
 *  bubble opens on focus as well as hover — never on the browser
 *  `title` attribute alone. Escape and outside dismissal come from
 *  the owning control where a dialog is involved. */
function FocusTip({ label, children }: { label: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);
  return (
    <span className="trend-tooltip-anchor"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}>
      {children}
      {show ? <span className="kpi-tip" role="status">{label}</span> : null}
    </span>
  );
}

/* Finished-report miniature shared by the inline preview and the
 * fullscreen dialog. Blocks hide/show with the selected modules:
 * Campaign Summary owns the KPI block, Creative Breakdown owns the
 * creative table. */
function PreviewDoc({ name, today, modules, previewKpis, top }: {
  name: string | null | undefined; today: string; modules: string[];
  previewKpis: { label: string; value: string }[];
  top: { creative_key: string; name?: string | null; metrics?: Record<string, number | null> | null;
    annotation?: { duration_s?: number | null } | null; duration_s?: number | null }[];
}) {
  const { t, locale } = useLocale();
  const unavailable = t("workbook.unavailable");
  const kpiName = (id: string) => {
    const key = `workbook.kpis.${id.toLowerCase()}`;
    const hit = t(key);
    return hit === key ? id : hit;
  };
  const showSummary = modules.includes("summary");
  const showBreakdown = modules.includes("breakdown");
  return (
    <div className="wb-doc">
      <div className="wb-doc-head">
        <img src={FOAP_LOGO} alt="Foap" style={{ height: 22, width: "auto" }} />
        <div style={{ minWidth: 0, marginLeft: 7 }}>
          <strong style={{ display: "block", fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {name || t("workbook.untitled")}
          </strong>
          <span className="panel-sub" style={{ fontSize: 11.5 }}>{today} · {t("workbook.previewCaption")}</span>
        </div>
      </div>
      <div className="wb-doc-body">
        {showSummary ? (
          previewKpis.length ? (
            <div className="wb-kpis-auto">
              {previewKpis.map((k) => (
                <div key={k.label} style={{ background: "var(--shell-bg)", border: "1px solid var(--shell-line)", borderRadius: 8, padding: "8px 10px" }}>
                  <strong style={{ display: "block", fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{k.value}</strong>
                  <span className="panel-sub" style={{ fontSize: 11 }}>{kpiName(k.label)}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState text={t("workbook.selectKpisHint")} />
        ) : null}
        {showBreakdown ? (
          top.length ? (
            <div className="tbl-wrap" style={{ marginTop: 8 }}>
              <table className="tbl" style={{ fontSize: 12.5 }}>
                <thead>
                  <tr><th>#</th><th>{t("workbook.previewTable.creative")}</th><th className="num">{t("workbook.previewTable.impressions")}</th><th className="num">{t("workbook.previewTable.ctr")}</th><th className="num">{t("workbook.previewTable.roas")}</th></tr>
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
                      <td className="num">{fmtCompact(num(c.metrics?.impressions), locale)}</td>
                      <td className="num">{fmtCell(c.metrics?.ctr, (n) => fmtPct(n * 100, 1, locale), unavailable)}</td>
                      <td className="num">{fmtCell(c.metrics?.roas, (n) => fmtMult(n, locale), unavailable)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState text={t("workbook.noCreativesInScope")} verbatim />
        ) : null}
        {!showSummary && !showBreakdown ? (
          <EmptyState text={t("workbook.enableBlocksHint")} />
        ) : null}
      </div>
    </div>
  );
}

export function WorkbookPage() {
  const { t, tp, fmtDate, locale } = useLocale();
  const unavailable = t("workbook.unavailable");
  const kpiName = (id: string) => {
    const key = `workbook.kpis.${id.toLowerCase()}`;
    const hit = t(key);
    return hit === key ? id : hit;
  };
  const [modules, setModules] = useState<string[]>(MODULES.map((m) => m.id));
  const [name, setName] = useState("Q1 2024 Creative Performance Report");
  const [description, setDescription] = useState("");
  const [kpis, setKpis] = useState<string[]>(["Impressions", "Clicks", "CTR", "CVR", "ROAS", "CPA", "Spend", "Conversions"]);
  const [template, setTemplate] = useState("executive");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [learnOpen, setLearnOpen] = useState(false);
  const [helpHover, setHelpHover] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);

  const compare = useCompare();
  const creatives = useScopedApi<CreativeRow[]>("/api/creatives");

  useEffect(() => {
    if (!fullScreen && !learnOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setFullScreen(false);
        setLearnOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [fullScreen, learnOpen]);

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
      if (!res.ok) throw new Error(`${t("workbook.exportFailed")} (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "foap-analyst-workbook.xlsx";
      a.click();
      URL.revokeObjectURL(url);
      setStatus(t("workbook.downloaded", {
        modules: modules.length,
        modulesLabel: tp("workbook.module", modules.length),
        kpis: kpis.length,
        kpisLabel: tp("workbook.kpi", kpis.length),
      }));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : t("workbook.exportFailed"));
    } finally {
      setBusy(false);
    }
  };

  // Current-date label: format the full instant so the selected time zone
  // yields today, not yesterday (a date-only string parses as UTC
  // midnight, which shifts the day for positive-offset zones).
  const today = fmtDate(new Date().toISOString());
  /* Preview KPIs follow the SELECTED KPI list (not a fixed four), so
   * the preview always agrees with the chips above and the export. */
  const previewKpis = useMemo(() => {
    if (!compare) return [];
    const m = compare.metrics;
    const empty = compare.current_n_ads === 0;
    const ratioPct = (v: number | null | undefined): string => {
      if (v == null) return empty ? fmtPct(0, 1, locale) : unavailable;
      return fmtPct(v * 100, 1, locale);
    };
    const get = (label: string): string => {
      switch (label) {
        case "Impressions": return kpiDisplay("count", m.impressions?.current, empty, locale, unavailable);
        case "Clicks": return kpiDisplay("count", m.clicks?.current, empty, locale, unavailable);
        case "CTR": return ratioPct(m.ctr?.current);
        case "CVR": {
          const conv = m.conversions?.current;
          const cl = m.clicks?.current;
          if (cl == null || cl === 0) return empty ? fmtPct(0, 1, locale) : unavailable;
          if (conv == null) return unavailable;
          return fmtPct((conv / cl) * 100, 1, locale);
        }
        case "ROAS": return kpiDisplay("mult", m.roas?.current, empty, locale, unavailable);
        case "CPA": return kpiDisplay("money", m.cpa?.current, empty, locale, unavailable);
        case "Spend": return kpiDisplay("money", m.spend?.current, empty, locale, unavailable);
        case "Conversions": return kpiDisplay("count", m.conversions?.current, empty, locale, unavailable);
        default: return unavailable;
      }
    };
    return kpis.map((k) => ({ label: k, value: get(k) }));
  }, [compare, kpis, locale, unavailable]);

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <h1 style={{ margin: 0 }}>{t("workbook.title")}</h1>
            <button
              type="button"
              className="icon-btn"
              style={{ width: 26, height: 26 }}
              aria-label={t("workbook.about")}
              aria-expanded={learnOpen || helpHover}
              onClick={() => setLearnOpen((v) => !v)}
              onMouseEnter={() => setHelpHover(true)}
              onMouseLeave={() => setHelpHover(false)}
              onFocus={() => setHelpHover(true)}
              onBlur={() => setHelpHover(false)}
            >
              <Icon name="info" size={15} />
            </button>
          </div>
          <p className="sub">{t("workbook.sub")}</p>
        </div>
      </div>
      {learnOpen || helpHover ? (
        <div className="panel" style={{ marginBottom: 12 }}>
          <p className="panel-sub" style={{ margin: 0 }}>
            {t("workbook.aboutBody")}
          </p>
        </div>
      ) : null}
      <Panel title={t("workbook.configure")} sub={t("workbook.configureSub")}>
        <div className="cards-4" style={{ gap: 10 }}>
          {MODULES.map((m) => {
            const on = modules.includes(m.id);
            return (
              <button
                key={m.id}
                type="button"
                className="cmp-card mod-card"
                aria-pressed={on}
                onClick={() => toggleModule(m.id)}
                style={{ textAlign: "left", cursor: "pointer", padding: 12, overflow: "hidden", borderColor: on ? "var(--shell-teal)" : "var(--shell-line)", opacity: on ? 1 : 0.6, "--card-tint": m.tint } as CSSProperties}
              >
                <span style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <input type="checkbox" checked={on} readOnly aria-hidden="true" tabIndex={-1} style={{ marginTop: 3 }} />
                  <span className="mod-ico" aria-hidden="true">
                    <Icon name={m.icon} size={22} />
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <strong className="mod-title">{t(`workbook.modules.${m.id}Title`)}</strong>
                    <span className="panel-sub" style={{ fontSize: 12 }}>{t(`workbook.modules.${m.id}Body`)}</span>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </Panel>
      <div className="wb-rail">
        <Panel title={t("workbook.details")}>
          <div className="field">
            <label htmlFor="wb-name">{t("workbook.nameLabel")}</label>
            <input id="wb-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field" style={{ marginTop: 10 }}>
            <label htmlFor="wb-desc">{t("workbook.descLabel")}</label>
            <textarea
              id="wb-desc"
              rows={2}
              maxLength={200}
              placeholder={t("workbook.descPlaceholder")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ width: "100%", boxSizing: "border-box", border: "1px solid var(--shell-line)", borderRadius: 8, padding: "9px 11px", fontFamily: "inherit", fontSize: 13.5 }}
            />
            <p className="panel-sub" style={{ textAlign: "right" }}>{description.length}/200</p>
          </div>
          <p style={{ fontSize: 13, fontWeight: 700, margin: "6px 0" }}>{t("workbook.selectKpis")}</p>
          <div className="chip-row">
            {kpis.map((k) => (
              <button key={k} type="button" className="chip" aria-label={t("workbook.removeKpi", { kpi: kpiName(k) })} onClick={() => toggleKpi(k)}>
                {kpiName(k)} <Icon name="x" size={12} />
              </button>
            ))}
            <select aria-label={t("workbook.addKpi")} value="" onChange={(e) => { if (e.target.value) toggleKpi(e.target.value); }}>
              <option value="">+ {t("workbook.addKpi")}</option>
              {KPI_CHOICES.filter((c) => !kpis.includes(c)).map((c) => <option key={c} value={c}>{kpiName(c)}</option>)}
            </select>
          </div>
        </Panel>
        <Panel
          title={t("workbook.preview")}
          action={(
            <FocusTip label={t("workbook.fullScreen")}>
              <button
                type="button"
                className="icon-btn"
                aria-label={t("workbook.fullScreen")}
                onClick={() => setFullScreen(true)}
              >
                <Icon name="expand" size={18} />
              </button>
            </FocusTip>
          )}
        >
          {compare && creatives.data ? (
            <PreviewDoc name={name} today={today} modules={modules}
              previewKpis={previewKpis} top={top} />
          ) : <Skeleton height={280} />}
        </Panel>
        <Panel title={t("workbook.templatesTitle")} sub={t("workbook.templatesSub")}>
          <div className="rail-stack" style={{ gap: 8 }}>
            {TEMPLATES.map((tpl) => (
              <button
                key={tpl.id}
                type="button"
                className="cmp-card mod-card"
                aria-pressed={template === tpl.id}
                onClick={() => applyTemplate(tpl.id)}
                style={{ textAlign: "left", cursor: "pointer", padding: "10px 12px", borderColor: template === tpl.id ? "var(--shell-teal)" : undefined, "--tile-tint": tpl.tint } as CSSProperties}
              >
                <span style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span className="mod-ico" aria-hidden="true">
                    <Icon name={tpl.icon} size={18} />
                  </span>
                  <span>
                    <strong className="mod-title">{t(`workbook.templates.${tpl.id}Title`)}</strong>
                    <span className="panel-sub" style={{ fontSize: 12 }}>{t(`workbook.templates.${tpl.id}Body`)}</span>
                  </span>
                </span>
              </button>
            ))}
          </div>
        </Panel>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 14, padding: "10px 4px", borderTop: "1px solid var(--shell-line)", position: "sticky", bottom: 0, background: "var(--shell-bg)", zIndex: 5 }}>
        {status ? <span className="panel-sub" role="status" style={{ margin: 0, flex: "1 1 auto", minWidth: 200 }}>{status}</span> : <span style={{ flex: "1 1 auto" }} />}
        <button type="button" className="btn-outline" onClick={() => applyTemplate(template)}>
          <Icon name="report" size={16} /> {t("workbook.duplicate")}
        </button>
        <button type="button" className="btn-outline" onClick={resetAll}>{t("workbook.cancel")}</button>
        <LoadingButton type="button" className="btn-primary" loading={busy} loadingLabel={t("workbook.creating")} disabled={busy} onClick={() => void createWorkbook()}>
          {t("workbook.create")}
        </LoadingButton>
      </div>
      {fullScreen ? (
        <div className="modal-overlay" onClick={() => setFullScreen(false)}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-label={t("workbook.previewTitle")}
            onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <strong style={{ fontSize: 14 }}>{name || t("workbook.untitled")}</strong>
              <span style={{ flex: "1 1 auto" }} />
              <FocusTip label={t("workbook.exitFullScreen")}>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={t("workbook.exitFullScreen")}
                  onClick={() => setFullScreen(false)}
                >
                  <Icon name="compress" size={18} />
                </button>
              </FocusTip>
            </div>
            {compare && creatives.data ? (
              <PreviewDoc name={name} today={today} modules={modules}
                previewKpis={previewKpis} top={top} />
            ) : <Skeleton height={280} />}
          </div>
        </div>
      ) : null}
    </>
  );
}
