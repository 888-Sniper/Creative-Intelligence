import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { SyncJobs } from "@/components/SyncJobs";
import { KpiTrend } from "@/components/KpiTrend";
import type { KpiComparison, KpiPeriod } from "@/components/KpiTrend";

interface CampaignAggregate {
  n_ads?: number;
  spend?: number;
  impressions?: number;
  clicks?: number;
  conversions?: number;
  video_views?: number;
  revenue?: number;
  cpa?: number | null;
}

type CampaignsResponse = Record<string, CampaignAggregate>;

interface IngestResponse {
  inserted: number;
  updated?: number;
  quarantined_count?: number;
}

interface SyncRunResponse {
  inserted: number;
  updated: number;
  quarantined_count: number;
}

interface SyncSourceStatus {
  last_finished_at?: string;
  last_run_at?: string;
  last_status?: string;
  last_inserted?: number;
  last_updated?: number;
  last_error?: string;
}

interface SyncStatusResponse {
  sources?: Record<string, SyncSourceStatus>;
  jobs?: string[];
}

interface ProviderStatusResponse {
  mode?: string;
  capabilities?: Record<string, { status?: string }>;
}

interface KpiCard {
  value: string;
  label: string;
  /** Supporting scope text ("Across 3 Campaigns") — never a comparison. */
  context: string;
  /** Backend comparison metric id, or null when no trend applies. */
  metricId: string | null;
}

interface CompareMetric extends KpiComparison {
  current: number | null;
  previous: number | null;
  abs_change: number | null;
}

interface CompareResponse {
  current_period: KpiPeriod | null;
  previous_period: KpiPeriod | null;
  comparison: string | null;
  metrics: Record<string, CompareMetric>;
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Dataset summary over GET /api/campaigns, mirroring the legacy kpis(). */
function buildKpiCards(campaigns: CampaignsResponse): KpiCard[] {
  const groups = Object.values(campaigns);
  const tot = (k: "spend" | "impressions" | "clicks" | "conversions" | "video_views" | "revenue") =>
    groups.reduce((t, g) => t + (Number(g[k]) || 0), 0);
  const spend = tot("spend");
  const impr = tot("impressions");
  const clicks = tot("clicks");
  const conv = tot("conversions");
  const views = tot("video_views");
  const rev = tot("revenue");
  const cpm = impr ? (spend / impr) * 1000 : 0;
  const vtr = impr ? views / impr : 0;
  const ctr = impr ? clicks / impr : 0;
  const cpa = conv ? spend / conv : 0;
  const roas = spend ? rev / spend : 0;
  const cpas = groups.map((g) => g.cpa).filter((v): v is number => typeof v === "number" && v > 0);
  const best = cpas.length ? Math.min(...cpas) : null;
  const scope = `Across ${groups.length} Campaign${groups.length === 1 ? "" : "s"}`;
  return [
    { value: "$" + spend.toFixed(2), label: "Spend", context: scope, metricId: "spend" },
    { value: impr ? impr.toLocaleString("en-US") : "—", label: "Impressions", context: impr ? scope : "No Impressions Yet", metricId: "impressions" },
    { value: impr ? "$" + cpm.toFixed(2) : "—", label: "CPM", context: impr ? scope : "No Impressions Yet", metricId: "cpm" },
    {
      value: impr ? ((vtr * 100).toFixed(1) + "%") : "—",
      label: "Play Rate",
      context: impr ? (views ? scope : "No Video Views Yet") : "No Impressions Yet",
      metricId: "view_rate",
    },
    { value: impr ? ((ctr * 100).toFixed(2) + "%") : "—", label: "CTR", context: impr ? scope : "No Impressions Yet", metricId: "ctr" },
    { value: conv ? "$" + cpa.toFixed(2) : "—", label: "CPA", context: conv ? "Blended " + scope : "No Conversions Yet", metricId: "cpa" },
    {
      value: spend && rev ? roas.toFixed(2) + "x" : "—",
      label: "ROAS",
      context: spend && rev ? "Blended " + scope : "No Revenue Yet",
      metricId: "roas",
    },
    {
      value: best != null ? "$" + best.toFixed(2) : "—",
      label: "Best CPA",
      context: best != null ? "Lowest Single Campaign" : "No Conversions Yet",
      metricId: null,
    },
  ];
}

const SYNC_NAMES: Record<string, string> = {
  meta: "Meta",
  tiktok: "TikTok",
  sheets: "Sheets",
  drive: "Drive",
};

/** Sync ledger text, mirroring the legacy sync_status(). */
function buildSyncText(s: SyncStatusResponse): string {
  const rows = Object.keys(SYNC_NAMES).map((k) => {
    const v = (s.sources || {})[k];
    if (!v) return SYNC_NAMES[k] + ": Never Synced";
    const when = v.last_finished_at || v.last_run_at || "?";
    if (v.last_status === "ok") {
      return `${SYNC_NAMES[k]}: OK @ ${when} (${v.last_inserted} New, ${v.last_updated} Updated)`;
    }
    return `${SYNC_NAMES[k]}: ${v.last_status} @ ${when}${v.last_error ? ": " + v.last_error : ""}`;
  });
  const jobs = (s.jobs || []).map((j) => SYNC_NAMES[j] || j);
  return (
    rows.join("\n") +
    (jobs.length ? "\nScheduled Jobs: " + jobs.join(", ") + "." : "\nNo Scheduled Jobs Yet — Run An Import Above First.")
  );
}

function readFileB64(file: File): Promise<string> {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(",", 2)[1] || "");
    fr.onerror = () => rej(new Error("Could Not Read File"));
    fr.readAsDataURL(file);
  });
}

/** Overview dashboard: dataset summary KPI cards, CSV/XLSX ingest upload,
 *  scheduled-sync status + run, and provider health (legacy v-main parity). */
export function OverviewPage() {
  const { scope } = useFilters();
  const [campaigns, setCampaigns] = useState<CampaignsResponse | null>(null);
  const [kpiError, setKpiError] = useState("");
  const [platform, setPlatform] = useState("meta");
  const [csv, setCsv] = useState("");
  const [upStatus, setUpStatus] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [syncOut, setSyncOut] = useState("");
  const [provStatus, setProvStatus] = useState("");
  const [compare, setCompare] = useState<CompareResponse | null>(null);

  const loadKpis = useCallback(async () => {
    try {
      const c = await api<CampaignsResponse>("GET", scopedPath("/api/campaigns", scope));
      setCampaigns(c);
      setKpiError("");
    } catch (e) {
      setKpiError(errorMessage(e));
    }
  }, [scope]);

  const loadCompare = useCallback(async () => {
    try {
      const r = await api<CompareResponse>("GET", scopedPath("/api/kpis/compare", scope));
      setCompare(r);
    } catch {
      // Comparisons are enhancement-only: a failed compare fetch
      // must never break the KPI cards themselves.
      setCompare(null);
    }
  }, [scope]);

  const loadSync = useCallback(async () => {
    try {
      const s = await api<SyncStatusResponse>("GET", "/api/sync/status");
      setSyncOut(buildSyncText(s));
    } catch {
      setSyncMsg("Sync Status Unavailable.");
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const h = await api<ProviderStatusResponse>("GET", "/api/providers/status");
      const caps = h.capabilities || {};
      const missing = Object.entries(caps)
        .filter(([, v]) => v?.status !== "configured")
        .map(([k]) => k);
      setProvStatus(
        h.mode === "live"
          ? "Providers: Live Mode." +
              (missing.length ? " Missing: " + missing.join(", ") + "." : " All Capability Groups Configured.")
          : "Providers: Mock Mode — Set CREATIVE_INTEL_PROVIDER_MODE=live And Add Provider Keys For Live Transcription, Vision And Structuring.",
      );
    } catch {
      setProvStatus("Provider Status Unavailable.");
    }
  }, []);

  const refreshViews = useCallback(() => {
    void loadKpis();
    void loadCompare();
    void loadSync();
    void loadHealth();
  }, [loadKpis, loadCompare, loadSync, loadHealth]);

  useEffect(() => {
    refreshViews();
  }, [refreshViews]);

  const uploadCsv = async () => {
    try {
      const r = await api<IngestResponse>("POST", "/api/ingest", { platform, csv });
      setUpStatus(
        "Inserted " + r.inserted + " Rows, " + r.updated + " Updated (" + r.quarantined_count + " Quarantined).",
      );
      refreshViews();
    } catch (e) {
      setUpStatus(errorMessage(e));
    }
  };

  const uploadXlsx = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) {
      setUpStatus("Choose An .Xlsx File First.");
      return;
    }
    try {
      const b64 = await readFileB64(f);
      const r = await api<IngestResponse>("POST", "/api/ingest", { platform, xlsx_b64: b64, source: "upload" });
      setUpStatus("Inserted " + r.inserted + " Rows (" + r.quarantined_count + " Quarantined).");
      refreshViews();
    } catch (err) {
      setUpStatus(errorMessage(err));
    }
  };

  const loadFixtureHint = () => {
    setUpStatus("Run: python3 Backend/ci_backend/main.py --load-fixture --db Data/local.db");
  };

  const syncNow = async (source: string) => {
    try {
      const r = await api<SyncRunResponse>("POST", "/api/sync/run", { source });
      const display = SYNC_NAMES[source] ?? source;
      setSyncMsg(
        "Synced " + display + ": " + r.inserted + " New, " + r.updated + " Updated (" + r.quarantined_count + " Quarantined).",
      );
      refreshViews();
    } catch (e) {
      setSyncMsg(errorMessage(e));
    }
  };

  let kpiContent: ReactNode;
  if (kpiError) {
    kpiContent = <div className="empty-state">{kpiError}</div>;
  } else if (!campaigns) {
    kpiContent = <>—</>;
  } else if (!Object.values(campaigns).length) {
    kpiContent = <div className="empty-state">Upload Performance Data To Begin.</div>;
  } else {
    kpiContent = (
      <div className="kpi-grid">
        {buildKpiCards(campaigns).map((c) => {
          const comp = c.metricId ? compare?.metrics[c.metricId] ?? null : null;
          return (
            <div className="kpi-card" key={c.label}>
              <div className="kpi-value">{c.value}</div>
              <div className="kpi-label">{c.label}</div>
              {c.context ? <div className="kpi-context">{c.context}</div> : null}
              {comp && compare?.previous_period ? (
                <KpiTrend metricLabel={c.label} comparison={comp} previous={compare.previous_period} />
              ) : null}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <>
      <h1 className="page-title">Overview</h1>
      <p className="page-sub">Your creative performance at a glance.</p>
      <div className="card">
        <h3>Upload (Meta / TikTok CSV, Excel .xlsx, Sheets Link)</h3>
        <select value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="Platform">
          <option value="meta">Meta</option>
          <option value="tiktok">TikTok</option>
        </select>
        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          placeholder="Paste CSV export text here"
          aria-label="CSV Export Text"
        />
        <br />
        <br />
        <button type="button" className="action" onClick={() => void uploadCsv()}>
          Upload CSV
        </button>
        <label className="secondary" style={{ display: "inline-block", cursor: "pointer" }}>
          Upload .xlsx
          <input
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            hidden
            aria-label="Upload .xlsx file"
            onChange={(e) => void uploadXlsx(e)}
          />
        </label>
        <button type="button" className="action" onClick={loadFixtureHint}>
          Load Fixture (main.py --load-fixture)
        </button>
        <span className="muted">{upStatus}</span>
        <div style={{ marginTop: 12 }}>
          <h4>Scheduled Sync</h4>
          <div className="muted" style={{ fontSize: 12 }}>
            Successful Imports Are Remembered As Sync Jobs: Re-Imports Update Matching Rows Instead Of Duplicating Them,
            And The Server Re-Runs Them On A Timer When Started With --sync-every SECONDS.
          </div>
          <div style={{ marginTop: 8 }}>
            <button type="button" className="action" onClick={() => void syncNow("meta")}>
              Sync Meta Now
            </button>
            <button type="button" className="action" onClick={() => void syncNow("tiktok")}>
              Sync TikTok Now
            </button>
            <span className="muted">{syncMsg}</span>
          </div>
          <div className="muted" style={{ fontSize: 12, whiteSpace: "pre-line" }}>
            {syncOut}
          </div>
        </div>
        <SyncJobs />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          {provStatus}
        </div>
      </div>
      <div className="card">
        <h3>KPIs</h3>
        <div>{kpiContent}</div>
      </div>
    </>
  );
}
