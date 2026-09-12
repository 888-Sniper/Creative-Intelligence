import { useEffect, useMemo, useRef, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { EmptyState, PageHeader, Panel } from "@/components/product";

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

/** UI copy rule: Title Case labels, true acronyms (CPA/CTR/…) stay caps. */
const KPI_LABELS: Record<string, string> = {
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
const kpiLabel = (k: string): string => KPI_LABELS[k] ?? k.toUpperCase();

const BENCH_OPTIONS = [
  { id: "industry", label: "Scope Average" },
  { id: "hook_type", label: "Hook Type" },
  { id: "creator_vs_branded", label: "Creator Vs Branded" },
  { id: "edit_style", label: "Edit Style" },
  { id: "platform", label: "Platform" },
  { id: "campaign", label: "Campaign" },
];

type ReportFormat = "pptx" | "xlsx" | "one-pager";

const FORMATS: Array<{ id: ReportFormat; title: string; body: string }> = [
  { id: "pptx", title: "PPTX", body: "Presentation Deck" },
  { id: "xlsx", title: "XLSX", body: "Data Workbook" },
  { id: "one-pager", title: "One-Pager", body: "Executive Summary" },
];

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
function demoHistory(campaigns: string[]): HistoryRow[] {
  const kinds = ["Campaign Performance Report", "Platform Deep Dive", "Executive Summary", "Industry Comparison"];
  return campaigns.slice(0, 8).map((c, i) => ({
    id: `demo-${i}`,
    title: `${c} ${["Performance", "Growth Analysis", "Impact", "Benchmark Report", "Digest", "Content Analysis", "ROI Report", "Executive Summary"][i % 8]}`,
    kind: kinds[i % kinds.length],
    status: i === 3 ? "Generating" : i === 6 ? "Failed" : "Completed",
    format: (["pptx", "xlsx", "one-pager"] as ReportFormat[])[i % 3],
    created: DEMO_DATES[i % DEMO_DATES.length],
    by: DEMO_AUTHORS[i % DEMO_AUTHORS.length],
    chips: i % 2 ? ["All Campaigns", "ROAS"] : ["3 Campaigns", "5 KPIs", "+2"],
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
  if (status === "Generating") {
    return (
      <span className="pill pill-info">
        <span className="spinner" aria-hidden="true" /> Generating
      </span>
    );
  }
  if (status === "Failed") {
    return (
      <span className="pill pill-bad">
        <Icon name="x" size={12} /> Failed
      </span>
    );
  }
  return (
    <span className="pill pill-ok">
      <Icon name="check" size={12} /> Completed
    </span>
  );
}

function MultiCheck({
  id,
  label,
  options,
  checked,
  onToggle,
  empty,
}: {
  id: string;
  label: string;
  options: Array<{ value: string; label: string }>;
  checked: string[];
  onToggle: (v: string) => void;
  empty: string;
}) {
  const [open, setOpen] = useState(false);
  const text = checked.length
    ? `${checked.length} ${label} Selected`
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
  const [campaigns, setCampaigns] = useState<string[] | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [checkedCampaigns, setCheckedCampaigns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<string[]>(["spend", "impressions", "clicks", "ctr", "roas"]);
  const [benchmark, setBenchmark] = useState("industry");
  const [dateRange, setDateRange] = useState("Jan 1, 2024 – Mar 31, 2024");
  const [format, setFormat] = useState<ReportFormat>("pptx");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [history, setHistory] = useState<HistoryRow[]>(() => loadSessionHistory());
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All Statuses");
  const [formatFilter, setFormatFilter] = useState("All Formats");

  const hrefs = useRef<string[]>([]);
  useEffect(() => {
    const list = hrefs.current;
    return () => {
      for (const h of list) URL.revokeObjectURL(h);
    };
  }, []);

  const persist = (rows: HistoryRow[]) => {
    setHistory(rows);
    try {
      window.localStorage.setItem(
        HISTORY_KEY,
        JSON.stringify(rows.filter((r) => !r.isDemo).map(({ href: _h, ...rest }) => rest)),
      );
    } catch {
      /* private mode: history simply does not persist */
    }
  };

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
        if (!cancelled) setCatalogError(errMessage(err, "Failed To Load Campaigns."));
      });
    return () => {
      cancelled = true;
    };
  }, [scope, filters.campaign]);

  const toggle = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  /** Legacy report_body(): unchecked-everything campaigns send null,
   *  unchecked-everything KPIs fall back to cpa + ctr. */
  const reportBody = (): Record<string, unknown> => ({
    campaigns: checkedCampaigns.length ? checkedCampaigns : null,
    kpis: kpis.length ? kpis : ["cpa", "ctr"],
    benchmark: benchmark === "industry" ? "hook_type" : benchmark,
    benchmark_scope: "filters",
    rank_by: "cpa",
    override: false,
    strict_human: false,
    filters: scopeFilterBody(scope),
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

  const runReport = async (fmt: ReportFormat, body: Record<string, unknown>, title: string, chips: string[], rowId?: string) => {
    if (rowId) {
      persist(history.map((h) => (h.id === rowId ? { ...h, status: "Generating" as const, note: "" } : h)));
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
        kind: fmt === "pptx" ? "Campaign Performance Report" : fmt === "xlsx" ? "Platform Deep Dive" : "Executive Summary",
        status: "Completed",
        format: fmt,
        created: new Date().toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }),
        by: "You",
        chips,
        href: dl.href,
        filename: dl.filename,
        isDemo: false,
        body,
      };
      persist(rowId ? history.map((h) => (h.id === rowId ? row : h)) : [row, ...history]);
      setStatus(`${FORMATS.find((f) => f.id === fmt)?.title} Built: ${dl.filename}.`);
    } catch (err) {
      const message = errMessage(err, "Report Blocked.");
      if (rowId) {
        persist(history.map((h) => (h.id === rowId ? { ...h, status: "Failed" as const, note: message } : h)));
      }
      setStatus(`BLOCKED: ${message}`);
    } finally {
      if (!rowId) setBusy(false);
    }
  };

  const generate = () => {
    const n = checkedCampaigns.length;
    const title = n === 1 ? `${checkedCampaigns[0]} Performance` : n > 1 ? `${n}-Campaign Performance` : "Workspace Performance";
    void runReport(format, reportBody(), title, [
      n ? `${n} Campaign${n === 1 ? "" : "s"}` : "All Campaigns",
      `${kpis.length || 2} KPIs`,
      "+2",
    ]);
  };

  const saveTemplate = () => {
    try {
      window.localStorage.setItem("ci-report-template", JSON.stringify({ campaigns: checkedCampaigns, kpis, benchmark, format }));
      setStatus("Template Saved.");
    } catch {
      setStatus("Could Not Save Template In This Browser.");
    }
  };

  const rows = useMemo(() => {
    const demo = campaigns ? demoHistory(campaigns) : [];
    const merged = [...history.filter((h) => !h.isDemo), ...demo];
    const q = query.trim().toLowerCase();
    return merged.filter((r) => {
      if (statusFilter !== "All Statuses" && r.status !== statusFilter) return false;
      if (formatFilter !== "All Formats" && r.format !== formatFilter) return false;
      if (q && !`${r.title} ${r.kind} ${r.by}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [history, campaigns, query, statusFilter, formatFilter]);

  const latest = useMemo(() => rows.filter((r) => r.status === "Completed").slice(0, 5), [rows]);

  return (
    <>
      <PageHeader
        title="Generated Reports"
        sub="Create and download custom reports to share insights, track performance, and showcase results."
      />
      <div className="main-rail" style={{ marginTop: 12, gap: 12 }}>
        <div className="rail-stack" style={{ gap: 12 }}>
          <Panel
            title="Generate a New Report"
            sub="Select your content, metrics, and format to create a custom report."
            action={(
              <button type="button" className="btn-outline" onClick={saveTemplate}>
                <Icon name="bookmark" size={15} /> Save as Template
              </button>
            )}
          >
            {catalogError ? <EmptyState text={catalogError} /> : null}
            <div className="filter-grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: "10px 12px" }}>
              <MultiCheck
                id="rep-camp"
                label="Campaigns"
                empty="All Campaigns"
                options={(campaigns ?? []).map((c) => ({ value: c, label: c }))}
                checked={checkedCampaigns}
                onToggle={(v) => setCheckedCampaigns((p) => toggle(p, v))}
              />
              <MultiCheck
                id="rep-kpi"
                label="KPIs"
                empty="Select KPIs"
                options={KPI_OPTIONS.map((k) => ({ value: k, label: kpiLabel(k) }))}
                checked={kpis}
                onToggle={(v) => setKpis((p) => toggle(p, v))}
              />
              <div className="field">
                <label htmlFor="rep-bench">Benchmarks</label>
                <select id="rep-bench" value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
                  {BENCH_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="rep-range">Date Range</label>
                <input id="rep-range" value={dateRange} onChange={(e) => setDateRange(e.target.value)} />
              </div>
            </div>
            <p style={{ fontSize: 13, fontWeight: 700, margin: "10px 0 6px" }}>Output Format</p>
            <div className="fmt-row" style={{ gap: 10 }}>
              {FORMATS.map((f) => {
                const on = format === f.id;
                return (
                  <button
                    key={f.id}
                    type="button"
                    className={`fmt-card${on ? " on" : ""}`}
                    aria-pressed={on}
                    onClick={() => setFormat(f.id)}
                    style={{ padding: "10px 12px" }}
                  >
                    <span className="fmt-ico"><Icon name="report" size={20} /></span>
                    <span>
                      <strong>{f.title}</strong>
                      <span className="panel-sub">{f.body}</span>
                    </span>
                    <span className={`fmt-radio${on ? " on" : ""}`} aria-hidden="true">
                      {on ? <Icon name="check" size={12} /> : null}
                    </span>
                  </button>
                );
              })}
              <div className="fmt-go">
                <LoadingButton type="button" className="btn-primary" loading={busy} loadingLabel="Generating…" disabled={busy || campaigns === null} onClick={generate}>
                  <Icon name="spark" size={16} /> Generate Report
                </LoadingButton>
                <p className="panel-sub">Estimated generation time: 1–2 minutes</p>
              </div>
            </div>
            {status ? <p className="panel-sub" role="status" style={{ marginTop: 8 }}>{status}</p> : null}
          </Panel>
          <Panel
            title="Generated Reports"
            sub="View, download, and manage your previously generated reports."
            action={(
              <span className="rep-filters">
                <span className="rep-search">
                  <Icon name="search" size={14} />
                  <input aria-label="Search reports" placeholder="Search reports…" value={query} onChange={(e) => setQuery(e.target.value)} />
                </span>
                <select aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  {["All Statuses", "Completed", "Generating", "Failed"].map((o) => <option key={o}>{o}</option>)}
                </select>
                <select aria-label="Filter by format" value={formatFilter} onChange={(e) => setFormatFilter(e.target.value)}>
                  {["All Formats", "pptx", "xlsx", "one-pager"].map((o) => <option key={o}>{o}</option>)}
                </select>
                <select aria-label="Filter by time" defaultValue="All Time">
                  <option>All Time</option>
                  <option>Last 7 Days</option>
                  <option>Last 30 Days</option>
                </select>
              </span>
            )}
          >
            {campaigns === null && !catalogError ? (
              <EmptyState text="Loading Reports…" />
            ) : rows.length ? (
              <div className="tbl-wrap">
                <table className="tbl rep-tbl" style={{ fontSize: 13 }}>
                  <thead>
                    <tr>
                      <th scope="col">Report</th>
                      <th scope="col">Status</th>
                      <th scope="col">Format</th>
                      <th scope="col">Created</th>
                      <th scope="col">Created By</th>
                      <th scope="col">Filters Used</th>
                      <th scope="col"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id}>
                        <td style={{ padding: "8px 10px" }}>
                          <strong className="cell-main" style={{ display: "block" }}>{r.title}</strong>
                          <span className="panel-sub">{r.kind}</span>
                        </td>
                        <td style={{ padding: "8px 10px" }}><StatusPill status={r.status} /></td>
                        <td style={{ padding: "8px 10px" }}><FormatBadge format={r.format} /></td>
                        <td style={{ padding: "8px 10px" }}>{r.created}</td>
                        <td style={{ padding: "8px 10px" }}>{r.by}</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span className="chip-row">
                            {r.chips.map((c) => <span key={c} className="chip-static">{c}</span>)}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span className="row-actions">
                            {r.href ? (
                              <a className="icon-btn" download={r.filename ?? "report"} href={r.href} aria-label={`Download ${r.title}`}>
                                <Icon name="download" size={16} />
                              </a>
                            ) : r.status === "Generating" ? (
                              <span className="icon-btn" aria-label={`${r.title} is generating`}>
                                <span className="spinner" aria-hidden="true" />
                              </span>
                            ) : (
                              <button
                                type="button"
                                className="icon-btn"
                                aria-label={r.status === "Failed" ? `Retry ${r.title}` : `Download ${r.title}`}
                                title={r.note ?? "Regenerate through the reporting backend, then download"}
                                onClick={() => r.body && void runReport(r.format, r.body, r.title, r.chips, r.id)}
                              >
                                <Icon name="download" size={16} />
                              </button>
                            )}
                            <button type="button" className="icon-btn" aria-label={`More actions for ${r.title}`}>
                              <Icon name="dots" size={16} />
                            </button>
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState text={query || statusFilter !== "All Statuses" || formatFilter !== "All Formats" ? "No reports match these filters." : "No reports yet. Configure the generator above to create your first report."} />
            )}
          </Panel>
        </div>
        <div className="rail-stack" style={{ gap: 12 }}>
          <Panel title="Reporting Tips" action={<span className="link-teal">See All</span>}>
            <ul className="tips-list">
              <li style={{ padding: "10px 0" }}>
                <span className="insight-ico" style={{ background: "#E7F1FB" }}><Icon name="bars" size={18} /></span>
                <div><h4>Focus on Key KPIs</h4><p>Include 3–5 core metrics to keep your report clear and impactful.</p></div>
              </li>
              <li style={{ padding: "10px 0" }}>
                <span className="insight-ico" style={{ background: "#E5F5EC" }}><Icon name="users" size={18} /></span>
                <div><h4>Use Benchmarks for Context</h4><p>Compare against workspace benchmarks to highlight performance.</p></div>
              </li>
              <li style={{ padding: "10px 0" }}>
                <span className="insight-ico" style={{ background: "#E7F1FB" }}><Icon name="report" size={18} /></span>
                <div><h4>Choose the Right Format</h4><p>Use a deck for presentations, XLSX for deep analysis, or a one-pager for quick sharing.</p></div>
              </li>
              <li style={{ padding: "10px 0" }}>
                <span className="insight-ico" style={{ background: "#E5F5EC" }}><Icon name="target" size={18} /></span>
                <div><h4>Tailor to Your Audience</h4><p>Customize your report based on stakeholders – from creative teams to executive leadership.</p></div>
              </li>
            </ul>
          </Panel>
          <Panel title="Latest Generated Files" action={<span className="link-teal">See All</span>}>
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
              <EmptyState text="No generated files yet." />
            )}
            <button type="button" className="btn-outline" style={{ width: "100%", marginTop: 8 }}>
              View All Generated Reports <Icon name="chev" size={14} />
            </button>
          </Panel>
        </div>
      </div>
    </>
  );
}
