import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  CreativeThumb,
  EmptyState,
  MetaSelect,
  Panel,
  Skeleton,
  compareDisplayed,
  fmtCell,
  fmtCompact,
  fmtMult,
  fmtPct,
  kpiDisplay,
  platformLabel,
  useCampaignMeta,
  useScopedApi,
} from "@/components/product";

interface AnalystTable {
  title?: string | null;
  columns: string[];
  rows: (string | number | null)[][];
}

interface AnalystFinding {
  finding_id: string;
  status?: string;
  primary_signal?: string | null;
  diagnosis?: string | null;
  creative_hypothesis?: string | null;
  recommended_iteration?: string | null;
  priority?: string | null;
  confidence_level?: string | null;
  element_to_preserve?: string | null;
  element_to_change?: string | null;
  creative_ids?: string[];
}

interface AnalystAnswer {
  text: string;
  language?: string;
  tables?: AnalystTable[];
  findings_stored?: AnalystFinding[];
  follow_ups?: string[];
  warnings?: string[];
}

interface AskResponse {
  conversation_id: string;
  answer: AnalystAnswer;
  scope_snapshot?: Record<string, unknown>;
  dataset_version?: string | null;
}

interface ConversationSummary {
  id: string;
  title?: string | null;
  objective?: string | null;
  updated_at?: string | null;
  message_count?: number;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  answer?: AnalystAnswer | null;
}

interface BenchGroup {
  spend: number;
  impressions: number;
  clicks: number;
  conversions: number;
  revenue: number;
  ctr: number | null;
  cpc: number | null;
  cpa: number | null;
  roas: number | null;
}

interface CreativeMetrics {
  spend?: number | null;
  impressions?: number | null;
  clicks?: number | null;
  conversions?: number | null;
  video_views?: number | null;
  revenue?: number | null;
  ctr?: number | null;
  cpc?: number | null;
  cpa?: number | null;
  roas?: number | null;
}

interface CreativeAnn {
  hook_type?: string | null;
  duration_s?: number | null;
  brand_seconds?: Array<{ start_s?: number | null }> | null;
}

interface CreativeRow {
  creative_key: string;
  name?: string | null;
  platform?: string | null;
  format?: string | null;
  duration_s?: number | null;
  campaigns?: string[];
  metrics?: CreativeMetrics | null;
  annotation?: CreativeAnn | null;
}

const OBJECTIVES = ["reach", "video_views", "traffic", "conversions", ""] as const;

const TRY_KEYS = ["t0", "t1", "t2", "t3"] as const;

const DATE_RANGES = [
  { value: "all", key: "all" },
  { value: "7", key: "d7" },
  { value: "30", key: "d30" },
  { value: "90", key: "d90" },
] as const;

type TFn = (key: string, vars?: Record<string, string | number>) => string;

/** Backend hook codes render through the UI locale; unknown codes
 *  keep the honest Title Case form. */
function hookName(t: TFn, key: string): string {
  const hit = t(`filters.hooks.${key}`);
  return hit === `filters.hooks.${key}` ? titleCase(key) : hit;
}

/** Filter-bar scope as a body dict (multi-values become arrays).
 *  The analyst POST routes read scope from the JSON body, not the
 *  query string, so this must travel in the body or filters silently
 *  analyse the whole dataset. */
export function scopeBody(scope: URLSearchParams): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const key of new Set(scope.keys())) {
    const vals = scope.getAll(key);
    if (vals.length > 0) out[key] = vals;
  }
  return out;
}

async function downloadReportBlob(body: unknown): Promise<Blob> {
  const res = await fetch("/api/analyst/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as {
      detail?: { error?: string };
    } | null;
    throw new Error(detail?.detail?.error ?? `Report export failed (${res.status})`);
  }
  return res.blob();
}

function fmtScope(scope?: Record<string, unknown>): string {
  if (!scope) return "";
  const parts: string[] = [];
  for (const key of ["campaign", "platform", "market", "date_from", "date_to", "objective"]) {
    const value = scope[key];
    if (value !== undefined && value !== null && value !== "") parts.push(`${key}: ${String(value)}`);
  }
  return parts.join(" · ");
}

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function brandStart(ann?: CreativeAnn | null): number | null {
  const spans = ann?.brand_seconds;
  if (!Array.isArray(spans)) return null;
  let best: number | null = null;
  for (const s of spans) {
    const t = s?.start_s;
    if (typeof t === "number" && Number.isFinite(t) && (best == null || t < best)) best = t;
  }
  return best;
}

function stampNow(fmtDate: (iso: string, opts?: Intl.DateTimeFormatOptions) => string): string {
  return fmtDate(new Date().toISOString(), {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

/** Accessible horizontal bars (value labels, no chart lib needed for
 *  single-series breakdowns). */
function LabeledBars({ rows, format, color = "#0A9183" }: {
  rows: Array<{ label: string; value: number }>;
  format: (v: number) => string;
  color?: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {rows.map((r) => (
        <div key={r.label}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, marginBottom: 5 }}>
            <span style={{ color: "var(--shell-navy)", fontWeight: 600 }}>{r.label}</span>
            <span style={{ color: "var(--shell-navy)", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
              {format(r.value)}
            </span>
          </div>
          <div
            role="img"
            aria-label={`${r.label}: ${format(r.value)}`}
            style={{ height: 9, borderRadius: 5, background: "var(--shell-line)" }}
          >
            <div style={{
              width: `${Math.max(3, (r.value / max) * 100)}%`, height: "100%",
              borderRadius: 5, background: color,
            }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Compact bars (CTR) + line (ROAS) combo for video-length bands. */
function LengthCombo({ rows }: {
  rows: Array<{ label: string; ctr: number; roas: number | null }>;
}) {
  const { t, fmtNum, locale } = useLocale();
  const dec1 = (v: number): string =>
    fmtNum(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const w = 560;
  const h = 190;
  const padL = 44;
  const padB = 30;
  const padT = 14;
  const maxCtr = Math.max(1, ...rows.map((r) => r.ctr));
  const maxRoas = Math.max(1, ...rows.map((r) => r.roas ?? 0));
  const iw = w - padL - 12;
  const ih = h - padT - padB;
  const slot = iw / Math.max(1, rows.length);
  const pts = rows.map((r, i) => {
    const x = padL + slot * i + slot / 2;
    const y = padT + ih - ((r.roas ?? 0) / maxRoas) * ih;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} role="img"
        aria-label={rows.map((r) => t("analyst.comboAria", { label: r.label, ctr: dec1(r.ctr) })).join("; ")}
        style={{ width: "100%", height: "auto", display: "block" }}>
        {[0, 0.5, 1].map((t) => {
          const y = padT + ih * (1 - t);
          return (
            <g key={t}>
              <line x1={padL} x2={w - 6} y1={y} y2={y} stroke="var(--shell-line)" strokeWidth="1" />
              <text x={padL - 7} y={y + 4} textAnchor="end" fontSize="11" fill="var(--shell-faint)">
                {fmtPct(maxCtr * t, 1, locale)}
              </text>
            </g>
          );
        })}
        {rows.map((r, i) => {
          const bw = Math.min(64, slot * 0.44);
          const x = padL + slot * i + (slot - bw) / 2;
          const bh = Math.max(3, (r.ctr / maxCtr) * ih);
          const y = padT + ih - bh;
          return (
            <g key={r.label}>
              <rect x={x} y={y} width={bw} height={bh} rx="5" fill="#0A9183" />
              <text x={x + bw / 2} y={y - 6} textAnchor="middle" fontSize="12"
                fontWeight="700" fill="var(--shell-navy)">
                {fmtPct(r.ctr, 1, locale)}
              </text>
              <text x={padL + slot * i + slot / 2} y={h - 8} textAnchor="middle"
                fontSize="12" fill="var(--shell-muted)">
                {r.label}
              </text>
            </g>
          );
        })}
        {rows.some((r) => r.roas != null) && pts.length > 1 ? (
          <>
            <polyline points={pts.join(" ")} fill="none" stroke="#E8833A"
              strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            {rows.map((r, i) => {
              const [x, y] = pts[i].split(",").map(Number);
              return r.roas == null ? null : (
                <circle key={r.label} cx={x} cy={y} r="4.5" fill="#E8833A"
                  stroke="var(--shell-card)" strokeWidth="2" />
              );
            })}
          </>
        ) : null}
      </svg>
      <div className="legend" aria-hidden="true">
        <span><i style={{ background: "#0A9183" }} />{t("filters.kpis.ctr")}</span>
        <span><i style={{ background: "#E8833A" }} />{t("filters.kpis.roas")}</span>
      </div>
    </div>
  );
}

export function AnalystPage({ accountKey = "" }: { accountKey?: string }) {
  const { filters, setFilter, clearFilters, applyPresetDays, scope } = useFilters();
  const { t, tp, fmtDate, fmtNum, locale: uiLocale } = useLocale();
  const unavailable = t("common.unavailable");
  // Bare decimals for sentence templates (the % / x suffix lives in
  // the template so ES can space it: "{ctr} %").
  const dec1 = (v: number): string =>
    fmtNum(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dec0 = (v: number): string => fmtNum(v, { maximumFractionDigits: 0 });
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // A07: identity generation for every in-flight analyst request.
  // Late responses carrying the previous account's key are dropped
  // instead of rendering Account A's content under Account B.
  const accountRef = useRef(accountKey);
  accountRef.current = accountKey;
  const [input, setInput] = useState("");
  const [objective, setObjective] = useState(filters.objective || "reach");
  const [locale, setLocale] = useState("auto");
  // Backend contract (AnalystBody.language): "pl" | "en" | omitted.
  // "auto" means omit so the backend detects from the question text.
  const language = locale === "auto" ? undefined : locale;
  const [busy, setBusy] = useState(false);
  // Which action owns the in-flight request: only that button spins,
  // the others stay merely disabled. "ask" and "three-points" are
  // distinct actions so the 3 Points button never lights up Ask.
  const [op, setOp] = useState<null | "run" | "ask" | "three-points">(null);
  const [exporting, setExporting] = useState<null | "one-pager" | "xlsx" | "workbook">(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastScope, setLastScope] = useState("");
  const [datasetVersion, setDatasetVersion] = useState<string | null>(null);
  const [range, setRange] = useState("all");
  const [stamp] = useState(() => stampNow(fmtDate));

  const hooks = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=hook_type");
  const plats = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=platform");
  const campaignsRec = useScopedApi<Record<string, unknown>>("/api/campaigns");
  const creatives = useScopedApi<CreativeRow[]>("/api/creatives");

  const loadConversations = useCallback(async () => {
    const key = accountRef.current;
    try {
      const data = await api<{ conversations: ConversationSummary[] }>(
        "GET",
        "/api/analyst/conversations",
      );
      if (key !== accountRef.current) return;
      setConversations(data.conversations ?? []);
    } catch {
      /* sidebar is optional; chat still works */
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  // Deep links (?conversation=<id>, e.g. from Ask recent chats) open
  // the chosen conversation once the list arrives.
  useEffect(() => {
    if (activeId || !conversations.length) return;
    const id = new URLSearchParams(window.location.search).get("conversation");
    if (id && conversations.some((c) => c.id === id)) setActiveId(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversations]);

  // A07: even if a remount is skipped, changing identity clears all
  // account-specific chat state before reloading. busy resets too:
  // the in-flight request's finally-block stands down because its
  // key no longer matches.
  useEffect(() => {
    setConversations([]);
    setActiveId(null);
    setMessages([]);
    setError(null);
    setLastScope("");
    setDatasetVersion(null);
    setBusy(false);
    setOp(null);
    void loadConversations();
  }, [accountKey, loadConversations]);

  async function startConversation() {
    if (starting) return;
    setStarting(true);
    setError(null);
    const key = accountRef.current;
    try {
      const data = await api<{ id: string }>("POST", "/api/analyst/conversations", {
        objective: objective || undefined,
      });
      if (key !== accountRef.current) return;
      setActiveId(data.id);
      setMessages([]);
      await loadConversations();
    } catch (e) {
      if (key !== accountRef.current) return;
      setError(e instanceof Error ? e.message : t("analyst.startFailed"));
    } finally {
      if (key === accountRef.current) setStarting(false);
    }
  }

  async function send(kind: "run" | "ask" | "three-points", maxPoints?: number, override?: string) {
    const question = (override ?? input).trim();
    if (!question || busy) return;
    // A07: stamp the owning identity; a late answer from the previous
    // account is dropped instead of rendered under the new one.
    const key = accountRef.current;
    setBusy(true);
    setOp(kind);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    try {
      const data = await api<AskResponse>("POST", "/api/analyst/ask", {
        conversation_id: activeId,
        question,
        scope: scopeBody(scope),
        objective: objective || undefined,
        language,
        max_points: maxPoints,
      });
      if (key !== accountRef.current) return;
      if (!activeId) setActiveId(data.conversation_id);
      setLastScope(fmtScope(data.scope_snapshot));
      setDatasetVersion(data.dataset_version ?? null);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.answer.text, answer: data.answer },
      ]);
      await loadConversations();
    } catch (e) {
      if (key !== accountRef.current) return;
      setError(e instanceof Error ? e.message : t("analyst.askFailed"));
    } finally {
      if (key === accountRef.current) {
        setBusy(false);
        setOp((cur) => (cur === kind ? null : cur));
      }
    }
  }

  function clearAll() {
    setMessages([]);
    setInput("");
    setError(null);
    setLastScope("");
    setActiveId(null);
  }

  async function downloadReport(fmt: "one-pager" | "xlsx") {
    if (exporting !== null) return;
    setExporting(fmt);
    setError(null);
    try {
      // One-pager goes through the shared client so session expiry
      // re-gates the app; xlsx needs a raw blob fetch with parsed errors.
      const blob =
        fmt === "xlsx"
          ? await downloadReportBlob({
              scope: scopeBody(scope),
              objective: objective || undefined,
              language,
              fmt,
            })
          : new Blob(
              [
                (
                  await api<{ markdown?: string }>(
                    "POST",
                    "/api/analyst/report",
                    {
                      scope: scopeBody(scope),
                      objective: objective || undefined,
                      language,
                      fmt,
                    },
                  )
                ).markdown ?? "",
              ],
              { type: "text/markdown" },
            );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download =
        fmt === "xlsx" ? "foap-analyst-report.xlsx" : "foap-analyst-report.md";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("analyst.reportFailed"));
    } finally {
      setExporting((cur) => (cur === fmt ? null : cur));
    }
  }

  async function downloadWorkbook() {
    // The blank workbook is built server-side on demand: fetch it as a
    // blob (with parsed errors and session re-gating) instead of a
    // direct link, which would download error pages as .xlsx files.
    if (exporting !== null) return;
    setExporting("workbook");
    setError(null);
    const key = accountRef.current;
    try {
      const res = await fetch("/api/analyst/workbook");
      if (key !== accountRef.current) return;
      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as {
          detail?: { error?: string };
        } | null;
        throw new Error(detail?.detail?.error ?? `Workbook download failed (${res.status})`);
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "foap-analyst-workbook.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      if (key !== accountRef.current) return;
      setError(e instanceof Error ? e.message : t("analyst.workbookFailed"));
    } finally {
      if (key === accountRef.current) setExporting((cur) => (cur === "workbook" ? null : cur));
    }
  }

  async function decideFinding(findingId: string, decision: "accepted" | "rejected") {
    setError(null);
    const key = accountRef.current;
    try {
      await api("POST", `/api/analyst/findings/${encodeURIComponent(findingId)}`, {
        status: decision,
      });
      if (key !== accountRef.current) return;
      setMessages((prev) =>
        prev.map((m) =>
          m.answer?.findings_stored
            ? {
                ...m,
                answer: {
                  ...m.answer,
                  findings_stored: m.answer.findings_stored.map((f) =>
                    f.finding_id === findingId ? { ...f, status: decision } : f,
                  ),
                },
              }
            : m,
        ),
      );
    } catch (e) {
      if (key !== accountRef.current) return;
      setError(e instanceof Error ? e.message : t("analyst.decisionFailed"));
    }
  }

  /* ---- scope-derived analysis (real backend data, live filters) ---- */

  const hookRows = useMemo(() => {
    const rows = Object.entries(hooks.data ?? {}).map(([key, g]) => ({
      key,
      ctr: g.ctr == null ? null : g.ctr * 100,
      roas: g.roas,
      impressions: num(g.impressions),
    })).filter((r) => r.ctr != null);
    const totClicks = rows.reduce((t, r) => t + (r.ctr ?? 0) / 100 * r.impressions, 0);
    const totImpr = rows.reduce((t, r) => t + r.impressions, 0);
    const avg = totImpr ? (totClicks / totImpr) * 100 : null;
    return {
      rows: rows.sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0)),
      avg,
    };
  }, [hooks.data]);

  const platRows = useMemo(() => {
    const rows = Object.entries(plats.data ?? {}).map(([key, g]) => ({
      key,
      roas: g.roas,
      ctr: g.ctr == null ? null : g.ctr * 100,
      spend: num(g.spend),
    }));
    const totRev = rows.reduce((t, r) => t + (r.roas ?? 0) * r.spend, 0);
    const totSpend = rows.reduce((t, r) => t + r.spend, 0);
    const avg = totSpend ? totRev / totSpend : null;
    return {
      rows: rows.filter((r) => r.roas != null).sort((a, b) => (b.roas ?? 0) - (a.roas ?? 0)),
      avg,
    };
  }, [plats.data]);

  const lengthRows = useMemo(() => {
    const buckets = [
      { label: t("creatives.lengthShort"), test: (s: number) => s < 15 },
      { label: t("creatives.lengthSweet"), test: (s: number) => s >= 15 && s <= 30 },
      { label: t("creatives.lengthLong"), test: (s: number) => s > 30 },
    ].map((b) => ({ ...b, clicks: 0, impr: 0, spend: 0, revenue: 0 }));
    for (const c of creatives.data ?? []) {
      const seconds = num(c.annotation?.duration_s ?? c.duration_s);
      if (!seconds) continue;
      const bucket = buckets.find((b) => b.test(seconds));
      if (!bucket) continue;
      bucket.clicks += num(c.metrics?.clicks);
      bucket.impr += num(c.metrics?.impressions);
      bucket.spend += num(c.metrics?.spend);
      bucket.revenue += num(c.metrics?.revenue);
    }
    return buckets.map((b) => ({
      label: b.label,
      ctr: b.impr ? (b.clicks / b.impr) * 100 : null,
      roas: b.spend ? b.revenue / b.spend : null,
      impr: b.impr,
    }));
  }, [creatives.data, t]);

  const brandRows = useMemo(() => {
    const buckets = [
      { label: t("analyst.brandB0"), test: (s: number) => s < 3 },
      { label: t("analyst.brandB1"), test: (s: number) => s >= 3 && s <= 10 },
      { label: t("analyst.brandB2"), test: (s: number) => s > 10 },
    ].map((b) => ({ ...b, clicks: 0, impr: 0 }));
    for (const c of creatives.data ?? []) {
      const t = brandStart(c.annotation);
      if (t == null) continue;
      const bucket = buckets.find((b) => b.test(t));
      if (!bucket) continue;
      bucket.clicks += num(c.metrics?.clicks);
      bucket.impr += num(c.metrics?.impressions);
    }
    return buckets.map((b) => ({
      label: b.label,
      ctr: b.impr ? (b.clicks / b.impr) * 100 : null,
      impr: b.impr,
    }));
  }, [creatives.data, t]);

  const engagement = useMemo(() => {
    let top = 0;
    let views = 0;
    let impr = 0;
    for (const c of creatives.data ?? []) {
      const i = num(c.metrics?.impressions);
      const v = num(c.metrics?.video_views);
      views += v;
      impr += i;
      if (i > 0) top = Math.max(top, v / i);
    }
    const avg = impr ? views / impr : null;
    return {
      mult: avg && avg > 0 ? top / avg : null,
      ready: (creatives.data ?? []).length > 0 && views > 0,
    };
  }, [creatives.data]);

  const bestHook = hookRows.rows[0];
  const hookLift = bestHook?.ctr != null && hookRows.avg
    ? ((bestHook.ctr - hookRows.avg) / hookRows.avg) * 100 : null;
  const bestPlat = platRows.rows[0];
  const roasLift = bestPlat?.roas != null && platRows.avg
    ? ((bestPlat.roas - platRows.avg) / platRows.avg) * 100 : null;
  const bestLength = lengthRows.filter((r) => r.ctr != null)
    .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0))[0];
  const scopeReady = hookRows.rows.length > 0 || platRows.rows.length > 0;

  const summary = useMemo(() => {
    if (!scopeReady) {
      return t("analyst.summaryEmpty");
    }
    const parts: string[] = [];
    const n = (creatives.data ?? []).length;
    parts.push(tp("analyst.analysisOf", n, { count: n }));
    if (bestHook?.ctr != null) {
      parts.push(t("analyst.hookLead", {
        hook: hookName(t, bestHook.key),
        ctr: dec1(bestHook.ctr),
        lift: hookLift != null && hookLift > 0 ? t("analyst.liftAbove", { pct: dec0(hookLift) }) : "",
      }));
    }
    if (bestPlat?.roas != null) {
      parts.push(t("analyst.platLead", { plat: platformLabel(bestPlat.key), roas: dec1(bestPlat.roas) }));
    }
    if (bestLength?.ctr != null) {
      parts.push(t("analyst.lenLead", { band: bestLength.label, ctr: dec1(bestLength.ctr) }));
    }
    return parts.join(" ");
  }, [scopeReady, creatives.data, bestHook, hookLift, bestPlat, bestLength, t, tp, fmtNum]);

  // Empty loaded scope shows zero placeholders; loaded errors say
  // Unavailable. Loading renders a skeleton upstream, never these.
  const scopeFailed = Boolean(hooks.error || plats.error);
  // Loading renders a skeleton upstream (never these cards), so no
  // loading flag is needed here: unready + unfailed post-load means
  // the loaded scope genuinely holds no records.
  const emptyScope = !scopeReady && !scopeFailed;
  const liftDisplay = (lift: number | null | undefined): string => {
    if (lift == null) return emptyScope ? fmtPct(0, 0, uiLocale) : unavailable;
    return (lift > 0 ? "+" : "") + fmtPct(lift, 0, uiLocale);
  };
  const statCards = [
    {
      value: liftDisplay(hookLift),
      label: t("analyst.higherCtr"),
      sub: bestHook ? `${hookName(t, bestHook.key)} ${t("analyst.hooksSuffix")}` : t("analyst.noHook"),
      icon: "click",
      tint: "var(--shell-blue-soft)",
    },
    {
      value: liftDisplay(roasLift),
      label: t("analyst.higherRoas"),
      sub: bestPlat ? `${platformLabel(bestPlat.key)} ${t("analyst.leadingSuffix")}` : t("analyst.noPlat"),
      icon: "coin",
      tint: "var(--shell-green-soft)",
    },
    {
      value: kpiDisplay("mult", engagement.ready ? engagement.mult : null, emptyScope, uiLocale, unavailable),
      label: t("analyst.moreEng"),
      sub: t("analyst.topVsAvg"),
      icon: "users",
      tint: "var(--shell-violet-soft)",
    },
    {
      value: bestLength ? bestLength.label.replace("–", "-") : "—",
      label: t("analyst.optLen"),
      sub: bestLength?.ctr != null ? t("analyst.ctrInBand", { ctr: dec1(bestLength.ctr) }) : t("analyst.noDur"),
      icon: "bars",
      tint: "var(--shell-amber-soft)",
    },
  ];

  const storedFindings = useMemo(
    () => messages.flatMap((m) => (m.role === "assistant" ? (m.answer?.findings_stored ?? []) : [])),
    [messages],
  );

  const testNext = useMemo(() => {
    const fromFindings = storedFindings
      .map((f) => f.recommended_iteration?.trim())
      .filter((s): s is string => !!s)
      .slice(0, 4);
    if (fromFindings.length) return fromFindings;
    const out: string[] = [];
    if (bestHook) out.push(t("analyst.testScale", { hook: hookName(t, bestHook.key) }));
    if (bestPlat?.roas != null) {
      out.push(t("analyst.testShift", { plat: platformLabel(bestPlat.key), roas: dec1(bestPlat.roas) }));
    }
    if (bestLength) out.push(t("analyst.testCut", { band: bestLength.label }));
    if (brandRows.some((r) => r.ctr != null)) {
      const top = brandRows.filter((r) => r.ctr != null).sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0))[0];
      if (top) out.push(t("analyst.testBrand", { band: top.label }));
    }
    return out.slice(0, 4);
  }, [storedFindings, bestHook, bestPlat, bestLength, brandRows, t, fmtNum]);

  const relatedInsights = useMemo(() => {
    // Stat-derived only: finding signals render once, in Stored
    // Findings, so they must not repeat here.
    const out: Array<{ title: string; body: string }> = [];
    if (bestHook?.ctr != null && hookRows.rows[1]?.ctr != null) {
      const runner = hookRows.rows[1];
      const verdict = compareDisplayed(bestHook.ctr, runner.ctr ?? NaN);
      if (verdict !== "unknown") {
        const diff = bestHook.ctr - (runner.ctr ?? 0);
        const ha = hookName(t, bestHook.key);
        const hb = hookName(t, runner.key);
        out.push(verdict === "tie" ? {
          title: t("analyst.relHookTieTitle", { a: ha, b: hb }),
          body: t("analyst.relHookTieBody", { a: ha, b: hb, ctr: dec1(bestHook.ctr) }),
        } : {
          title: t("analyst.relHookLeadTitle", { a: ha }),
          body: t("analyst.relHookLeadBody", {
            a: ha, ctr: dec1(bestHook.ctr),
            diff: (diff >= 0 ? "+" : "") + dec1(diff), b: hb,
          }),
        });
      }
    }
    if (bestPlat?.roas != null) {
      const runner = platRows.rows[1];
      const verdict = runner?.roas != null
        ? compareDisplayed(bestPlat.roas, runner.roas)
        : "unknown";
      const pa = platformLabel(bestPlat.key);
      if (verdict === "tie" && runner) {
        const pb = platformLabel(runner.key);
        out.push({
          title: t("analyst.relPlatTieTitle", { a: pa, b: pb }),
          body: t("analyst.relPlatTieBody", { a: pa, b: pb, roas: dec1(bestPlat.roas) }),
        });
      } else if (verdict === "lead") {
        out.push({
          title: t("analyst.relPlatLeadTitle", { a: pa }),
          body: t("analyst.relPlatLeadBody", { a: pa, roas: dec1(bestPlat.roas) }),
        });
      } else if (verdict === "unknown" && !runner) {
        // Single platform in scope: state the number without crowning it.
        out.push({
          title: t("analyst.relPlatSnapTitle", { a: pa }),
          body: t("analyst.relPlatSnapBody", { a: pa, roas: dec1(bestPlat.roas) }),
        });
      }
    }
    if (bestLength?.ctr != null) {
      const runnerBest = Math.max(...lengthRows
        .filter((r) => r.label !== bestLength.label && r.ctr != null)
        .map((r) => r.ctr ?? Number.NaN));
      const verdict = compareDisplayed(bestLength.ctr, runnerBest);
      if (verdict === "tie") {
        out.push({
          title: t("analyst.relLenTieTitle", { a: bestLength.label }),
          body: t("analyst.relLenTieBody", { a: bestLength.label, ctr: dec1(bestLength.ctr) }),
        });
      } else if (verdict === "lead") {
        out.push({
          title: t("analyst.relLenLeadTitle", { a: bestLength.label }),
          body: t("analyst.relLenLeadBody", { a: bestLength.label, ctr: dec1(bestLength.ctr) }),
        });
      }
    }
    return out.slice(0, 3);
  }, [bestHook, hookRows.rows, bestPlat, bestLength, t, fmtNum]);

  const topCreatives = useMemo(() => {
    const rows = creatives.data ?? [];
    const score = (c: CreativeRow) => c.metrics?.roas ?? c.metrics?.ctr ?? -1;
    return rows.slice().sort((a, b) => score(b) - score(a)).slice(0, 4);
  }, [creatives.data]);

  const campaignNames = useMemo(
    () => Object.keys(campaignsRec.data ?? {}).sort(),
    [campaignsRec.data],
  );
  const metaRows = useCampaignMeta().data?.campaigns ?? [];
  const metaClients = useMemo(
    () => [...new Set(metaRows.map((r) => r.client.trim()).filter(Boolean))].sort(),
    [metaRows]);
  const metaProjects = useMemo(
    () => [...new Set(metaRows.flatMap((r) => r.projects ?? []).map((s) => s.trim()).filter(Boolean))].sort(),
    [metaRows]);

  function renderTable(table: AnalystTable, key: number) {
    return (
      <div key={key} className="tbl-wrap">
        {table.title ? <h4 style={{ margin: "12px 0 6px", fontSize: 14 }}>{table.title}</h4> : null}
        <table className="tbl">
          <thead>
            <tr>
              {table.columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell === null || cell === undefined ? "—" : String(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function findingCard(f: AnalystFinding) {
    return (
      <div key={f.finding_id} className="takeaways" style={{ marginTop: 10 }}>
        <h5>
          {f.primary_signal || f.finding_id}
          <span className={`pill finding-pill${f.status === "accepted" ? " pill-ok" : f.status === "rejected" ? " pill-bad" : " pill-info"}`}
            style={{ marginLeft: 8, verticalAlign: "middle" }}>
            {f.status === "accepted" ? t("analyst.pillAccepted") : f.status === "rejected" ? t("analyst.pillRejected") : t("analyst.pillProposed")}
          </span>
        </h5>
        <p style={{ margin: "0 0 6px", fontSize: 12.5, color: "var(--shell-muted)" }}>
          {[f.priority ? t("analyst.priorityLabel", { p: f.priority }) : "",
            f.confidence_level ? t("analyst.confidenceLabel", { c: f.confidence_level }) : ""].filter(Boolean).join(" · ")}
        </p>
        {f.diagnosis ? <p style={{ margin: "0 0 4px", fontSize: 13 }}>{t("analyst.diagnosisLabel", { d: f.diagnosis })}</p> : null}
        {f.creative_hypothesis ? <p style={{ margin: "0 0 4px", fontSize: 13 }}>{t("analyst.hypothesisLabel", { h: f.creative_hypothesis })}</p> : null}
        {f.recommended_iteration ? <p style={{ margin: "0 0 4px", fontSize: 13 }}>{t("analyst.iterationLabel", { r: f.recommended_iteration })}</p> : null}
        {f.element_to_preserve || f.element_to_change ? (
          <p style={{ margin: 0, fontSize: 13 }}>
            {t("analyst.preserveChange", { p: f.element_to_preserve || "—", c: f.element_to_change || "—" })}
          </p>
        ) : null}
        {(!f.status || f.status === "proposed") && (
          <div className="chip-row" style={{ marginTop: 10 }}>
            <button type="button" className="btn-soft"
              onClick={() => void decideFinding(f.finding_id, "accepted")}>
              {t("analyst.savePlan")}
            </button>
            <button type="button" className="btn-outline"
              onClick={() => void decideFinding(f.finding_id, "rejected")}>
              {t("analyst.dismiss")}
            </button>
          </div>
        )}
      </div>
    );
  }

  const loadingScope = hooks.data === null || plats.data === null || creatives.data === null;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">{t("analyst.eyebrow")}</p>
          <h1 className="page-title">{t("analyst.title")}</h1>
          <p className="sub">{t("analyst.sub")}</p>
        </div>
        <div className="head-actions">
          <button type="button" className="link-teal" onClick={clearAll}>
            {t("analyst.clear")}
          </button>
          <LoadingButton type="button" className="btn-primary" loading={op === "run"} loadingLabel={t("analyst.analysing")} disabled={busy || !input.trim()}
            onClick={() => void send("run")}>
            <Icon name="spark" size={16} /> {t("analyst.run")}
          </LoadingButton>
        </div>
      </div>

      <section aria-label={t("analyst.convoSection")}>
      <Panel title={t("analyst.askTitle")}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send("ask");
          }}
        >
          <div className="composer">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("analyst.inputPlaceholder")}
              aria-label={t("analyst.inputAria")}
            />
            <LoadingButton type="submit" className="btn-primary" loading={op === "ask"} loadingLabel={t("analyst.analysing")} disabled={busy || !input.trim()}>
              {t("analyst.askBtn")}
            </LoadingButton>
            <LoadingButton
              type="button"
              className="btn-outline btn-compact"
              disabled={busy || !input.trim()}
              loading={op === "three-points"}
              loadingLabel={t("analyst.condensing")}
              onClick={() => void send("three-points", 3)}
              title={t("analyst.threePointsTitle")}
            >
              <Icon name="list" size={14} /> {t("analyst.threePoints")}
            </LoadingButton>
          </div>
        </form>
        <div className="prompt-chips" aria-label={t("analyst.tryAria")}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--shell-muted)", alignSelf: "center" }}>
            {t("analyst.tryLabel")}
          </span>
          {TRY_KEYS.map((k) => {
            const q = t(`analyst.tryAsking.${k}`);
            return (
              <button key={k} type="button" className="chip chip-sugg"
                onClick={() => { setInput(q); void send('ask', undefined, q); }}>
                {q}
              </button>
            );
          })}
        </div>
      </Panel>
      </section>

      <div className="section-gap" />
      <Panel
        title={t("analyst.controlsTitle")}
        sub={t("analyst.controlsSub")}
        action={(
          <button type="button" className="link-teal" onClick={() => { clearFilters(); setRange("all"); }}>
            {t("analyst.reset")}
          </button>
        )}
      >
        <div className="filter-grid">
          <div className="field">
            <label htmlFor="a-campaign">{t("filters.campaign")}</label>
            <select id="a-campaign" value={filters.campaign}
              onChange={(e) => setFilter("campaign", e.target.value)}>
              <option value="">{t("filters.allCampaigns")}</option>
              {campaignNames.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-platform">{t("filters.platform")}</label>
            <select id="a-platform" value={filters.platform === "all" ? "" : filters.platform}
              onChange={(e) => setFilter("platform", e.target.value)}>
              <option value="">{t("filters.allPlatforms")}</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-range">{t("filters.dateRange")}</label>
            <select id="a-range" value={range}
              onChange={(e) => {
                const v = e.target.value;
                setRange(v);
                if (v === "all") {
                  setFilter("date", "");
                  setFilter("date_from", "");
                  setFilter("date_to", "");
                } else {
                  applyPresetDays(Number(v));
                }
              }}>
              {DATE_RANGES.map((r) => <option key={r.value} value={r.value}>{t(`analyst.ranges.${r.key}`)}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-objective">{t("analyst.objectiveLabel")}</label>
            <select id="a-objective" value={objective} onChange={(e) => setObjective(e.target.value)}
              aria-label={t("analyst.objectiveAria")}>
              {OBJECTIVES.map((o) => (
                <option key={o} value={o}>
                  {o === "" ? t("analyst.objectives.auto") : o === "reach" ? t("analyst.objectives.reach") : (() => { const k = `filters.objectives.${o}`; const h = t(k); return h === k ? titleCase(o) : h; })()}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-locale">{t("analyst.languageLabel")}</label>
            <select id="a-locale" value={locale} onChange={(e) => setLocale(e.target.value)} aria-label={t("analyst.languageLabel")}>
              <option value="auto">Auto</option>
              <option value="pl">Polski</option>
              <option value="en">English</option>
            </select>
          </div>
        </div>
        <details style={{ marginTop: 10 }}>
          <summary className="link-teal" style={{ cursor: "pointer", display: "inline-block" }}>
            {t("analyst.moreFilters")}
          </summary>
          <div className="cols-2-even" style={{ marginTop: 10 }}>
            <MetaSelect id="a-client" label={t("filters.client")} allLabel={t("filters.allClients")}
              values={metaClients} value={filters.client}
              onPick={(v) => setFilter("client", v)} />
            <MetaSelect id="a-project" label={t("filters.project")} allLabel={t("filters.allProjects")}
              values={metaProjects} value={filters.project}
              onPick={(v) => setFilter("project", v)} />
          </div>
          <div className="chip-row" style={{ marginTop: 10 }}>
            <LoadingButton type="button" className="btn-outline" onClick={() => void startConversation()}
              loading={starting} loadingLabel={t("analyst.starting")} spinnerClass="spinner dark"
              disabled={busy} title={t("analyst.newConvTitle")}>
              <Icon name="plus" size={14} /> {t("analyst.newConv")}
            </LoadingButton>
            <LoadingButton type="button" className="btn-outline" onClick={() => void downloadReport("one-pager")}
              loading={exporting === "one-pager"} loadingLabel={t("analyst.preparing")} spinnerClass="spinner dark"
              disabled={busy || exporting !== null} title={t("analyst.reportMdTitle")}>
              {t("analyst.reportBtn")}
            </LoadingButton>
            <LoadingButton type="button" className="btn-outline" onClick={() => void downloadReport("xlsx")}
              loading={exporting === "xlsx"} loadingLabel={t("analyst.preparing")} spinnerClass="spinner dark"
              disabled={busy || exporting !== null} title={t("analyst.reportXlsxTitle")}>
              {t("analyst.reportXlsx")}
            </LoadingButton>
            <LoadingButton type="button" className="btn-outline" onClick={() => void downloadWorkbook()}
              loading={exporting === "workbook"} loadingLabel={t("analyst.preparing")} spinnerClass="spinner dark"
              disabled={busy || exporting !== null} title={t("analyst.workbookTitle")}>
              {t("analyst.blankWorkbook")}
            </LoadingButton>
          </div>
          {conversations.length > 0 && (
            <div className="chip-row" style={{ marginTop: 10 }} aria-label={t("analyst.prevAnalyses")}>
              {conversations.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="chip"
                  aria-pressed={c.id === activeId}
                  onClick={() => {
                    setActiveId(c.id);
                    setMessages([]);
                  }}
                  title={c.objective ? t("pageInsights.objectiveBody", { objective: c.objective }) : undefined}
                >
                  {c.title || t("pageInsights.untitledConv")}
                  {typeof c.message_count === "number" ? ` (${c.message_count})` : ""}
                </button>
              ))}
            </div>
          )}
          {(lastScope || datasetVersion) && (
            <p className="panel-sub" style={{ marginTop: 10 }}>
              {lastScope}
              {datasetVersion ? ` · ${t("analyst.dataVersion", { version: datasetVersion })}` : ""}
            </p>
          )}
        </details>
      </Panel>

      {error ? (
        <p className="error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </p>
      ) : null}

      <div className="section-gap" />
      <Panel
        title={t("analyst.foundTitle")}
        sub={stamp}
        action={<span className="badge-demo">{t("analyst.aiBadge")}</span>}
      >
        {loadingScope && !scopeReady ? <Skeleton height={150} /> : (
          <>
            <p className="answer-tint" style={{ fontSize: 14, lineHeight: 1.65, margin: "0 0 4px" }}>{summary}</p>
            <div className="kpi-grid">
              {statCards.map((s) => (
                <div className="kpi-card" key={s.label}>
                  <span className="kpi-ico" style={{ background: s.tint }}>
                    <Icon name={s.icon} size={20} />
                  </span>
                  <div className="kpi-body">
                    <div className="kpi-label">{s.label}</div>
                    <div className="kpi-value">{s.value}</div>
                    <div className="kpi-label">
                      {s.sub}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      {messages.length > 0 && (
        <>
          <div className="section-gap" />
          <Panel title={t("analyst.convoTitle")} sub={t("analyst.convoSub")}>
            <div style={{ display: "grid", gap: 14 }}>
              {messages.map((m, i) => (
                <article key={i}>
                  <p style={{
                    margin: 0, fontSize: m.role === "user" ? 14 : 13.5,
                    fontWeight: m.role === "user" ? 700 : 400,
                    color: "var(--shell-navy)", lineHeight: 1.6,
                  }}>
                    {m.role === "user" ? `${t("analyst.qPrefix")}${m.text}` : m.text}
                  </p>
                  {m.role === "assistant" && m.answer ? (
                    <>
                      {(m.answer.tables ?? []).map((t, k) => renderTable(t, k))}
                      {(m.answer.findings_stored ?? []).length > 0 && (
                        <p className="panel-sub" style={{ marginTop: 8 }}>
                          {tp("analyst.findingsStored", (m.answer.findings_stored ?? []).length, { count: (m.answer.findings_stored ?? []).length })}
                        </p>
                      )}
                      {(m.answer.follow_ups ?? []).length > 0 && (
                        <div className="prompt-chips">
                          {(m.answer.follow_ups ?? []).map((q) => (
                            <button key={q} type="button" className="chip chip-sugg"
                              onClick={() => { setInput(q); void send('ask', undefined, q); }}>
                              {q}
                            </button>
                          ))}
                        </div>
                      )}
                      {(m.answer.warnings ?? []).length > 0 && (
                        <ul className="rec-list" style={{ marginTop: 8 }}>
                          {(m.answer.warnings ?? []).map((w) => (
                            <li key={w}>{w}</li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : null}
                </article>
              ))}
            </div>
          </Panel>
        </>
      )}

      <div className="section-gap" />
      <div className="cols-3">
        <Panel title={t("analyst.hookPanel")} sub={t("analyst.hookSub")}>
          {hooks.data === null ? <Skeleton height={200} /> : hookRows.rows.length ? (
            <LabeledBars
              rows={hookRows.rows.slice(0, 5).map((r) => ({ label: hookName(t, r.key), value: r.ctr ?? 0 }))}
              format={(v) => fmtPct(v, 1, uiLocale)}
            />
          ) : <EmptyState lift text={t("analyst.noHooks")} />}
        </Panel>
        <Panel title={t("analyst.lenPanel")} sub={t("analyst.lenSub")}>
          {creatives.data === null ? <Skeleton height={200} /> : lengthRows.some((r) => r.ctr != null) ? (
            <LengthCombo rows={lengthRows.map((r) => ({
              label: r.label, ctr: r.ctr ?? 0, roas: r.roas,
            }))} />
          ) : <EmptyState lift text={t("analyst.noDuration")} />}
        </Panel>
        <Panel title={t("analyst.brandPanel")} sub={t("analyst.brandSub")}>
          {creatives.data === null ? <Skeleton height={200} /> : brandRows.some((r) => r.ctr != null) ? (
            <LabeledBars
              rows={brandRows.filter((r) => r.ctr != null).map((r) => ({ label: r.label, value: r.ctr ?? 0 }))}
              format={(v) => fmtPct(v, 1, uiLocale)}
              color="#3B82C4"
            />
          ) : <EmptyState lift text={t("analyst.noBrand")} />}
        </Panel>
      </div>

      <div className="section-gap" />
      <div className="cols-3">
        <Panel title={t("analyst.testNextTitle")} sub={t("analyst.testNextSub")}>
          {testNext.length ? (
            <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 8, fontSize: 13, color: "var(--shell-navy)" }}>
              {testNext.map((item) => <li key={item}>{item}</li>)}
            </ol>
          ) : <EmptyState lift text={t("analyst.noTests")} />}
        </Panel>
        <Panel title={t("analyst.relatedTitle")} sub={t("analyst.relatedSub")}>
          {relatedInsights.length ? (
            <div>
              {relatedInsights.map((r) => (
                <div className="insight" key={r.title}>
                  <span className="insight-ico" style={{ background: "var(--shell-blue-soft)" }}>
                    <Icon name="spark" size={18} />
                  </span>
                  <div>
                    <h4>{r.title}</h4>
                    <p>{r.body}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState lift text={t("analyst.noRelated")} />}
        </Panel>
        <Panel title={t("analyst.storedTitle")} sub={t("analyst.storedSub")}>
          {storedFindings.length ? (
            <div>{storedFindings.map((f) => findingCard(f))}</div>
          ) : <EmptyState lift compact icon="bookmark" title={t("analyst.noStoredTitle")} text={t("analyst.noStoredBody")} />}
        </Panel>
      </div>

      <div className="section-gap" />
      <Panel title={t("analyst.topTitle")} sub={t("analyst.topSub")}>
        {creatives.data === null ? <Skeleton height={180} /> : topCreatives.length ? (
          <div className="creative-cards-4">
            {topCreatives.map((c) => (
              <div className="creative-card" key={c.creative_key}>
                <div className="creative-thumb-lg">
                  <CreativeThumb
                    seed={c.creative_key}
                    duration={num(c.annotation?.duration_s ?? c.duration_s) || null}
                    label={c.name || c.creative_key}
                  />
                </div>
                <p className="creative-name">{c.name || c.creative_key}</p>
                <p className="cell-sub" style={{ margin: "0 0 8px" }}>
                  {[c.platform ? platformLabel(c.platform) : "",
                    (c.campaigns ?? [])[0] || ""].filter(Boolean).join(" · ")}
                </p>
                <div className="creative-stats">
                  <span>{t("analyst.statCtr", { v: fmtCell(c.metrics?.ctr, (n) => fmtPct(n * 100, 1, uiLocale), unavailable) })}</span>
                  <span>{t("analyst.statRoas", { v: fmtCell(c.metrics?.roas, (n) => fmtMult(n, uiLocale), unavailable) })}</span>
                  <span>{t("analyst.statImpr", { n: fmtCompact(num(c.metrics?.impressions), uiLocale) })}</span>
                </div>
              </div>
            ))}
          </div>
        ) : <EmptyState lift compact icon="creatives" title={t("analyst.noTopTitle")} text={t("analyst.noTopBody")} />}
      </Panel>
    </>
  );
}

