import { useEffect, useRef, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";

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

/** Legacy defaults: every KPI checked except roas. */
const DEFAULT_KPIS = KPI_OPTIONS.filter((k) => k !== "roas");

const BENCH_OPTIONS = ["hook_type", "creator_vs_branded", "edit_style", "platform", "campaign"];
const RANK_OPTIONS = ["cpa", "cpm", "ctr", "vtr", "roas"];

/** UI copy rule: Title Case labels, true acronyms (CPA/CTR/…) stay caps. */
const KPI_LABELS: Record<string, string> = {
  vtr: "VTR (Completed)",
  view_rate: "Play Rate",
  spend: "Spend",
  impressions: "Impressions",
  clicks: "Clicks",
  conversions: "Conversions",
  video_views: "Video Views",
  hook_type: "Hook Type",
  creator_vs_branded: "Creator Vs Branded",
  edit_style: "Edit Style",
  platform: "Platform",
  campaign: "Campaign",
};
const kpiLabel = (k: string): string => KPI_LABELS[k] ?? k.toUpperCase();

type ReportFormat = "one-pager" | "csv" | "pptx" | "xlsx" | "deck";

interface CreativeRow {
  creative_key: string;
  name?: string;
  campaigns?: string[];
}

interface DeckSlot {
  creative_key: string;
  [metric: string]: unknown;
}

interface Deck {
  title?: string;
  rank_by?: string;
  slides?: { campaign: string; kpis?: Record<string, unknown> }[];
  why?: string[];
  learnings?: string[];
  recommendations?: string[];
  creatives?: Record<string, { best?: DeckSlot | null; worst?: DeckSlot | null }>;
}

interface ReportResponse {
  format?: string;
  markdown?: string;
  csv?: string;
  filename?: string;
  pptx_b64?: string;
  xlsx_b64?: string;
  deck?: Deck;
}

interface DownloadLink {
  filename: string;
  href: string;
}

function esc(v: unknown): string {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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

function textDownload(filename: string, mime: string, text: string): DownloadLink {
  return { filename, href: URL.createObjectURL(new Blob([text], { type: mime })) };
}

/** Legacy download_b64(): base64 payload bytes behind a download link. */
function b64Download(filename: string, mime: string, b64: string): DownloadLink {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return { filename, href: URL.createObjectURL(new Blob([arr], { type: mime })) };
}

/** Legacy report_deck(): client-side HTML deck built from the deck JSON. */
function deckHtml(d: Deck): string {
  const rk = d.rank_by || "cpa";
  const sym = ["spend", "cpa", "cpc", "cpm"].includes(rk) ? "$" : "";
  const fmtv = (v: unknown) => (v == null ? "N/A" : sym + String(v));
  const slides = (d.slides || [])
    .map((s) => {
      const cw = (d.creatives || {})[s.campaign] || {};
      const best = cw.best
        ? `<p>Best: ${esc(cw.best.creative_key)} (${esc(rk.toUpperCase())} ${esc(fmtv(cw.best[rk]))})</p>`
        : "";
      const worst = cw.worst
        ? `<p>Watch: ${esc(cw.worst.creative_key)} (${esc(rk.toUpperCase())} ${esc(fmtv(cw.worst[rk]))})</p>`
        : "";
      return `<section class="slide"><h2>${esc(s.campaign)}</h2><p>${esc(Object.entries(s.kpis || {}).map(([k, v]) => k + ": " + (v == null ? "N/A" : v)).join(" · "))}</p>${best}${worst}</section>`;
    })
    .join("");
  const why = (d.why || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const learn = (d.learnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const reco = (d.recommendations || []).map((w) => `<li>${esc(w)}</li>`).join("");
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>${esc(d.title || "Client Deck")}</title><style>body{font-family:system-ui,sans-serif;color:#1a1a1a;margin:0}.slide{padding:48px;page-break-after:always;border-bottom:2px solid #e2e2e0}</style></head><body><h1 style="padding:48px 48px 0">${esc(d.title || "Client Deck")}</h1>${slides}<section class="slide"><h2>Why It Won</h2><ul>${why}</ul></section><section class="slide"><h2>Creative Learnings</h2><ul>${learn}</ul></section><section class="slide"><h2>Recommendations / Next Steps</h2><ul>${reco}</ul></section></body></html>`;
}

/** Reports (legacy v-report): campaign/KPI/benchmark selection with
 *  one-pager, CSV, .pptx, .xlsx and HTML-deck outputs (POST /api/report),
 *  plus the gated creative one-pager (POST /api/export). */
export function ReportsPage() {
  const { scope, filters } = useFilters();

  const [campaigns, setCampaigns] = useState<string[] | null>(null);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [checkedCampaigns, setCheckedCampaigns] = useState<string[]>([]);
  const [creatives, setCreatives] = useState<CreativeRow[] | null>(null);
  const [creativeError, setCreativeError] = useState<string | null>(null);
  const [checkedCreatives, setCheckedCreatives] = useState<string[]>([]);
  const [kpis, setKpis] = useState<string[]>(DEFAULT_KPIS);
  const [benchmark, setBenchmark] = useState("hook_type");
  const [benchmarkScope, setBenchmarkScope] = useState("filters");
  const [rankBy, setRankBy] = useState("cpa");
  const [override, setOverride] = useState(false);
  const [strictHuman, setStrictHuman] = useState(false);
  const [status, setStatus] = useState("");
  const [links, setLinks] = useState<DownloadLink[]>([]);

  const linksRef = useRef<DownloadLink[]>([]);
  linksRef.current = links;
  useEffect(() => {
    const previous = linksRef.current;
    return () => {
      for (const l of previous) URL.revokeObjectURL(l.href);
    };
  }, [links]);
  useEffect(() => {
    return () => {
      for (const l of linksRef.current) URL.revokeObjectURL(l.href);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setCampaigns(null);
    setCampaignError(null);
    api<Record<string, unknown>>("GET", scopedPath("/api/campaigns", scope))
      .then((c) => {
        if (cancelled) return;
        const needle = filters.campaign.trim().toLowerCase();
        const keys = Object.keys(c).filter((k) => !needle || k.toLowerCase().includes(needle));
        setCampaigns(keys);
        setCheckedCampaigns(keys);
      })
      .catch((err) => {
        if (!cancelled) setCampaignError(errMessage(err, "Failed To Load Campaigns."));
      });
    return () => {
      cancelled = true;
    };
  }, [scope, filters.campaign]);

  useEffect(() => {
    let cancelled = false;
    setCreatives(null);
    setCreativeError(null);
    api<CreativeRow[]>("GET", scopedPath("/api/creatives", scope))
      .then((rows) => {
        if (cancelled) return;
        const needle = filters.campaign.trim().toLowerCase();
        setCreatives(
          rows.filter((r) => {
            if (!needle) return true;
            return [r.creative_key, r.name, (r.campaigns || []).join(" ")]
              .join(" | ")
              .toLowerCase()
              .includes(needle);
          }),
        );
      })
      .catch((err) => {
        if (!cancelled) setCreativeError(errMessage(err, "Failed To Load Creatives."));
      });
    return () => {
      cancelled = true;
    };
  }, [scope, filters.campaign]);

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  /** Legacy report_body(): unchecked-everything campaigns send null,
   *  unchecked-everything KPIs fall back to cpa + ctr. */
  function reportBody() {
    return {
      campaigns: checkedCampaigns.length ? checkedCampaigns : null,
      kpis: kpis.length ? kpis : ["cpa", "ctr"],
      benchmark,
      benchmark_scope: benchmarkScope,
      rank_by: rankBy,
      override,
      strict_human: strictHuman,
      filters: scopeFilterBody(scope),
    };
  }

  function blocked(err: unknown) {
    setStatus("BLOCKED: " + errMessage(err, "Report Blocked."));
    setLinks([]);
  }

  async function runReport(format: ReportFormat) {
    try {
      const r = await api<ReportResponse>("POST", "/api/report", { ...reportBody(), format });
      if (format === "one-pager") {
        setStatus(r.markdown ?? "");
        setLinks([textDownload("one-pager.md", "text/markdown", r.markdown ?? "")]);
      } else if (format === "csv") {
        setStatus(r.csv ?? "");
        setLinks([textDownload("report.csv", "text/csv", r.csv ?? "")]);
      } else if (format === "pptx") {
        setStatus("PowerPoint Built: " + r.filename + ".");
        setLinks([
          b64Download(
            r.filename ?? "campaign-report.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            r.pptx_b64 ?? "",
          ),
        ]);
      } else if (format === "xlsx") {
        setStatus("Excel Workbook Built: " + r.filename + ".");
        setLinks([
          b64Download(
            r.filename ?? "campaign-report.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            r.xlsx_b64 ?? "",
          ),
        ]);
      } else {
        const deck = r.deck ?? {};
        setStatus("Deck Built: " + (deck.slides || []).length + " Campaign Slides + Why-Analysis.");
        setLinks([textDownload("deck.html", "text/html", deckHtml(deck))]);
      }
    } catch (err) {
      blocked(err);
    }
  }

  /** Gated one-pager over the selected creatives (legacy /api/export). */
  async function runExport() {
    try {
      const r = await api<{ markdown: string }>("POST", "/api/export", {
        creative_keys: checkedCreatives,
        override,
      });
      setStatus(r.markdown);
      setLinks([textDownload("one-pager.md", "text/markdown", r.markdown)]);
    } catch (err) {
      blocked(err);
    }
  }

  return (
    <>
      <h1 className="page-title">Reports</h1>
      <p className="page-sub">
        Select Campaigns, KPIs And A Benchmark, Then Generate. One-Pager, CSV, True PowerPoint
        (.Pptx), True Excel (.Xlsx) And Presentation (HTML Deck) Formats.
      </p>
      <div className="card">
        <h3>Campaigns</h3>
        {campaigns === null && campaignError === null ? (
          <p className="muted">Loading…</p>
        ) : campaignError !== null ? (
          <p className="muted">{campaignError}</p>
        ) : campaigns !== null && campaigns.length > 0 ? (
          campaigns.map((k) => (
            <div key={k}>
              <label>
                <input
                  type="checkbox"
                  checked={checkedCampaigns.includes(k)}
                  onChange={() => setCheckedCampaigns((prev) => toggle(prev, k))}
                />{" "}
                {k}
              </label>
            </div>
          ))
        ) : (
          <span className="muted">No Campaigns.</span>
        )}
      </div>
      <div className="card">
        <h3>Creatives (One-Pager Source)</h3>
        {creatives === null && creativeError === null ? (
          <p className="muted">Loading…</p>
        ) : creativeError !== null ? (
          <p className="muted">{creativeError}</p>
        ) : creatives !== null && creatives.length > 0 ? (
          creatives.map((r) => (
            <div key={r.creative_key}>
              <label>
                <input
                  type="checkbox"
                  checked={checkedCreatives.includes(r.creative_key)}
                  onChange={() => setCheckedCreatives((prev) => toggle(prev, r.creative_key))}
                />{" "}
                {r.name || r.creative_key}
              </label>
            </div>
          ))
        ) : (
          <span className="muted">No Creatives.</span>
        )}
        <div style={{ marginTop: 8 }}>
          <button type="button" className="action" onClick={() => void runExport()}>
            Export One-Pager
          </button>
        </div>
      </div>
      <div className="card">
        <h3>KPIs</h3>
        {KPI_OPTIONS.map((k) => (
          <label key={k} style={{ marginRight: 12 }}>
            <input
              type="checkbox"
              checked={kpis.includes(k)}
              onChange={() => setKpis((prev) => toggle(prev, k))}
            />{" "}
            {kpiLabel(k)}
          </label>
        ))}
      </div>
      <div className="card">
        <h3>Benchmark</h3>
        <label>
          Group By{" "}
          <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
            {BENCH_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {kpiLabel(o)}
              </option>
            ))}
          </select>
        </label>{" "}
        <label>
          Benchmark Scope{" "}
          <select value={benchmarkScope} onChange={(e) => setBenchmarkScope(e.target.value)}>
            <option value="filters">Current Filters</option>
            <option value="global">Global</option>
          </select>
        </label>{" "}
        <label>
          Rank Best/Watch By{" "}
          <select value={rankBy} onChange={(e) => setRankBy(e.target.value)}>
            {RANK_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {kpiLabel(o)}
              </option>
            ))}
          </select>
        </label>{" "}
        <label>
          <input
            type="checkbox"
            checked={override}
            onChange={(e) => setOverride(e.target.checked)}
          />{" "}
          Override (Logged)
        </label>{" "}
        <label>
          <input
            type="checkbox"
            checked={strictHuman}
            onChange={(e) => setStrictHuman(e.target.checked)}
          />{" "}
          HUMAN-VERIFIED Insights Only
        </label>
        <br />
        <br />
        <button type="button" className="action" onClick={() => void runReport("one-pager")}>
          Generate One-Pager
        </button>
        <button type="button" className="action" onClick={() => void runReport("csv")}>
          Generate CSV
        </button>
        <button type="button" className="action" onClick={() => void runReport("pptx")}>
          Generate PowerPoint (.pptx)
        </button>
        <button type="button" className="action" onClick={() => void runReport("xlsx")}>
          Generate Excel (.xlsx)
        </button>
        <button type="button" className="action" onClick={() => void runReport("deck")}>
          Generate Presentation (HTML Deck)
        </button>
        <pre className="muted">{status}</pre>
        <span className="report-outputs">
          {links.map((l) => (
            <a key={l.filename} download={l.filename} href={l.href}>
              Download {l.filename}
            </a>
          ))}
        </span>
      </div>
    </>
  );
}
