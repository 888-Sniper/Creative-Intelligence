import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import {
  CreativeThumb,
  EmptyState,
  Panel,
  Skeleton,
  fmtCompact,
  platformLabel,
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

const TRY_ASKING = [
  "Which hook types drive the highest CTR?",
  "What video length performs best?",
  "When should the brand appear for maximum impact?",
  "Which creatives should we scale next?",
];

const DATE_RANGES = [
  { value: "all", label: "All Time" },
  { value: "7", label: "Last 7 Days" },
  { value: "30", label: "Last 30 Days" },
  { value: "90", label: "Last 90 Days" },
];

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

function stampNow(): string {
  const d = new Date();
  const date = d.toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
  const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  return `${date} at ${time}`;
}

/** Accessible horizontal bars (value labels, no chart lib needed for
 *  single-series breakdowns). */
function LabeledBars({ rows, format, color = "#00B3A0" }: {
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
        aria-label={rows.map((r) => `${r.label}: ${r.ctr.toFixed(1)} percent CTR`).join("; ")}
        style={{ width: "100%", height: "auto", display: "block" }}>
        {[0, 0.5, 1].map((t) => {
          const y = padT + ih * (1 - t);
          return (
            <g key={t}>
              <line x1={padL} x2={w - 6} y1={y} y2={y} stroke="var(--shell-line)" strokeWidth="1" />
              <text x={padL - 7} y={y + 4} textAnchor="end" fontSize="11" fill="var(--shell-faint)">
                {(maxCtr * t).toFixed(1)}%
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
              <rect x={x} y={y} width={bw} height={bh} rx="5" fill="#00B3A0" />
              <text x={x + bw / 2} y={y - 6} textAnchor="middle" fontSize="12"
                fontWeight="700" fill="var(--shell-navy)">
                {r.ctr.toFixed(1)}%
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
        <span><i style={{ background: "#00B3A0" }} />CTR</span>
        <span><i style={{ background: "#E8833A" }} />ROAS</span>
      </div>
    </div>
  );
}

export function AnalystPage({ accountKey = "" }: { accountKey?: string }) {
  const { filters, setFilter, clearFilters, applyPresetDays, scope } = useFilters();
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
  const [error, setError] = useState<string | null>(null);
  const [lastScope, setLastScope] = useState("");
  const [datasetVersion, setDatasetVersion] = useState<string | null>(null);
  const [range, setRange] = useState("all");
  const [stamp] = useState(stampNow);

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
    void loadConversations();
  }, [accountKey, loadConversations]);

  async function startConversation() {
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
      setError(e instanceof Error ? e.message : "Could Not Start A Conversation");
    }
  }

  async function send(maxPoints?: number, override?: string) {
    const question = (override ?? input).trim();
    if (!question || busy) return;
    // A07: stamp the owning identity; a late answer from the previous
    // account is dropped instead of rendered under the new one.
    const key = accountRef.current;
    setBusy(true);
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
      setError(e instanceof Error ? e.message : "Analyst Request Failed");
    } finally {
      if (key === accountRef.current) setBusy(false);
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
      setError(e instanceof Error ? e.message : "Report Export Failed");
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
      setError(e instanceof Error ? e.message : "Could Not Save The Decision");
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
      { label: "Under 15s", test: (s: number) => s < 15 },
      { label: "15–30s", test: (s: number) => s >= 15 && s <= 30 },
      { label: "Over 30s", test: (s: number) => s > 30 },
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
  }, [creatives.data]);

  const brandRows = useMemo(() => {
    const buckets = [
      { label: "First 3s", test: (s: number) => s < 3 },
      { label: "3–10s", test: (s: number) => s >= 3 && s <= 10 },
      { label: "After 10s", test: (s: number) => s > 10 },
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
  }, [creatives.data]);

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
      return "No benchmark data in the current scope yet. Widen the filters or ask a question below — every answer is grounded in your uploaded data.";
    }
    const parts: string[] = [];
    const n = (creatives.data ?? []).length;
    parts.push(`Analysis of ${n} creative${n === 1 ? "" : "s"} in the current scope.`);
    if (bestHook?.ctr != null) {
      parts.push(`${titleCase(bestHook.key)} hooks lead at ${bestHook.ctr.toFixed(1)}% CTR${
        hookLift != null && hookLift > 0 ? `, ${hookLift.toFixed(0)}% above the scope average` : ""
      }.`);
    }
    if (bestPlat?.roas != null) {
      parts.push(`${platformLabel(bestPlat.key)} delivers the strongest ROAS at ${bestPlat.roas.toFixed(1)}x.`);
    }
    if (bestLength?.ctr != null) {
      parts.push(`${bestLength.label} videos hold attention best at ${bestLength.ctr.toFixed(1)}% CTR.`);
    }
    return parts.join(" ");
  }, [scopeReady, creatives.data, bestHook, hookLift, bestPlat, bestLength]);

  const statCards = [
    {
      value: hookLift != null && hookLift > 0 ? `+${hookLift.toFixed(0)}%` : "—",
      label: "Higher CTR",
      sub: bestHook ? `${titleCase(bestHook.key)} hooks` : "No hook data",
      icon: "click",
      tint: "#E7F1FB",
    },
    {
      value: roasLift != null && roasLift > 0 ? `+${roasLift.toFixed(0)}%` : "—",
      label: "Higher ROAS",
      sub: bestPlat ? `${platformLabel(bestPlat.key)} leading` : "No platform data",
      icon: "coin",
      tint: "#E5F5EC",
    },
    {
      value: engagement.mult != null && engagement.ready ? `${engagement.mult.toFixed(1)}x` : "—",
      label: "More Engagement",
      sub: "Top creative vs average",
      icon: "users",
      tint: "#EFEAFB",
    },
    {
      value: bestLength ? bestLength.label.replace("–", "-") : "—",
      label: "Optimal Video Length",
      sub: bestLength?.ctr != null ? `${bestLength.ctr.toFixed(1)}% CTR in band` : "No duration data",
      icon: "bars",
      tint: "#FBF3E2",
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
    if (bestHook) out.push(`Scale ${titleCase(bestHook.key)} openings into three new first-frame variants.`);
    if (bestPlat?.roas != null) {
      out.push(`Shift incremental budget to ${platformLabel(bestPlat.key)} while ROAS holds above ${bestPlat.roas.toFixed(1)}x.`);
    }
    if (bestLength) out.push(`Cut the next flight to ${bestLength.label} first and re-test hold.`);
    if (brandRows.some((r) => r.ctr != null)) {
      const top = brandRows.filter((r) => r.ctr != null).sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0))[0];
      if (top) out.push(`Move first brand appearance into the ${top.label} window.`);
    }
    return out.slice(0, 4);
  }, [storedFindings, bestHook, bestPlat, bestLength, brandRows]);

  const relatedInsights = useMemo(() => {
    // Stat-derived only: finding signals render once, in Stored
    // Findings, so they must not repeat here.
    const out: Array<{ title: string; body: string }> = [];
    if (bestHook?.ctr != null && hookRows.rows[1]?.ctr != null) {
      const diff = bestHook.ctr - (hookRows.rows[1].ctr ?? 0);
      out.push({
        title: `${titleCase(bestHook.key)} Hooks Drive Higher CTR`,
        body: `${titleCase(bestHook.key)} openings average ${bestHook.ctr.toFixed(1)}% CTR, ${diff >= 0 ? "+" : ""}${diff.toFixed(1)}pts versus ${titleCase(hookRows.rows[1].key)}.`,
      });
    }
    if (bestPlat?.roas != null) {
      out.push({
        title: `${platformLabel(bestPlat.key)} Leads On Efficiency`,
        body: `${platformLabel(bestPlat.key)} averages ${bestPlat.roas.toFixed(1)}x ROAS across the current scope.`,
      });
    }
    if (bestLength?.ctr != null) {
      out.push({
        title: `${bestLength.label} Is The Length To Beat`,
        body: `${bestLength.label} videos average ${bestLength.ctr.toFixed(1)}% CTR — build variants inside that band first.`,
      });
    }
    return out.slice(0, 3);
  }, [bestHook, hookRows.rows, bestPlat, bestLength]);

  const topCreatives = useMemo(() => {
    const rows = creatives.data ?? [];
    const score = (c: CreativeRow) => c.metrics?.roas ?? c.metrics?.ctr ?? -1;
    return rows.slice().sort((a, b) => score(b) - score(a)).slice(0, 4);
  }, [creatives.data]);

  const campaignNames = useMemo(
    () => Object.keys(campaignsRec.data ?? {}).sort(),
    [campaignsRec.data],
  );

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
        <h5>{f.primary_signal || f.finding_id}</h5>
        <p style={{ margin: "0 0 6px", fontSize: 12.5, color: "var(--shell-muted)" }}>
          {[f.priority ? `Priority: ${f.priority}` : "",
            f.confidence_level ? `Confidence: ${f.confidence_level}` : "",
            f.status && f.status !== "proposed" ? f.status : ""].filter(Boolean).join(" · ")}
        </p>
        {f.diagnosis ? <p style={{ margin: "0 0 4px", fontSize: 13 }}>Diagnosis: {f.diagnosis}</p> : null}
        {f.creative_hypothesis ? <p style={{ margin: "0 0 4px", fontSize: 13 }}>Hypothesis: {f.creative_hypothesis}</p> : null}
        {f.recommended_iteration ? <p style={{ margin: "0 0 4px", fontSize: 13 }}>Iteration: {f.recommended_iteration}</p> : null}
        {f.element_to_preserve || f.element_to_change ? (
          <p style={{ margin: 0, fontSize: 13 }}>
            Preserve: {f.element_to_preserve || "—"} · Change: {f.element_to_change || "—"}
          </p>
        ) : null}
        {(!f.status || f.status === "proposed") && (
          <div className="chip-row" style={{ marginTop: 10 }}>
            <button type="button" className="btn-soft"
              onClick={() => void decideFinding(f.finding_id, "accepted")}>
              Save To Next-Flight Plan
            </button>
            <button type="button" className="btn-outline"
              onClick={() => void decideFinding(f.finding_id, "rejected")}>
              Dismiss
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
          <p className="eyebrow">AI Analyst</p>
          <h1 className="page-title">Your Creative Partner</h1>
          <p className="sub">Ask questions, uncover insights, and get recommendations from your creative data.</p>
        </div>
        <div className="head-actions">
          <button type="button" className="link-teal" onClick={clearAll}>
            Clear
          </button>
          <button type="button" className="btn-primary" disabled={busy || !input.trim()}
            onClick={() => void send()}>
            {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="spark" size={16} />}
            {busy ? "Analysing…" : "Run Analysis"}
          </button>
        </div>
      </div>

      <section aria-label="Foap Analyst Conversation">
      <Panel title="Ask Anything">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className="composer">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything about your campaigns, creatives, or performance…"
              aria-label="Ask Foap Analyst"
            />
            <button type="submit" className="btn-primary" disabled={busy || !input.trim()}>
              {busy ? "Analysing…" : "Ask"}
            </button>
            <button
              type="button"
              className="btn-outline"
              disabled={busy || !input.trim()}
              onClick={() => void send(3)}
              title="Condense The Answer To 3 Points"
            >
              3 Points
            </button>
          </div>
        </form>
        <div className="prompt-chips" aria-label="Try asking">
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--shell-muted)", alignSelf: "center" }}>
            Try asking:
          </span>
          {TRY_ASKING.map((q) => (
            <button key={q} type="button" className="chip"
              onClick={() => { setInput(q); void send(undefined, q); }}>
              {q}
            </button>
          ))}
        </div>
      </Panel>
      </section>

      <div className="section-gap" />
      <Panel
        title="Analysis Filters"
        sub="Every answer and chart respects this scope."
        action={(
          <button type="button" className="link-teal" onClick={() => { clearFilters(); setRange("all"); }}>
            Reset
          </button>
        )}
      >
        <div className="filter-grid">
          <div className="field">
            <label htmlFor="a-client">Client</label>
            <input id="a-client" placeholder="All Clients" value={filters.client}
              onChange={(e) => setFilter("client", e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="a-project">Project</label>
            <input id="a-project" placeholder="All Projects" value={filters.project}
              onChange={(e) => setFilter("project", e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="a-campaign">Campaign</label>
            <select id="a-campaign" value={filters.campaign}
              onChange={(e) => setFilter("campaign", e.target.value)}>
              <option value="">All Campaigns</option>
              {campaignNames.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-platform">Platform</label>
            <select id="a-platform" value={filters.platform === "all" ? "" : filters.platform}
              onChange={(e) => setFilter("platform", e.target.value)}>
              <option value="">All Platforms</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-range">Date Range</label>
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
              {DATE_RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
        </div>
      </Panel>

      <div className="section-gap" />
      <Panel title="Analyst Controls" sub="Objective, language, conversations, and exports.">
        <div className="chip-row">
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600 }}>
            Objective{" "}
            <select value={objective} onChange={(e) => setObjective(e.target.value)}
              aria-label="Objective">
              {OBJECTIVES.map((o) => (
                <option key={o} value={o}>
                  {(o || "auto").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600 }}>
            Language{" "}
            <select value={locale} onChange={(e) => setLocale(e.target.value)} aria-label="Language">
              <option value="auto">Auto</option>
              <option value="pl">Polski</option>
              <option value="en">English</option>
            </select>
          </label>
          <button type="button" className="btn-outline" onClick={() => void startConversation()}>
            <Icon name="plus" size={14} /> New Conversation
          </button>
          <button type="button" className="btn-outline" onClick={() => void downloadReport("one-pager")}
            disabled={busy} title="Sectioned Findings Report (Markdown)">
            Report
          </button>
          <button type="button" className="btn-outline" onClick={() => void downloadReport("xlsx")}
            disabled={busy} title="Sectioned Findings Report (Excel)">
            Report XLSX
          </button>
          <a className="btn-outline" style={{ textDecoration: "none" }} href="/api/analyst/workbook">
            Blank Workbook
          </a>
        </div>
        {conversations.length > 0 && (
          <div className="chip-row" style={{ marginTop: 12 }} aria-label="Previous analyses">
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
                title={c.objective ? `Objective: ${c.objective}` : undefined}
              >
                {c.title || "Untitled Conversation"}
                {typeof c.message_count === "number" ? ` (${c.message_count})` : ""}
              </button>
            ))}
          </div>
        )}
        {(lastScope || datasetVersion) && (
          <p className="panel-sub" style={{ marginTop: 10 }}>
            {lastScope}
            {datasetVersion ? ` · Data v${datasetVersion}` : ""}
          </p>
        )}
      </Panel>

      {error ? (
        <p className="error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </p>
      ) : null}

      <div className="section-gap" />
      <Panel
        title="Here's What I Found"
        sub={stamp}
        action={<span className="badge-demo">AI Analysis</span>}
      >
        {loadingScope && !scopeReady ? <Skeleton height={150} /> : (
          <>
            <p style={{ fontSize: 14, lineHeight: 1.65, margin: "0 0 4px" }}>{summary}</p>
            <div className="kpi-grid">
              {statCards.map((s) => (
                <div className="kpi-card" key={s.label}>
                  <span className="kpi-ico" style={{ background: s.tint }}>
                    <Icon name={s.icon} size={22} />
                  </span>
                  <div className="kpi-body">
                    <div className="kpi-label">{s.label}</div>
                    <div className="kpi-value">{s.value}</div>
                    <div className="kpi-label" style={{ textTransform: "none", letterSpacing: 0 }}>
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
          <Panel title="Conversation" sub="Questions and grounded answers for this session.">
            <div style={{ display: "grid", gap: 14 }}>
              {messages.map((m, i) => (
                <article key={i}>
                  <p style={{
                    margin: 0, fontSize: m.role === "user" ? 14 : 13.5,
                    fontWeight: m.role === "user" ? 700 : 400,
                    color: "var(--shell-navy)", lineHeight: 1.6,
                  }}>
                    {m.role === "user" ? `Q: ${m.text}` : m.text}
                  </p>
                  {m.role === "assistant" && m.answer ? (
                    <>
                      {(m.answer.tables ?? []).map((t, k) => renderTable(t, k))}
                      {(m.answer.findings_stored ?? []).length > 0 && (
                        <p className="panel-sub" style={{ marginTop: 8 }}>
                          {(m.answer.findings_stored ?? []).length} finding
                          {(m.answer.findings_stored ?? []).length === 1 ? "" : "s"} stored
                          below — review and accept them in Stored Findings.
                        </p>
                      )}
                      {(m.answer.follow_ups ?? []).length > 0 && (
                        <div className="prompt-chips">
                          {(m.answer.follow_ups ?? []).map((q) => (
                            <button key={q} type="button" className="chip"
                              onClick={() => { setInput(q); void send(undefined, q); }}>
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
        <Panel title="Top Performing Hook Types" sub="CTR by opening hook across the scope.">
          {hooks.data === null ? <Skeleton height={200} /> : hookRows.rows.length ? (
            <LabeledBars
              rows={hookRows.rows.slice(0, 5).map((r) => ({ label: titleCase(r.key), value: r.ctr ?? 0 }))}
              format={(v) => `${v.toFixed(1)}%`}
            />
          ) : <EmptyState text="No hook benchmarks in scope." />}
        </Panel>
        <Panel title="Video Length Performance" sub="CTR bars with ROAS trend by duration band.">
          {creatives.data === null ? <Skeleton height={200} /> : lengthRows.some((r) => r.ctr != null) ? (
            <LengthCombo rows={lengthRows.map((r) => ({
              label: r.label, ctr: r.ctr ?? 0, roas: r.roas,
            }))} />
          ) : <EmptyState text="No duration data in scope." />}
        </Panel>
        <Panel title="Performance by Brand Timing" sub="CTR by first brand appearance.">
          {creatives.data === null ? <Skeleton height={200} /> : brandRows.some((r) => r.ctr != null) ? (
            <LabeledBars
              rows={brandRows.filter((r) => r.ctr != null).map((r) => ({ label: r.label, value: r.ctr ?? 0 }))}
              format={(v) => `${v.toFixed(1)}%`}
              color="#3B82C4"
            />
          ) : <EmptyState text="No brand-timing annotations in scope." />}
        </Panel>
      </div>

      <div className="section-gap" />
      <div className="cols-2">
        <Panel title="What To Test Next" sub="Numbered next-flight plan from the latest findings.">
          {testNext.length ? (
            <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 10, fontSize: 13.5, color: "var(--shell-navy)" }}>
              {testNext.map((t) => <li key={t}>{t}</li>)}
            </ol>
          ) : <EmptyState text="Ask a question to generate test ideas." />}
        </Panel>
        <Panel title="Related Insights" sub="Signals behind the current analysis.">
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
          ) : <EmptyState text="No related insights in scope." />}
        </Panel>
      </div>

      <div className="section-gap" />
      <Panel title="Stored Findings" sub="Saved analyst findings with accept / dismiss decisions.">
        {storedFindings.length ? (
          <div>{storedFindings.map((f) => findingCard(f))}</div>
        ) : <EmptyState text="No stored findings yet — ask a question to generate findings." />}
      </Panel>

      <div className="section-gap" />
      <Panel title="Top Performing Creatives" sub="From this analysis — ranked by ROAS, then CTR.">
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
                  <span>CTR {c.metrics?.ctr == null ? "—" : `${(c.metrics.ctr * 100).toFixed(1)}%`}</span>
                  <span>ROAS {c.metrics?.roas == null ? "—" : `${c.metrics.roas.toFixed(1)}x`}</span>
                  <span>{fmtCompact(num(c.metrics?.impressions))} impr</span>
                </div>
              </div>
            ))}
          </div>
        ) : <EmptyState text="No creatives in scope." />}
      </Panel>
    </>
  );
}

