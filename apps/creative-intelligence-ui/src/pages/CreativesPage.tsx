import { useEffect, useMemo, useRef, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";

/** Creatives library + review workspace (port of legacy Web/Index.html v-creative). */

const KPI_LOWER_BETTER = ["cpa", "cpc", "cpm"];
const MONEY_KEYS = ["spend", "cpa", "cpc", "cpm"];
const HOOK_OPTIONS = [
  "question",
  "bold_claim",
  "demo_open",
  "social_proof",
  "offer",
  "story",
  "pattern_interrupt",
  "other",
];
const FORMAT_OPTIONS = ["creator", "branded", "hybrid"];
const STRUCTURE_SLOTS = ["hook", "body", "demo", "supers", "cta", "endframe", "voiceover"];
const SOURCE_KEYS = ["source_url", "video_url", "sourceUrl", "videoUrl"];

interface TimeSpan {
  start_s: number;
  end_s?: number;
}

interface StructureSeg {
  start_s?: number;
  end_s?: number;
  confidence?: number;
}

interface Annotation {
  schema_version?: string;
  hook_type?: string;
  hook_modality?: string;
  hook_confidence?: number;
  creator_vs_branded?: string;
  creator_confidence?: number;
  edit_style?: string;
  duration_s?: number | null;
  status?: string;
  source_url?: string;
  video_url?: string;
  sourceUrl?: string;
  videoUrl?: string;
  brand_seconds?: TimeSpan[];
  product_seconds?: TimeSpan[];
  logo_seconds?: TimeSpan[];
  structure?: Record<string, StructureSeg>;
  transcript_words?: Array<{ level?: string }>;
  brand_audio_mention_s?: number | null;
  brand_audio_matches?: Array<{ end?: number; approx?: boolean }>;
  brand_audio_approx?: boolean;
  supers?: string[] | string;
  cta?: string;
  voiceover?: string;
  pace_cuts_per_min?: number | null;
  [key: string]: unknown;
}

interface CreativeRow {
  creative_key: string;
  name?: string;
  platform?: string;
  campaigns?: string[];
  duration_s?: number;
  status?: string;
  annotation?: Annotation;
  metrics?: Record<string, number | string | null | undefined>;
}

interface CurvePoint {
  t: number;
  p: number;
}

interface CurveMarkers {
  hook?: { start_s: number; end_s: number };
  product_s?: number;
  brand_s?: number;
  cta_s?: number;
}

interface RetentionCurve {
  points: CurvePoint[];
  markers?: CurveMarkers;
}

interface DropElement {
  slot?: string;
  product_demo?: boolean;
  brand_visible?: boolean;
  cta_present?: boolean;
  voiceover?: boolean;
}

interface DropEvent {
  creative_key?: string;
  start_s: number;
  end_s: number;
  seek_s?: number;
  drop_pts: number;
  from_pct?: number;
  to_pct?: number;
  element?: DropElement;
}

interface RetentionSeg {
  segment: string;
  drop_pts: number;
  n_points?: number;
}

function rankVal(v: number | string | null | undefined, lower: boolean): number {
  if (v === null || v === undefined || v === "") return lower ? Infinity : -Infinity;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function kpiText(v: number | string | null | undefined, money: boolean): string {
  if (v === null || v === undefined || v === "") return "—";
  return (money ? "$" : "") + String(v);
}

function pickSource(a: Annotation): string | null {
  for (const k of SOURCE_KEYS) {
    const u = a[k];
    if (typeof u === "string" && /^(https?:|blob:|\/media\/)/.test(u.trim())) return u.trim();
  }
  return null;
}

function spanStart(spans: TimeSpan[] | undefined): number | null {
  if (!Array.isArray(spans) || !spans.length) return null;
  const t = Number(spans[0].start_s);
  return Number.isFinite(t) ? t : null;
}

function segStart(a: Annotation, slot: string): number {
  const seg = (a.structure ?? {})[slot];
  return seg ? Number(seg.start_s) : NaN;
}

function audioTimingTxt(a: Annotation): string {
  const tw = Array.isArray(a.transcript_words) ? a.transcript_words : [];
  if (!tw.length) return "—";
  const levels = [...new Set(tw.map((e) => e.level ?? "word"))];
  return `${tw.length} timings (${levels.join("/")}-level)`;
}

function supersTxt(a: Annotation): string {
  if (Array.isArray(a.supers) && a.supers.length) return a.supers.join(", ");
  if (typeof a.supers === "string" && a.supers.trim()) return a.supers;
  const s = (a.structure ?? {}).supers ?? {};
  if ((s.end_s ?? 0) > (s.start_s ?? 0)) return `set ${s.start_s}–${s.end_s}s (from structure)`;
  return "—";
}

function brandAudioTxt(a: Annotation): string {
  if (a.brand_audio_mention_s === null || a.brand_audio_mention_s === undefined) return "—";
  const m = Array.isArray(a.brand_audio_matches) ? a.brand_audio_matches[0] : null;
  const approx = a.brand_audio_approx ?? m?.approx;
  if (!approx) return `${a.brand_audio_mention_s}s (word-level)`;
  const end = m?.end ?? "?";
  return `within ${a.brand_audio_mention_s}–${end}s segment (segment-level timing, not an exact word time)`;
}

function readFileB64(file: File): Promise<string> {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(",", 2)[1] ?? "");
    fr.onerror = () => rej(new Error("could not read file"));
    fr.readAsDataURL(file);
  });
}

function storyboardSvg(a: Annotation): { slots: string[]; dur: number } {
  return { slots: STRUCTURE_SLOTS, dur: Number(a.duration_s) || 30 };
}

/** Retention graph: curve + drops + per-segment bars, with click-to-seek and
 *  reverse sync (video timeupdate moves the playhead marker). */
function RetentionGraph({
  creativeKey,
  scope,
  videoRef,
}: {
  creativeKey: string;
  scope: URLSearchParams;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const [segs, setSegs] = useState<RetentionSeg[] | null>(null);
  const [events, setEvents] = useState<DropEvent[]>([]);
  const [curve, setCurve] = useState<RetentionCurve | null>(null);
  const [error, setError] = useState("");
  const playheadRef = useRef<SVGLineElement | null>(null);
  const labelRef = useRef<SVGTextElement | null>(null);

  useEffect(() => {
    let live = true;
    setSegs(null);
    setCurve(null);
    setEvents([]);
    setError("");
    (async () => {
      try {
        const s = await api<RetentionSeg[]>(
          "GET",
          `/api/retention?creative_key=${encodeURIComponent(creativeKey)}`,
        );
        let evs: DropEvent[] = [];
        try {
          const pats = await api<{ events?: DropEvent[] }>(
            "GET",
            scopedPath("/api/retention/patterns", scope),
          );
          if (Array.isArray(pats.events)) evs = pats.events.filter((e) => e.creative_key === creativeKey);
        } catch {
          evs = [];
        }
        let cv: RetentionCurve | null = null;
        try {
          cv = await api<RetentionCurve>(
            "GET",
            `/api/retention/curve?creative_key=${encodeURIComponent(creativeKey)}`,
          );
        } catch {
          cv = null;
        }
        if (!live) return;
        setSegs(s);
        setEvents(evs);
        setCurve(cv);
      } catch (e) {
        if (!live) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      live = false;
    };
  }, [creativeKey, scope]);

  const maxT = useMemo(() => {
    const pts = curve?.points ?? [];
    if (!pts.length) return 1;
    return Math.max(...pts.map((p) => Number(p.t) || 0), 1);
  }, [curve]);

  // Reverse sync: while the video plays, the playhead follows video.currentTime.
  useEffect(() => {
    const video = videoRef.current;
    const pts = curve?.points ?? [];
    if (!video || !pts.length) return;
    const W = 560;
    const ML = 44;
    const PW = W - ML - 8;
    const X = (t: number) => ML + Math.min(Math.max(Number(t) || 0, 0), maxT) / maxT * PW;
    const at = (t: number): number | null => {
      let bestDt = Infinity;
      let bestP: number | null = null;
      for (const p of pts) {
        const dt = Math.abs(Number(p.t) - t);
        if (dt < bestDt) {
          bestDt = dt;
          bestP = Number(p.p);
        }
      }
      return bestP;
    };
    const onTime = () => {
      const t = Number(video.currentTime) || 0;
      const head = playheadRef.current;
      const label = labelRef.current;
      if (head) {
        head.setAttribute("x1", String(X(t)));
        head.setAttribute("x2", String(X(t)));
        head.style.visibility = "visible";
      }
      if (label) {
        label.setAttribute("x", String(Math.min(X(t) + 4, 540)));
        const pct = at(t);
        label.textContent = `${t.toFixed(1)}s${pct === null ? "" : ` · ${pct}%`}`;
      }
    };
    video.addEventListener("timeupdate", onTime);
    return () => {
      video.removeEventListener("timeupdate", onTime);
    };
  }, [curve, creativeKey, maxT, videoRef]);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v && Number.isFinite(Number(t))) {
      try {
        v.currentTime = Number(t);
      } catch {
        /* jsdom / seek out of range: ignore */
      }
    }
  };

  if (error) return <span className="muted">{error}</span>;
  if (segs === null) return <span className="muted">Loading retention…</span>;

  const pts = curve?.points ?? [];
  const W = 560;
  const H = 170;
  const ML = 44;
  const MB = 24;
  const MT = 8;
  const PW = W - ML - 8;
  const PH = H - MT - MB;
  const X = (t: number) => ML + t / maxT * PW;
  const Y = (p: number) => MT + (100 - Math.min(100, Math.max(0, Number(p) || 0))) / 100 * PH;
  const mk = curve?.markers ?? {};
  const step = [1, 2, 3, 5, 6, 10, 15, 30, 60].find((s) => maxT / s <= 7) ?? Math.ceil(maxT / 7);
  const ticks: number[] = [];
  for (let t = 0; t <= maxT + 1e-9; t += step) ticks.push(t);
  const vline = (t: number | undefined, label: string, color: string, key: string) => {
    if (t === undefined || t === null || !Number.isFinite(Number(t))) return null;
    return (
      <g key={key}>
        <line
          x1={X(Number(t))}
          y1={MT}
          x2={X(Number(t))}
          y2={MT + PH}
          stroke={color}
          strokeWidth={1.5}
          strokeDasharray="4 3"
        >
          <title>{`${label} at ${t}s`}</title>
        </line>
        <text x={X(Number(t)) + 3} y={MT + 10} fontSize={10} fill={color}>
          {label}
        </text>
      </g>
    );
  };
  const segMax = Math.max(0.01, ...segs.map((s) => Number(s.drop_pts) || 0));

  return (
    <div>
      {pts.length === 0 ? (
        <div className="empty-state">No retention curve stored for this creative yet.</div>
      ) : (
        <>
          <svg
            id="retention-svg"
            data-max-t={maxT}
            viewBox={`0 0 ${W} ${H}`}
            width="100%"
            role="img"
            aria-label="Retention percentage over time"
          >
            <title>
              Retention % vs time from /api/retention/curve; shaded bands are detected drop windows
              (click to seek)
            </title>
            {[0, 25, 50, 75, 100].map((p) => (
              <g key={p}>
                <line x1={ML} y1={Y(p)} x2={W - 8} y2={Y(p)} stroke="#D8D5CE" strokeWidth={1} />
                <text x={ML - 5} y={Y(p) + 4} fontSize={10} fill="#5F6B69" textAnchor="end">
                  {p}%
                </text>
              </g>
            ))}
            {ticks.map((t) => (
              <text key={t} x={X(t)} y={H - 8} fontSize={10} fill="#5F6B69" textAnchor="middle">
                {t}s
              </text>
            ))}
            {mk.hook && mk.hook.end_s > mk.hook.start_s && (
              <rect
                x={X(mk.hook.start_s)}
                y={MT}
                width={Math.max(1, X(mk.hook.end_s) - X(mk.hook.start_s))}
                height={PH}
                style={{ fill: "var(--foap-primary)" }}
                opacity={0.14}
              >
                <title>
                  Hook window {mk.hook.start_s}–{mk.hook.end_s}s
                </title>
              </rect>
            )}
            {vline(mk.product_s, "Product", "#2E7D32", "product")}
            {vline(mk.brand_s, "Brand", "#0A7C72", "brand")}
            {vline(mk.cta_s, "CTA", "#C0362C", "cta")}
            <polyline
              points={pts.map((p) => `${X(Number(p.t)).toFixed(1)},${Y(Number(p.p)).toFixed(1)}`).join(" ")}
              fill="none"
              strokeWidth={2}
              style={{ stroke: "var(--foap-primary)" }}
            />
            {pts.map((p) => (
              <circle
                key={`${p.t}-${p.p}`}
                cx={X(Number(p.t))}
                cy={Y(Number(p.p))}
                r={2.5}
                style={{ fill: "var(--foap-primary)" }}
              >
                <title>
                  {String(p.t)}s — {String(p.p)}%
                </title>
              </circle>
            ))}
            {events.map((e, i) => (
              <rect
                key={i}
                x={X(Number(e.start_s) || 0)}
                y={MT}
                width={Math.max(3, X(Number(e.end_s) || 0) - X(Number(e.start_s) || 0))}
                height={PH}
                fill="#C0362C"
                opacity={0.16}
                style={{ cursor: "pointer" }}
                onClick={() => seek(Number(e.seek_s ?? 0))}
              >
                <title>
                  Drop −{String(e.drop_pts)} pts ({String(e.start_s)}–{String(e.end_s)}s) — click to
                  seek
                </title>
              </rect>
            ))}
            <line
              id="retention-playhead"
              ref={playheadRef}
              x1={ML}
              y1={MT}
              x2={ML}
              y2={MT + PH}
              stroke="#17211F"
              strokeWidth={2}
              style={{ visibility: "hidden" }}
            />
            <text
              id="retention-playhead-label"
              ref={labelRef}
              x={ML + 4}
              y={MT + 12}
              fontSize={11}
              fontWeight={700}
              fill="#17211F"
            />
          </svg>
          <p className="muted" style={{ fontSize: 12 }}>
            Curve: retention % over time. Teal band = hook window. Dashed lines = first product /
            brand / CTA. Red bands = detected drops (click to seek the video).
          </p>
        </>
      )}
      {events.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          No steep drops (≥5 pts) in this curve.
        </p>
      ) : (
        <ul className="plain">
          {events.map((e, i) => {
            const el = e.element ?? {};
            const bits =
              [
                el.slot ? `during ${el.slot}` : null,
                el.product_demo ? "product demo on screen" : null,
                el.brand_visible ? "brand visible" : null,
                el.cta_present ? "CTA present" : null,
                el.voiceover ? "voiceover running" : null,
              ]
                .filter(Boolean)
                .join(" · ") || "no element annotated";
            return (
              <li key={i} style={{ fontSize: 13 }}>
                <button type="button" className="chip" onClick={() => seek(Number(e.seek_s ?? 0))}>
                  {String(e.start_s)}–{String(e.end_s)}s
                </button>{" "}
                <span className="retention-drop">−{String(e.drop_pts)} pts</span> ({String(e.from_pct)}
                % → {String(e.to_pct)}%) — {bits}. Click the time chip to seek the video.
              </li>
            );
          })}
        </ul>
      )}
      {segs.length === 0 ? (
        <div className="empty-state">No retention data is available for this creative.</div>
      ) : (
        <svg
          viewBox={`0 0 560 ${segs.length * 24 + 6}`}
          width="100%"
          role="img"
          aria-label="Retention drop per segment"
        >
          <title>Retention drop per segment from /api/retention</title>
          {segs.map((s, i) => {
            const dv = Number(s.drop_pts) || 0;
            const w = Math.round((280 * dv) / segMax);
            const y = i * 24;
            const prevMax = Math.max(0, ...segs.slice(0, i).map((x) => Number(x.drop_pts) || 0));
            const worst = i > 0 && dv >= prevMax && dv > 0;
            return (
              <g key={i}>
                <text x={0} y={y + 15} fontSize={12} fill="#5F6B69">
                  {String(s.segment)}
                </text>
                <rect
                  x={110}
                  y={y + 2}
                  width={w}
                  height={15}
                  rx={4}
                  style={{ fill: "var(--foap-primary)" }}
                >
                  <title>{`${String(s.segment)}: ${dv} pts`}</title>
                </rect>
                <text x={115 + w} y={y + 15} fontSize={12} fill={dv > 0 ? "#C0362C" : "#5F6B69"}>
                  {String(dv)} pts drop (n={String(s.n_points ?? 0)}){worst ? " — biggest drop" : ""}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

export function CreativesPage() {
  const { filters, scope } = useFilters();
  const [rows, setRows] = useState<CreativeRow[] | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [brandTerms, setBrandTerms] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [mediaStatus, setMediaStatus] = useState("");
  const [benchOut, setBenchOut] = useState("");
  const [edits, setEdits] = useState<Record<string, { hook: string; format: string }>>({});
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaFileRef = useRef<HTMLInputElement | null>(null);
  const scopeKey = scope.toString();

  useEffect(() => {
    let live = true;
    setRows(null);
    setError("");
    (async () => {
      try {
        const params = new URLSearchParams(scopeKey);
        const data = await api<CreativeRow[]>("GET", scopedPath("/api/creatives", params));
        if (live) setRows(data);
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      live = false;
    };
  }, [scopeKey]);

  const kept = useMemo(() => {
    const list = rows ?? [];
    const q = filters.campaign.trim().toLowerCase();
    const filtered = q
      ? list.filter((r) =>
          [r.creative_key, r.name ?? "", (r.campaigns ?? []).join(" ")]
            .join(" | ")
            .toLowerCase()
            .includes(q),
        )
      : list.slice();
    if (!filters.kpi || filters.kpi === "all") return filtered;
    const k = filters.kpi;
    const lower = KPI_LOWER_BETTER.includes(k);
    return filtered.slice().sort((a, b) => {
      const va = rankVal(a.metrics?.[k], lower);
      const vb = rankVal(b.metrics?.[k], lower);
      return lower ? va - vb : vb - va;
    });
  }, [rows, filters.campaign, filters.kpi]);

  const selectedRow = selected ? (kept.find((r) => r.creative_key === selected) ?? null) : null;
  const selectedHidden =
    selected !== null && selectedRow === null && (rows ?? []).some((r) => r.creative_key === selected);
  const kpiKey = filters.kpi && filters.kpi !== "all" ? filters.kpi : "cpa";

  const refresh = async () => {
    try {
      const data = await api<CreativeRow[]>(
        "GET",
        scopedPath("/api/creatives", new URLSearchParams(scopeKey)),
      );
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const runPipeline = async () => {
    if (!selected) return;
    setActionStatus("");
    try {
      await api("POST", "/api/pipeline/run", { creative_key: selected, brand_terms: brandTerms });
      setActionStatus("Pipeline run complete.");
      await refresh();
    } catch (e) {
      setActionStatus(e instanceof Error ? e.message : String(e));
    }
  };

  const verifySelected = async () => {
    if (!selected) return;
    setActionStatus("");
    try {
      await api("POST", `/api/creatives/${encodeURIComponent(selected)}/verify`);
      setActionStatus("Marked HUMAN-VERIFIED.");
      await refresh();
    } catch (e) {
      setActionStatus(e instanceof Error ? e.message : String(e));
    }
  };

  const saveAnnotation = async (key: string, hook: string, format: string) => {
    const found = (rows ?? []).find((x) => x.creative_key === key);
    const base: Annotation = { ...(found?.annotation ?? {}) };
    if (!base.schema_version) base.schema_version = "v0";
    if (typeof base.hook_confidence !== "number") base.hook_confidence = 0.5;
    if (typeof base.creator_confidence !== "number") base.creator_confidence = 0.5;
    if (!Array.isArray(base.brand_seconds)) base.brand_seconds = [];
    if (!Array.isArray(base.product_seconds)) base.product_seconds = [];
    if (!Array.isArray(base.logo_seconds)) base.logo_seconds = [];
    const st = { ...(base.structure ?? {}) };
    for (const s of STRUCTURE_SLOTS) {
      st[s] = { start_s: 0, end_s: 0, confidence: 0, ...(st[s] ?? {}) };
    }
    base.structure = st;
    base.hook_type = hook;
    base.creator_vs_branded = format;
    setActionStatus("");
    try {
      await api("POST", `/api/creatives/${encodeURIComponent(key)}/annotate`, {
        annotation: base,
      });
      setActionStatus("Annotation saved.");
      await refresh();
    } catch (e) {
      setActionStatus(e instanceof Error ? e.message : String(e));
    }
  };

  const uploadMedia = async () => {
    if (!selected) {
      setMediaStatus("Select a creative below first.");
      return;
    }
    const f = mediaFileRef.current?.files?.[0];
    if (!f) {
      setMediaStatus("Choose a media file first.");
      return;
    }
    try {
      const b64 = await readFileB64(f);
      const r = await api<{ filename: string; bytes: number; url: string }>(
        "POST",
        "/api/media/upload",
        { creative_key: selected, filename: f.name, content_b64: b64, mime: f.type || undefined },
      );
      setMediaStatus(`Stored ${r.filename} (${r.bytes} bytes) → ${r.url}.`);
      await refresh();
    } catch (e) {
      setMediaStatus(e instanceof Error ? e.message : String(e));
    }
  };

  const loadBenchmark = async () => {
    if (!selectedRow) return;
    try {
      const bench = await api<Record<string, Record<string, number | null>>>(
        "GET",
        scopedPath("/api/benchmarks?group_by=campaign", new URLSearchParams(scopeKey)),
      );
      const m = selectedRow.metrics ?? {};
      const fmt = (v: number | string | null | undefined) =>
        v === null || v === undefined ? "—" : `$${String(v)}`;
      const parts = (selectedRow.campaigns ?? []).map(
        (c) => `${c}: CPA ${bench[c] ? fmt(bench[c].cpa) : "—"} vs mine ${fmt(m.cpa)}`,
      );
      setBenchOut(parts.length ? ` — ${parts.join("; ")}` : " — no campaign benchmark");
    } catch (e) {
      setBenchOut(` — ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const seekVideo = (t: number) => {
    const v = videoRef.current;
    if (v && Number.isFinite(Number(t))) {
      try {
        v.currentTime = Number(t);
      } catch {
        /* ignore seek failures */
      }
    }
  };

  const renderDetail = () => {
    if (!selected) return <p className="muted">Select a creative below.</p>;
    if (selectedHidden || !selectedRow)
      return <p className="muted">Selected creative is hidden by the current filters.</p>;
    const found = selectedRow;
    const a = found.annotation ?? {};
    const m = found.metrics ?? {};
    const src = pickSource(a);
    const hookT = segStart(a, "hook");
    const ctaT = segStart(a, "cta");
    const brandT = spanStart(a.brand_seconds);
    const productT = spanStart(a.product_seconds);
    const chips: Array<{ label: string; t: number }> = [];
    if (Number.isFinite(hookT)) chips.push({ label: "Hook", t: hookT });
    if (brandT !== null) chips.push({ label: "Brand", t: brandT });
    if (productT !== null) chips.push({ label: "Product", t: productT });
    if (Number.isFinite(ctaT)) chips.push({ label: "CTA", t: ctaT });
    const status = String(a.status ?? found.status ?? "auto");
    const { slots, dur } = storyboardSvg(a);
    const kpiRow = (label: string, value: string) => (
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, padding: "3px 0" }}>
        <span className="muted">{label}</span>
        <strong>{value}</strong>
      </div>
    );
    const intelRow = (label: string, value: string) => (
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, padding: "3px 0" }}>
        <span className="muted">{label}</span>
        <span>{value}</span>
      </div>
    );
    return (
      <div>
        <h3 style={{ margin: "0 0 2px" }}>{found.name || found.creative_key}</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
          key={found.creative_key} · {found.platform ?? "—"} ·{" "}
          <span className={status === "human_verified" ? "verified" : "unverified"}>{status}</span>
        </div>
        <div className="detail-layout">
          <div className="detail-main">
            <div>
              {src ? (
                <>
                  <video
                    id="creative-video"
                    data-testid="creative-video"
                    ref={videoRef}
                    controls
                    preload="metadata"
                    style={{ maxWidth: "100%" }}
                  >
                    <source src={src} />
                  </video>
                  <div className="muted" style={{ fontSize: 12 }}>
                    Playing annotated source URL.
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <svg viewBox="0 0 560 64" width="100%" role="img" aria-label="Storyboard">
                      <title>{`Storyboard, duration ${dur}s`}</title>
                      {slots.map((s, i) => {
                        const seg = (a.structure ?? {})[s] ?? { start_s: 0, end_s: 0 };
                        const w = Math.max(8, Math.round(560 / slots.length));
                        const op = (0.25 + (0.75 * (i + 1)) / slots.length).toFixed(2);
                        return (
                          <g key={s}>
                            <rect
                              x={i * w}
                              y={8}
                              width={w - 2}
                              height={40}
                              fill="#00C7B2"
                              fillOpacity={op}
                              stroke="#008F7F"
                            />
                            <text x={i * w + 4} y={32} fontSize={10} fill="#17211F">
                              {s}
                            </text>
                            <title>{`${s} ${seg.start_s ?? 0}-${seg.end_s ?? 0}s`}</title>
                          </g>
                        );
                      })}
                      <text x={0} y={62} fontSize={10}>
                        {`duration ${dur}s`}
                      </text>
                    </svg>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    No annotated source URL — SVG storyboard from annotation structure.
                  </div>
                </>
              )}
            </div>
            <div style={{ marginTop: 8 }}>
              {chips.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  className="chip"
                  onClick={() => seekVideo(c.t)}
                >
                  {c.label} @ {String(c.t)}s
                </button>
              ))}
            </div>
            <h4>Retention</h4>
            <div id="retention-graph" className="muted">
              <RetentionGraph
                creativeKey={found.creative_key}
                scope={new URLSearchParams(scopeKey)}
                videoRef={videoRef}
              />
            </div>
          </div>
          <div className="detail-side">
            <div className="card" style={{ margin: 0 }}>
              <h4 style={{ marginTop: 0 }}>Performance</h4>
              {kpiRow("Spend", `$${String(m.spend ?? "—")}`)}
              {kpiRow("CPM", `$${String(m.cpm ?? "—")}`)}
              {kpiRow("VTR", String(m.vtr ?? "—"))}
              {kpiRow("CTR", String(m.ctr ?? "—"))}
              {kpiRow("CPA", `$${String(m.cpa ?? "—")}`)}
              {kpiRow("ROAS", String(m.roas ?? "—"))}
              <div className="muted" style={{ fontSize: 13 }}>
                campaigns: {(found.campaigns ?? []).join(", ") || "—"} ·{" "}
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    void loadBenchmark();
                  }}
                >
                  vs benchmark
                </a>
                <span>{benchOut}</span>
              </div>
            </div>
            <div className="card" style={{ margin: 0 }}>
              <h4 style={{ marginTop: 0 }}>Creative intelligence</h4>
              {intelRow("Hook", a.hook_type ?? "—")}
              {intelRow("Hook modality (visual/spoken/text)", a.hook_modality ?? "unknown")}
              {intelRow("Creator vs branded", a.creator_vs_branded ?? "—")}
              {intelRow("Edit style", a.edit_style ?? "—")}
              {intelRow("Duration", `${String(a.duration_s ?? found.duration_s ?? "—")}s`)}
              {intelRow("Audio timings", audioTimingTxt(a))}
              {intelRow("Brand first mentioned (audio)", brandAudioTxt(a))}
              {intelRow(
                "Brand appearance",
                String(
                  a.brand_seconds && a.brand_seconds.length
                    ? `${a.brand_seconds[0].start_s}s`
                    : "—",
                ),
              )}
              {intelRow(
                "Product appearance",
                String(
                  a.product_seconds && a.product_seconds.length
                    ? `${a.product_seconds[0].start_s}s`
                    : "—",
                ),
              )}
              {intelRow("CTA", a.cta ?? ((a.structure ?? {}).cta ? "set" : "—"))}
              {intelRow("Voiceover", a.voiceover ?? ((a.structure ?? {}).voiceover ? "set" : "—"))}
              {intelRow("Supers", supersTxt(a))}
              {intelRow(
                "Editing pace",
                a.pace_cuts_per_min !== null && a.pace_cuts_per_min !== undefined
                  ? `${String(a.pace_cuts_per_min)} cuts/min`
                  : "—",
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      <h1 className="page-title">Creatives</h1>
      <p className="page-sub">Scan the work first, metrics second. Select any creative for the full review workspace.</p>
      <div className="card">
        <button type="button" className="action" onClick={() => void runPipeline()}>
          Run pipeline on selected
        </button>
        <label style={{ fontSize: 13, marginLeft: 8 }}>
          Brand terms (optional, comma-separated){" "}
          <input
            type="text"
            aria-label="Brand terms (optional, comma-separated)"
            placeholder="e.g. foap, shop now"
            style={{ maxWidth: 220 }}
            value={brandTerms}
            onChange={(e) => setBrandTerms(e.target.value)}
          />
        </label>
        <button type="button" className="action" onClick={() => void verifySelected()}>
          Mark HUMAN-VERIFIED
        </button>
        <span className="muted">Manual annotate: edit hook type / format, then Save.</span>
        {actionStatus && (
          <div className="muted" role="status" style={{ marginTop: 6 }}>
            {actionStatus}
          </div>
        )}
        <div style={{ marginTop: 10 }}>
          <h4>Media for selected creative</h4>
          <div className="ask-row">
            <input
              type="file"
              ref={mediaFileRef}
              accept="video/*,image/*,audio/*"
              aria-label="Creative media file"
            />
            <button type="button" className="action" onClick={() => void uploadMedia()}>
              Upload media
            </button>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Stored locally, linked as the creative preview and used by live analysis.{" "}
            <span>{mediaStatus}</span>
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Creative view</h3>
        <div id="creative-detail">{renderDetail()}</div>
      </div>
      {error ? (
        <div className="card">
          <p className="muted">{error}</p>
        </div>
      ) : rows === null ? (
        <p className="muted">Loading creatives…</p>
      ) : (
        <div id="library" className="creative-grid">
          {kept.length === 0 ? (
            <div className="empty-state">No creatives match the current filters.</div>
          ) : (
            kept.map((r) => {
              const a = r.annotation ?? {};
              const m = r.metrics ?? {};
              const verified = a.status === "human_verified";
              const kval = m[kpiKey];
              const ktxt =
                kval === null || kval === undefined || kval === ""
                  ? "—"
                  : MONEY_KEYS.includes(kpiKey)
                    ? `$${kval}`
                    : String(kval);
              const prev = pickSource(a);
              const hookVal = edits[r.creative_key]?.hook ?? a.hook_type ?? HOOK_OPTIONS[0];
              const fmtVal = edits[r.creative_key]?.format ?? a.creator_vs_branded ?? FORMAT_OPTIONS[0];
              const hookShown = HOOK_OPTIONS.includes(hookVal) ? hookVal : HOOK_OPTIONS[0];
              const fmtShown = FORMAT_OPTIONS.includes(fmtVal) ? fmtVal : FORMAT_OPTIONS[0];
              return (
                <div
                  key={r.creative_key}
                  className={`creative-card${selected === r.creative_key ? " selected" : ""}`}
                >
                  <div className="media">
                    {prev ? (
                      <video
                        muted
                        playsInline
                        preload="metadata"
                        src={prev}
                        title="Preview — click to play/pause"
                        onClick={(e) => {
                          const v = e.currentTarget;
                          if (v.paused) void v.play().catch(() => undefined);
                          else v.pause();
                        }}
                      />
                    ) : (
                      `${a.hook_type ?? "untagged hook"} · ${String(a.duration_s ?? r.duration_s ?? "—")}s`
                    )}
                  </div>
                  <div className="body">
                    <div className="title">{r.name || r.creative_key}</div>
                    <span className={verified ? "verified" : "unverified"}>
                      {verified ? "HUMAN-VERIFIED" : "auto"}
                    </span>
                    <span className="muted" style={{ fontSize: 13 }}>
                      {r.platform ?? "—"} · {(r.campaigns ?? []).join(", ") || "—"} ·{" "}
                      {a.creator_vs_branded ?? "—"}
                    </span>
                    <span style={{ fontSize: 13 }}>
                      <strong>{kpiKey.toUpperCase()}</strong> {ktxt} · CPA {kpiText(m.cpa, true)}
                    </span>
                    <label style={{ fontSize: 13 }}>
                      <input
                        type="radio"
                        name="sel"
                        value={r.creative_key}
                        checked={selected === r.creative_key}
                        onChange={() => {
                          setSelected(r.creative_key);
                          setBenchOut("");
                        }}
                        aria-label={`Select ${r.name || r.creative_key}`}
                      />{" "}
                      Select
                    </label>
                    <label style={{ fontSize: 13 }}>
                      Hook{" "}
                      <select
                        aria-label={`Hook type for ${r.name || r.creative_key}`}
                        value={hookShown}
                        onChange={(e) =>
                          setEdits((prevEdits) => ({
                            ...prevEdits,
                            [r.creative_key]: {
                              hook: e.target.value,
                              format:
                                prevEdits[r.creative_key]?.format ?? fmtShown,
                            },
                          }))
                        }
                      >
                        {HOOK_OPTIONS.map((h) => (
                          <option key={h} value={h}>
                            {h}
                          </option>
                        ))}
                      </select>
                    </label>{" "}
                    <label style={{ fontSize: 13 }}>
                      Format{" "}
                      <select
                        aria-label={`Format for ${r.name || r.creative_key}`}
                        value={fmtShown}
                        onChange={(e) =>
                          setEdits((prevEdits) => ({
                            ...prevEdits,
                            [r.creative_key]: {
                              hook: prevEdits[r.creative_key]?.hook ?? hookShown,
                              format: e.target.value,
                            },
                          }))
                        }
                      >
                        {FORMAT_OPTIONS.map((h) => (
                          <option key={h} value={h}>
                            {h}
                          </option>
                        ))}
                      </select>
                    </label>{" "}
                    <button
                      type="button"
                      className="action save"
                      onClick={() => void saveAnnotation(r.creative_key, hookShown, fmtShown)}
                    >
                      Save annotation
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </>
  );
}
