import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { EmptyState, PageHeader, Panel, Skeleton, useCampaignMeta } from "@/components/product";

interface SampleFileRow {
  key: string; name: string; format: string; mime: string;
  bytes: number; created_at: string; url: string;
}

const KPI_OPTIONS = [
  "spend",
  "impressions",
  "clicks",
  "conversions",
  "cpm",
  "vtr",
  "view_rate",
  "ctr",
  "cpc",
  "cpa",
  "roas",
];

type TFn = (key: string, vars?: Record<string, string | number>) => string;

/** UI copy rule: Title Case labels, true acronyms (CPA/CTR/…) stay caps. */
const KPI_FALLBACK: Record<string, string> = {
  vtr: "VTR (Completed)",
  view_rate: "Play Rate",
  spend: "Spend",
  impressions: "Impressions",
  clicks: "Clicks",
  conversions: "Conversions",
  cpm: "CPM",
  ctr: "CTR",
  cpc: "CPC",
  cpa: "CPA",
  roas: "ROAS",
};
const kpiLabel = (t: TFn, k: string): string => {
  if (k === "vtr") return t("compare.vtrCompleted");
  if (k === "view_rate") return t("compare.playRate");
  const key = `filters.kpis.${k}`;
  const hit = t(key);
  return hit === key ? (KPI_FALLBACK[k] ?? k.toUpperCase()) : hit;
};

const BENCH_OPTIONS = [
  "industry",
  "hook_type",
  "creator_vs_branded",
  "edit_style",
  "platform",
  "campaign",
];

type ReportFormat = "pptx" | "xlsx" | "one-pager" | "csv" | "workbook";

const FORMATS: Array<ReportFormat> = ["pptx", "xlsx", "one-pager"];
const FORMAT_TITLES: Record<ReportFormat, string> = {
  pptx: "PPTX",
  xlsx: "XLSX",
  "one-pager": "One-Pager",
  csv: "CSV",
  workbook: "Workbook",
};
const FORMAT_BODY_KEYS: Record<ReportFormat, string> = {
  pptx: "reports.fmtPptx",
  xlsx: "reports.fmtXlsx",
  "one-pager": "reports.fmtOnePager",
  csv: "reports.fmtXlsx",
  workbook: "reports.kindWorkbook",
};

interface ReportResponse {
  format?: string;
  markdown?: string;
  csv?: string;
  filename?: string;
  pptx_b64?: string;
  xlsx_b64?: string;
}

interface HistoryRow {
  id: string;
  title: string;
  kind: string;
  status: "Completed" | "Generating" | "Failed";
  format: ReportFormat;
  created: string;
  by: string;
  chips: string[];
  href: string | null;
  filename: string | null;
  isDemo: boolean;
  body: Record<string, unknown> | null;
  note?: string;
  /** Persisted sample-pack file key (backend /api/sample-files). */
  sampleKey?: string;
}

const HISTORY_KEY = "ci-reports-history";

function errMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/** Legacy scope_filters(): active top-filter-bar scope as {axis: [value]}. */
function scopeFilterBody(scope: URLSearchParams): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  scope.forEach((value, key) => {
    const list = out[key];
    if (list) list.push(value);
    else out[key] = [value];
  });
  return out;
}

function useAdminFlag(): boolean {
  try {
    return useAuth().me?.is_admin === true;
  } catch {
    return false;
  }
}

function b64Download(filename: string, mime: string, b64: string): { filename: string; href: string } {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return { filename, href: URL.createObjectURL(new Blob([arr], { type: mime })) };
}

function textDownload(filename: string, mime: string, text: string): { filename: string; href: string } {
  return { filename, href: URL.createObjectURL(new Blob([text], { type: mime })) };
}

const DEMO_AUTHORS = ["Alex Smith", "Jamie Davis", "Morgan Kim", "Casey Lee", "Sam Rivera"];
const DEMO_DATES = [
  "Mar 31, 2024 10:42 AM",
  "Mar 28, 2024 2:15 PM",
  "Mar 25, 2024 11:03 AM",
  "Mar 24, 2024 4:27 PM",
  "Mar 20, 2024 9:18 AM",
  "Mar 15, 2024 1:56 PM",
  "Mar 12, 2024 3:41 PM",
  "Mar 10, 2024 12:05 PM",
];

/** Deterministic demo history derived from the demo campaign catalog.
 *  Clearly synthetic (is_demo): demo campaign names only, neutral copy,
 *  and every row regenerates through POST /api/report on demand. */
function demoHistory(t: TFn, tp: (key: string, count: number, vars?: Record<string, string | number>) => string, campaigns: string[]): HistoryRow[] {
  const kinds = [t("reports.demoKinds.k0"), t("reports.demoKinds.k1"), t("reports.demoKinds.k2"), t("reports.demoKinds.k3")];
  return campaigns.slice(0, 8).map((c, i) => ({
    id: `demo-${i}`,
    title: `${c} ${t(`reports.demoTitles.t${i % 8}`)}`,
    kind: kinds[i % kinds.length],
    status: i === 3 ? "Generating" : i === 6 ? "Failed" : "Completed",
    format: (["pptx", "xlsx", "one-pager"] as ReportFormat[])[i % 3],
    created: DEMO_DATES[i % DEMO_DATES.length],
    by: DEMO_AUTHORS[i % DEMO_AUTHORS.length],
    chips: i % 2 ? [t("reports.allCampaigns"), "ROAS"] : [tp("reports.campChip", 3, { count: 3 }), t("reports.kpiChip", { count: 5 }), "+2"],
    href: null,
    filename: null,
    isDemo: true,
    body: {
      campaigns: [c],
      kpis: ["spend", "impressions", "clicks", "ctr", "roas"],
      benchmark: "hook_type",
      benchmark_scope: "filters",
      rank_by: "cpa",
      override: false,
      strict_human: false,
      filters: {},
    },
  }));
}

function loadSessionHistory(): HistoryRow[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const rows = JSON.parse(raw) as HistoryRow[];
    return rows.map((r) => ({ ...r, href: null }));
  } catch {
    return [];
  }
}

function FormatBadge({ format }: { format: ReportFormat }) {
  return (
    <span className={`fmt-badge fmt-${format}`}>
      <Icon name="report" size={14} />
      {format === "one-pager" ? "One-Pager" : format.toUpperCase()}
    </span>
  );
}

function StatusPill({ status }: { status: HistoryRow["status"] }) {
  const { t } = useLocale();
  if (status === "Generating") {
    return (
      <span className="pill pill-info">
        <span className="spinner" aria-hidden="true" /> {t("reports.status.generating")}
      </span>
    );
  }
  if (status === "Failed") {
    return (
      <span className="pill pill-bad">
        <Icon name="x" size={12} /> {t("reports.status.failed")}
      </span>
    );
  }
  return (
    <span className="pill pill-ok">
      <Icon name="check" size={12} /> {t("reports.status.completed")}
    </span>
  );
}

/** Single-cell Date Range popover for the generator row: one button shows
 *  the active range (or All Time) and opens From/To inputs. Same repFrom /
 *  repTo state as the old joined control — only the presentation fits its
 *  grid cell so all four config fields share one row. */
function ReportRangeField({ from, to, onFrom, onTo }: {
  from: string; to: string; onFrom: (v: string) => void; onTo: (v: string) => void;
}) {
  const { t, fmtDate } = useLocale();
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
  const short = (iso: string) => {
    if (!iso) return "";
    return fmtDate(iso, { month: "short", day: "numeric", year: "numeric" });
  };
  const f = short(from);
  const toShort = short(to);
  const label = f || toShort ? `${f || "…"} – ${toShort || "…"}` : t("filters.allTime");
  return (
    <div className="field">
      <label id="rep-range-label">{t("filters.dateRange")}</label>
      <div className="daterange" ref={boxRef}>
        <button type="button" className="daterange-btn" aria-labelledby="rep-range-label rep-range-val"
          aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Icon name="calendar" size={15} />
          <span id="rep-range-val">{label}</span>
        </button>
        {open ? (
          <div className="daterange-pop" role="group" aria-labelledby="rep-range-label">
            <div className="field">
              <label htmlFor="rep-range-from">{t("filters.from")}</label>
              <input id="rep-range-from" type="date" aria-label={t("reports.fromDateAria")} value={from}
                onChange={(e) => onFrom(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="rep-range-to">{t("filters.to")}</label>
              <input id="rep-range-to" type="date" aria-label={t("reports.toDateAria")} value={to}
                onChange={(e) => onTo(e.target.value)} />
            </div>
            <div className="daterange-actions">
              <button type="button" className="link-teal"
                onClick={() => { onFrom(""); onTo(""); }}>
                {t("common.clear")}
              </button>
              <button type="button" className="btn-primary" onClick={() => setOpen(false)}>
                {t("common.done")}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function MultiCheck({
  id,
  label,
  options,
  checked,
  onToggle,
  empty,
  selectedKey,
}: {
  id: string;
  label: string;
  options: Array<{ value: string; label: string }>;
  checked: string[];
  onToggle: (v: string) => void;
  empty: string;
  selectedKey: string;
}) {
  const { tp } = useLocale();
  const [open, setOpen] = useState(false);
  const text = checked.length
    ? tp(selectedKey, checked.length, { count: checked.length })
    : empty;
  return (
    <div className="field">
      <label id={`${id}-label`}>{label}</label>
      <div className="multicheck">
        <button
          type="button"
          className="multicheck-btn"
          aria-labelledby={`${id}-label ${id}-btn`}
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <span id={`${id}-btn`}>{text}</span>
          <Icon name="chev" size={14} />
        </button>
        {open ? (
          <div className="multicheck-pop" role="group" aria-label={label}>
            {options.map((o) => (
              <label key={o.value} className="multicheck-opt">
                <input
                  type="checkbox"
                  checked={checked.includes(o.value)}
                  onChange={() => onToggle(o.value)}
                />{" "}
                {o.label}
              </label>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Generated Reports (reskinned): approved layout over POST /api/report.
 *  Campaign/KPI multi-selects, benchmark + date range, PPTX/XLSX/One-Pager
 *  outputs, in-session history plus regenerable synthetic demo rows. */
export function ReportsPage() {
  const { scope, filters } = useFilters();
  const { t, tp, fmtDate } = useLocale();
  const [campaigns, setCampaigns] = useState<string[] | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [checkedCampaigns, setCheckedCampaigns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<string[]>(["spend", "impressions", "clicks", "ctr", "roas"]);
  const [benchmark, setBenchmark] = useState("industry");
  /* Report-scoped range: validated From/To dates that override the
   * global scope inside the generated report request. Empty follows
   * the global scope (never a decorative free-text field). */
  const [repFrom, setRepFrom] = useState("");
  const [repTo, setRepTo] = useState("");
  const [format, setFormat] = useState<ReportFormat>("pptx");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [history, setHistory] = useState<HistoryRow[]>(() => loadSessionHistory());
  const isAdmin = useAdminFlag();
  /* Persisted sample-pack files from the backend report-history API
   * (never a render-time fixture): list + download for every
   * employee; delete stays admin-gated. */
  const [sampleFiles, setSampleFiles] = useState<SampleFileRow[] | null>(null);
  const [sampleError, setSampleError] = useState("");
  const loadSampleFiles = useCallback(async () => {
    try {
      const r = await api<{ files: SampleFileRow[] }>("GET", "/api/sample-files");
      setSampleFiles(Array.isArray(r.files) ? r.files : []);
      setSampleError("");
    } catch (e) {
      setSampleFiles([]);
      setSampleError(e instanceof Error ? e.message : t("reports.requestFailed"));
    }
  }, []);
  useEffect(() => { void loadSampleFiles(); }, [loadSampleFiles]);
  const [deletingSample, setDeletingSample] = useState<string | null>(null);
  const deleteSampleFile = async (key: string) => {
    if (deletingSample) return;
    setDeletingSample(key);
    try {
      await api("DELETE", `/api/admin/demo/pack/files/${encodeURIComponent(key)}`);
      await loadSampleFiles();
    } catch (e) {
      setSampleError(e instanceof Error ? e.message : t("reports.requestFailed"));
    } finally {
      setDeletingSample(null);
    }
  };
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All Statuses");
  const [formatFilter, setFormatFilter] = useState("All Formats");
  const [timeFilter, setTimeFilter] = useState("All Time");
  /* Synthetic demo history renders ONLY in demo workspaces (backend
   * source="demo" signal). A real workspace never sees fabricated
   * report rows just because campaigns exist. */
  const demoMode = useCampaignMeta().data?.demo === true;

  const hrefs = useRef<string[]>([]);
  useEffect(() => {
    const list = hrefs.current;
    return () => {
      for (const h of list) URL.revokeObjectURL(h);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setCampaigns(null);
    setCatalogError("");
    api<Record<string, unknown>>("GET", scopedPath("/api/campaigns", scope))
      .then((c) => {
        if (cancelled) return;
        const needle = filters.campaign.trim().toLowerCase();
        const keys = Object.keys(c).filter((k) => !needle || k.toLowerCase().includes(needle));
        setCampaigns(keys);
        setCheckedCampaigns(keys);
      })
      .catch((err) => {
        if (!cancelled) setCatalogError(errMessage(err, t("reports.failedCatalog")));
      });
    return () => {
      cancelled = true;
    };
  }, [scope, filters.campaign]);

  const toggle = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  /** Legacy report_body(): unchecked-everything campaigns send null,
   *  unchecked-everything KPIs fall back to cpa + ctr. The visible
   *  Date Range always lands in filters (report-scoped From/To win
   *  over the global scope; empty follows the global scope). */
  const reportBody = (): Record<string, unknown> => ({
    campaigns: checkedCampaigns.length ? checkedCampaigns : null,
    kpis: kpis.length ? kpis : ["cpa", "ctr"],
    benchmark: benchmark === "industry" ? "hook_type" : benchmark,
    benchmark_scope: "filters",
    rank_by: "cpa",
    override: false,
    strict_human: false,
    filters: {
      ...scopeFilterBody(scope),
      ...(repFrom ? { date_from: [repFrom] } : {}),
      ...(repTo ? { date_to: [repTo] } : {}),
    },
  });

  const buildDownload = (fmt: ReportFormat, r: ReportResponse) => {
    if (fmt === "pptx") {
      return b64Download(
        r.filename ?? "campaign-report.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        r.pptx_b64 ?? "",
      );
    }
    if (fmt === "xlsx") {
      return b64Download(
        r.filename ?? "campaign-report.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        r.xlsx_b64 ?? "",
      );
    }
    return textDownload("one-pager.md", "text/markdown", r.markdown ?? "");
  };

  /* Atomic history updates: overlapping generations each apply to
   *  the latest list instead of a stale closure snapshot. */
  const applyHistory = (fn: (prev: HistoryRow[]) => HistoryRow[]) => {
    setHistory((prev) => {
      const next = fn(prev);
      try {
        window.localStorage.setItem(
          HISTORY_KEY,
          JSON.stringify(next.filter((r) => !r.isDemo).map(({ href: _h, ...rest }) => rest)),
        );
      } catch {
        /* private mode: history simply does not persist */
      }
      return next;
    });
  };

  const runReport = async (fmt: ReportFormat, body: Record<string, unknown>, title: string, chips: string[], rowId?: string) => {
    if (rowId) {
      applyHistory((prev) => prev.map((h) => (h.id === rowId ? { ...h, status: "Generating" as const, note: "" } : h)));
    } else {
      setBusy(true);
    }
    setStatus("");
    try {
      const r = await api<ReportResponse>("POST", "/api/report", { ...body, format: fmt });
      const dl = buildDownload(fmt, r);
      hrefs.current.push(dl.href);
      const row: HistoryRow = {
        id: rowId ?? `sess-${Date.now()}`,
        title,
        kind: fmt === "pptx" ? t("reports.kindPptx") : fmt === "xlsx" ? t("reports.kindXlsx") : t("reports.kindOnePager"),
        status: "Completed",
        format: fmt,
        created: fmtDate(new Date().toISOString(), { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }),
        by: t("reports.byYou"),
        chips,
        href: dl.href,
        filename: dl.filename,
        isDemo: false,
        body,
      };
      applyHistory((prev) => (rowId ? prev.map((h) => (h.id === rowId ? row : h)) : [row, ...prev]));
      setStatus(t("reports.builtMsg", { fmt: FORMAT_TITLES[fmt] ?? fmt, file: dl.filename }));
    } catch (err) {
      const message = errMessage(err, t("reports.blockedFallback"));
      if (rowId) {
        applyHistory((prev) => prev.map((h) => (h.id === rowId ? { ...h, status: "Failed" as const, note: message } : h)));
      }
      setStatus(t("reports.blockedMsg", { message }));
    } finally {
      if (!rowId) setBusy(false);
    }
  };

  const generate = () => {
    const n = checkedCampaigns.length;
    const title = n === 1
      ? t("reports.titleOne", { name: checkedCampaigns[0] })
      : n > 1 ? t("reports.titleN", { count: n }) : t("reports.titleWorkspace");
    void runReport(format, reportBody(), title, [
      n ? tp("reports.campChip", n, { count: n }) : t("reports.allCampaigns"),
      t("reports.kpiChip", { count: kpis.length || 2 }),
      "+2",
    ]);
  };

  const saveTemplate = () => {
    try {
      window.localStorage.setItem("ci-report-template", JSON.stringify({ campaigns: checkedCampaigns, kpis, benchmark, format }));
      setStatus(t("reports.templateSaved"));
    } catch {
      setStatus(t("reports.templateFailed"));
    }
  };

  const sampleRows: HistoryRow[] = (sampleFiles ?? []).map((f) => ({
    id: `sample:${f.key}`,
    title: f.name.replace(/\.[^.]+$/, ""),
    kind: f.format === "workbook" ? t("reports.kindWorkbook") : t("reports.kindSample"),
    status: "Completed",
    format: f.format as ReportFormat,
    created: f.created_at ? fmtDate(f.created_at,
      { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "",
    by: t("reports.bySample"),
    chips: [t("reports.sampleDataChip"), f.format],
    href: f.url,
    filename: f.name,
    isDemo: false,
    body: null,
    sampleKey: f.key,
  }));

  const rows = useMemo(() => {
    const demo = demoMode && campaigns ? demoHistory(t, tp, campaigns) : [];
    const merged = [...sampleRows, ...history.filter((h) => !h.isDemo), ...demo];
    const q = query.trim().toLowerCase();
    const windowDays = timeFilter === "Last 7 Days" ? 7 : timeFilter === "Last 30 Days" ? 30 : 0;
    return merged.filter((r) => {
      if (statusFilter !== "All Statuses" && r.status !== statusFilter) return false;
      if (formatFilter !== "All Formats" && r.format !== formatFilter) return false;
      if (windowDays) {
        const t = new Date(r.created).getTime();
        if (!Number.isFinite(t) || Date.now() - t > windowDays * 86400000) return false;
      }
      if (q && !`${r.title} ${r.kind} ${r.by}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [history, sampleFiles, campaigns, demoMode, query, statusFilter, formatFilter, timeFilter, t, tp]);

  const latest = useMemo(() => rows.filter((r) => r.status === "Completed").slice(0, 5), [rows]);
  const isFiltered = Boolean(query) || statusFilter !== "All Statuses" || formatFilter !== "All Formats" || timeFilter !== "All Time";
  const resetListFilters = () => {
    setQuery("");
    setStatusFilter("All Statuses");
    setFormatFilter("All Formats");
    setTimeFilter("All Time");
  };

  return (
    <>
      <PageHeader
        title={t("reports.title")}
        sub={t("reports.sub")}
      />
      <div className="main-rail">
        <div className="rail-stack">
          <Panel
            title={t("reports.newTitle")}
            sub={t("reports.newSub")}
            action={(
              <button type="button" className="btn-outline" onClick={saveTemplate}>
                <Icon name="bookmark" size={15} /> {t("reports.saveTemplate")}
              </button>
            )}
          >
            {catalogError ? <EmptyState text={catalogError} /> : null}
            <div className="filter-grid fg-4">
              <MultiCheck
                id="rep-camp"
                label={t("reports.campaignsLabel")}
                empty={t("reports.allCampaigns")}
                selectedKey="reports.campSelected"
                options={(campaigns ?? []).map((c) => ({ value: c, label: c }))}
                checked={checkedCampaigns}
                onToggle={(v) => setCheckedCampaigns((p) => toggle(p, v))}
              />
              <MultiCheck
                id="rep-kpi"
                label={t("reports.kpisLabel")}
                empty={t("reports.selectKpis")}
                selectedKey="reports.kpiSelected"
                options={KPI_OPTIONS.map((k) => ({ value: k, label: kpiLabel(t, k) }))}
                checked={kpis}
                onToggle={(v) => setKpis((p) => toggle(p, v))}
              />
              <div className="field">
                <label htmlFor="rep-bench">{t("reports.benchLabel")}</label>
                <select id="rep-bench" value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
                  {BENCH_OPTIONS.map((o) => <option key={o} value={o}>{t(`reports.bench.${o}`)}</option>)}
                </select>
              </div>
              <ReportRangeField from={repFrom} to={repTo} onFrom={setRepFrom} onTo={setRepTo} />
            </div>
            <p style={{ fontSize: 13, fontWeight: 700, margin: "10px 0 6px" }}>{t("reports.outputFormat")}</p>
            <div className="fmt-row">
              {FORMATS.map((f) => {
                const on = format === f;
                return (
                  <button
                    key={f}
                    type="button"
                    className={`fmt-card${on ? " on" : ""}`}
                    aria-pressed={on}
                    onClick={() => setFormat(f)}
                  >
                    <span className="fmt-ico"><Icon name="report" size={20} /></span>
                    <span>
                      <strong>{FORMAT_TITLES[f]}</strong>
                      <span className="panel-sub">{t(FORMAT_BODY_KEYS[f])}</span>
                    </span>
                    <span className={`fmt-radio${on ? " on" : ""}`} aria-hidden="true">
                      {on ? <Icon name="check" size={12} /> : null}
                    </span>
                  </button>
                );
              })}
              <div className="fmt-go">
                <LoadingButton type="button" className="btn-primary" loading={busy} loadingLabel={t("reports.generating")} disabled={busy || campaigns === null} onClick={generate}>
                  <Icon name="spark" size={16} /> {t("reports.generate")}
                </LoadingButton>
                <p className="panel-sub">{t("reports.estTime")}</p>
              </div>
            </div>
            {status ? <p className="panel-sub" role="status" style={{ marginTop: 8 }}>{status}</p> : null}
            {sampleError ? <p className="panel-sub" role="alert" style={{ marginTop: 8 }}>{t("reports.sampleUnavailable", { error: sampleError })}</p> : null}
          </Panel>
          <Panel
            title={t("reports.listTitle")}
            sub={t("reports.listSub")}
            style={{ flex: "1 0 auto" }}
            action={(
              <span className="rep-filters">
                <span className="rep-search">
                  <Icon name="search" size={14} />
                  <input aria-label={t("reports.searchAria")} placeholder={t("reports.searchPlaceholder")} value={query} onChange={(e) => setQuery(e.target.value)} />
                </span>
                <select aria-label={t("reports.statusAria")} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  <option value="All Statuses">{t("reports.allStatuses")}</option>
                  {(["Completed", "Generating", "Failed"] as const).map((o) => (
                    <option key={o} value={o}>{t(`reports.status.${o.toLowerCase()}`)}</option>
                  ))}
                </select>
                <select aria-label={t("reports.formatAria")} value={formatFilter} onChange={(e) => setFormatFilter(e.target.value)}>
                  <option value="All Formats">{t("reports.allFormats")}</option>
                  {(["pptx", "xlsx", "one-pager"] as const).map((o) => <option key={o} value={o}>{FORMAT_TITLES[o]}</option>)}
                </select>
                <select aria-label={t("reports.timeAria")} value={timeFilter} onChange={(e) => setTimeFilter(e.target.value)}>
                  {(["All Time", "Last 7 Days", "Last 30 Days"] as const).map((o) => (
                    <option key={o} value={o}>{t(`pageInsights.dates.${o === "All Time" ? "all" : o === "Last 7 Days" ? "d7" : "d30"}`)}</option>
                  ))}
                </select>
              </span>
            )}
          >
            {campaigns === null && !catalogError ? (
              <Skeleton height={220} />
            ) : rows.length ? (

              <div className="tbl-wrap">
                <table className="tbl rep-tbl">
                  <thead>
                    <tr>
                      <th scope="col">{t("reports.headers.report")}</th>
                      <th scope="col">{t("reports.headers.status")}</th>
                      <th scope="col">{t("reports.headers.format")}</th>
                      <th scope="col">{t("reports.headers.created")}</th>
                      <th scope="col">{t("reports.headers.by")}</th>
                      <th scope="col">{t("reports.headers.filters")}</th>
                      <th scope="col"><span className="sr-only">{t("reports.headers.actions")}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id}>
                        <td>
                          <strong className="cell-main" style={{ display: "block" }}>{r.title}</strong>
                          <span className="panel-sub">{r.kind}</span>
                        </td>
                        <td><StatusPill status={r.status} /></td>
                        <td><FormatBadge format={r.format} /></td>
                        <td>{r.created}</td>
                        <td>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }}>
                            <span className="avatar" aria-hidden="true">
                              {r.by.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                            </span>
                            {r.by}
                          </span>
                        </td>
                        <td>
                          <span className="chip-row">
                            {r.chips.map((c) => <span key={c} className="chip-static">{c}</span>)}
                          </span>
                        </td>
                        <td>
                          <span className="row-actions">
                            {r.sampleKey && isAdmin ? (
                              <button type="button" className="icon-btn"
                                aria-label={t("reports.deleteRow", { title: r.title })}
                                disabled={deletingSample !== null}
                                onClick={() => void deleteSampleFile(r.sampleKey as string)}>
                                <Icon name="x" size={16} />
                              </button>
                            ) : null}
                            {r.href ? (
                              <a className="icon-btn" download={r.filename ?? "report"} href={r.href} aria-label={t("reports.downloadRow", { title: r.title })}>
                                <Icon name="download" size={16} />
                              </a>
                            ) : r.status === "Generating" ? (
                              <span className="icon-btn" aria-label={t("reports.generatingRow", { title: r.title })}>
                                <span className="spinner" aria-hidden="true" />
                              </span>
                            ) : (
                              <button
                                type="button"
                                className="icon-btn"
                                aria-label={r.status === "Failed" ? t("reports.retryRow", { title: r.title }) : t("reports.downloadRow", { title: r.title })}
                                title={r.note ?? t("reports.regenTitle")}
                                onClick={() => r.body && void runReport(r.format, r.body, r.title, r.chips, r.id)}
                              >
                                <Icon name="download" size={16} />
                              </button>
                            )}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-center">
                <EmptyState compact icon="report" title={isFiltered ? t("reports.noMatchTitle") : t("reports.noReportsTitle")} text={isFiltered ? t("reports.noMatchBody") : t("reports.noReportsBody")} />
              </div>
            )}
          </Panel>
        </div>
        <div className="rail-stack">
          <Panel title={t("reports.tipsTitle")}>
            <ul className="tips-list">
              <li>
                <span className="insight-ico"><Icon name="bars" size={18} /></span>
                <div><h4>{t("reports.tips.kpiTitle")}</h4><p>{t("reports.tips.kpiBody")}</p></div>
              </li>
              <li>
                <span className="insight-ico"><Icon name="target" size={18} /></span>
                <div><h4>{t("reports.tips.audienceTitle")}</h4><p>{t("reports.tips.audienceBody")}</p></div>
              </li>
              <li>
                <span className="insight-ico"><Icon name="report" size={18} /></span>
                <div><h4>{t("reports.tips.formatTitle")}</h4><p>{t("reports.tips.formatBody")}</p></div>
              </li>
              <li>
                <span className="insight-ico"><Icon name="users" size={18} /></span>
                <div><h4>{t("reports.tips.benchTitle")}</h4><p>{t("reports.tips.benchBody")}</p></div>
              </li>
            </ul>
          </Panel>
          <Panel title={t("reports.latestTitle")} style={{ flex: "1 0 auto" }}>
            {latest.length ? (
              <ul className="tips-list">
                {latest.map((r) => (
                  <li key={r.id} style={{ padding: "10px 0" }}>
                    <span className="file-thumb" aria-hidden="true"><Icon name="report" size={18} /></span>
                    <div style={{ flex: 1 }}>
                      <h4>{r.title}</h4>
                      <p>{r.created}</p>
                    </div>
                    <FormatBadge format={r.format} />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState compact icon="report" title={t("reports.noFilesTitle")} text={t("reports.noFilesBody")} />
            )}
            <button type="button" className="btn-outline" style={{ width: "100%", marginTop: 8 }}
              onClick={resetListFilters}>
              {t("reports.viewAll")} <Icon name="chev" size={14} />
            </button>
          </Panel>
        </div>
      </div>
    </>
  );
}
