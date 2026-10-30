import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { SyncJobs } from "@/components/SyncJobs";
import { KpiTrend } from "@/components/KpiTrend";
import type { KpiComparison, KpiPeriod } from "@/components/KpiTrend";
import { pooledBenchmark, type BenchmarkMetadata } from "@/components/benchmarkPooling";
import { formatNativeMoney, sharedSourceCurrency } from "@/components/sourceCurrency";
import { useLocale } from "@/i18n";

interface CampaignAggregate extends BenchmarkMetadata {
  spend?: number | null;
  impressions?: number | null;
  clicks?: number | null;
  conversions?: number | null;
  video_views?: number | null;
  revenue?: number | null;
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

function sumReported(
  groups: CampaignAggregate[],
  key: "spend" | "impressions" | "clicks" | "conversions" | "video_views" | "revenue",
): number | null {
  let total = 0;
  let any = false;
  for (const group of groups) {
    const value = group[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      total += value;
      any = true;
    }
  }
  return any ? total : null;
}

/** Dataset summary over GET /api/campaigns. Ratios use reporting components. */
function buildKpiCards(campaigns: CampaignsResponse, locale = "en-US"): KpiCard[] {
  const groups = Object.values(campaigns);
  const spend = sumReported(groups, "spend");
  const impr = sumReported(groups, "impressions");
  const views = sumReported(groups, "video_views");
  const code = sharedSourceCurrency(groups);
  const money = (value: number | null) => formatNativeMoney(value, code, locale, "—", { digits: 2 });
  const cpm = pooledBenchmark(groups, "cpm");
  const ctr = pooledBenchmark(groups, "ctr");
  const cpa = pooledBenchmark(groups, "cpa");
  const roas = pooledBenchmark(groups, "roas");
  const cpas = groups.map((g) => g.cpa).filter((v): v is number => typeof v === "number" && v > 0);
  const best = cpas.length && code ? Math.min(...cpas) : null;
  const scope = `Across ${groups.length} Campaign${groups.length === 1 ? "" : "s"}`;
  const roasShare = roas.coverage?.kind === "spend" ? roas.coverage.share : null;
  const play = impr != null && impr > 0 && views != null ? views / impr : null;
  return [
    { value: money(spend), label: "Spend", context: spend == null ? "No Spend Reported" : scope, metricId: "spend" },
    { value: impr ? impr.toLocaleString(locale) : "—", label: "Impressions", context: impr ? scope : "No Impressions Yet", metricId: "impressions" },
    { value: cpm.value == null ? "—" : money(cpm.value), label: "CPM", context: cpm.value == null ? "No Impressions Yet" : scope, metricId: "cpm" },
    {
      value: play == null ? "—" : ((play * 100).toFixed(1) + "%"),
      label: "Play Rate",
      context: impr ? (views ? scope : "No Video Views Yet") : "No Impressions Yet",
      metricId: "view_rate",
    },
    {
      value: ctr.value == null ? "—" : ((ctr.value * 100).toFixed(2) + "%"),
      label: "CTR",
      context: ctr.value == null ? "No Impressions Yet" : scope,
      metricId: "ctr",
    },
    {
      value: cpa.value == null ? "—" : money(cpa.value),
      label: "CPA",
      context: cpa.value == null ? "No Conversions Yet" : "Blended " + scope,
      metricId: "cpa",
    },
    {
      value: roas.value == null ? "—" : roas.value.toFixed(2) + "x",
      label: "ROAS",
      context: roas.value == null
        ? "No Revenue Yet"
        : (roasShare != null && roasShare < 1
          ? `Revenue-reporting spend coverage ${Math.round(roasShare * 100)}%`
          : "Blended " + scope),
      metricId: "roas",
    },
    {
      value: best != null ? money(best) : "—",
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
  const { locale } = useLocale();
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
        {buildKpiCards(campaigns, locale).map((c) => {
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
