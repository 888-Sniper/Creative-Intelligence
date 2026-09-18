import { useEffect, useMemo, useRef, useState } from "react";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { MediaPreview } from "@/components/MediaPreview";
import { MetaSelect, Toast, useCampaignMeta } from "@/components/product";
import {
  analyzeDraft,
  confirmMatch,
  correctDraft,
  createDraft,
  deleteDraftVideos,
  draftKey,
  formatBytes,
  getAnalysis,
  getCandidates,
  getDraft,
  getVideoLimits,
  HOOK_TYPE_OPTIONS,
  importDataset,
  MATCH_METHODS,
  parseSnapshots,
  patchDraft,
  proposeMatch,
  reviewDraft,
  SheetConflictError,
  uploadMedia,
  validateVideo,
  type DatasetCandidate,
  type DraftAnalysis,
  type DraftCorrections,
  type DraftMatch,
  type DraftView,
  type MatchSnapshot,
  type VideoLimits,
  type VideoUploadSpec,
} from "@/components/videoUploadApi";

export type UploadStage = "video" | "client" | "dataset" | "review";

export interface PanelOpen {
  draftId?: string;
  file?: File | null;
  stage?: UploadStage;
}

interface PanelProps {
  open: PanelOpen | null;
  employeeId: string;
  onClose: (refresh: boolean) => void;
}

const STAGES: UploadStage[] = ["video", "client", "dataset", "review"];

function stageForSpec(spec: VideoUploadSpec): UploadStage {
  if (spec.video?.status !== "valid") return "video";
  if (!spec.clientConfirmed) return "client";
  if (!spec.dataset) return "dataset";
  return "review";
}

function slugKey(name: string): string {
  return name
    .toLowerCase()
    .replace(/\.[a-z0-9]+$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

export function isVideoFile(file: File): boolean {
  const type = (file.type || "").toLowerCase();
  if (type === "video/mp4" || type === "video/quicktime") return true;
  return /\.(mp4|mov)$/i.test(file.name || "");
}

/** Server match rows are the source of truth (see boot hydration);
 *  no localStorage mirror is kept, so a cleared server confirmation
 *  can never be resurrected by stale browser state. */

/** Merge server rows back into the working spec so a reopened draft
 *  recovers its video/dataset even if it was closed before saving. */
function specFromDraft(draft: DraftView): VideoUploadSpec {
  const spec: VideoUploadSpec = { ...(draft.spec ?? {}) };
  const video = draft.videos?.[0];
  if (video && !spec.video) {
    let verdict: { status?: string; reason?: string } = {};
    try {
      verdict = JSON.parse(video.validation_json || "{}") as { status?: string; reason?: string };
    } catch {
      verdict = {};
    }
    spec.video = {
      video_id: video.id,
      duration_s: Number(video.duration_s) || 0,
      width: Number(video.width) || 0,
      height: Number(video.height) || 0,
      status: verdict.status === "valid" ? "valid" : "invalid",
      reason: typeof verdict.reason === "string" ? verdict.reason : undefined,
    };
    spec.creative_key = spec.creative_key || video.creative_key || undefined;
    if (video.media_id && !spec.media) {
      spec.media = {
        id: video.media_id, filename: "", bytes: 0, sha256: video.sha256 || "",
        url: `/media/${video.media_id}`,
      };
    }
  }
  const dataset = draft.datasets?.[0];
  if (dataset && !spec.dataset) {
    spec.dataset = {
      dataset_id: dataset.id, version: dataset.version || draft.dataset_version || "",
      rows: Number(dataset.rows) || 0, inserted: 0, updated: 0, quarantined: 0,
      filename: dataset.filename || "",
    };
  }
  return spec;
}

interface FrameMoment {
  t: number;
  label: string;
  flags: string[];
}

/** Rendering of a finished analysis: observed structure, measured
 *  dataset numbers, timestamped key moments with playback seeking,
 *  and suggested (never proven) tests — plus human correction
 *  controls. A review note cannot rewrite the underlying finding, so
 *  transcript text, hook values, frame moments, and per-test verdicts
 *  each save back to the stored annotation (with a fresh revision);
 *  pass `correction` to enable them. */
export function FindingsView({
  analysis, vu, onSeek, correction,
}: {
  analysis: DraftAnalysis;
  vu: (key: string, vars?: Record<string, string | number>) => string;
  onSeek?: (t: number) => void;
  correction?: { onCorrect: (c: DraftCorrections) => Promise<void> };
}) {
  const ann = (analysis.annotation ?? {}) as Record<string, unknown>;
  const block = (ann["analysis"] ?? {}) as Record<string, unknown>;
  const measured = (block["measured"] ?? {}) as Record<string, unknown>;
  const totals = (measured["totals"] ?? {}) as Record<string, unknown>;
  const tests = Array.isArray(block["suggested_tests"])
    ? (block["suggested_tests"] as Array<Record<string, unknown>>) : [];
  const rawMoments: Array<Record<string, unknown>> = Array.isArray(ann["frame_labels"])
    ? (ann["frame_labels"] as Array<Record<string, unknown>>)
      .filter((f) => typeof f["t_sec"] === "number")
    : [];
  const moments: FrameMoment[] = rawMoments.map((f) => {
    const flags: string[] = [];
    if (f["brand_visible"]) flags.push("brand");
    if (f["product_visible"]) flags.push("product");
    if (f["logo_visible"]) flags.push("logo");
    if (f["cta_visible"]) flags.push("CTA");
    if (f["end_frame"]) flags.push("end");
    return {
      t: Number(f["t_sec"]),
      label: String(f["label"] ?? ""),
      flags,
    };
  });
  const hookType = typeof ann["hook_type"] === "string" ? String(ann["hook_type"]) : "other";
  const hookConf = typeof ann["hook_confidence"] === "number"
    && Number.isFinite(ann["hook_confidence"]) ? Number(ann["hook_confidence"]) : 0;
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [correctError, setCorrectError] = useState("");
  const submitCorrection = async (section: string, c: DraftCorrections): Promise<void> => {
    if (!correction || busy) return;
    setBusy(section);
    setCorrectError("");
    try {
      await correction.onCorrect(c);
    } catch (e) {
      setCorrectError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const num = (v: unknown): string =>
    typeof v === "number" && Number.isFinite(v) ? String(v) : "—";
  const ctr = measured["pooled_link_ctr_pct"];
  const measureWarnings: string[] = Array.isArray(measured["warnings"])
    ? (measured["warnings"] as unknown[]).map(String) : [];
  const coverage = (measured["coverage"] ?? {}) as Record<string, unknown>;
  const coverageText = [
    Array.isArray(coverage["platforms"]) ? (coverage["platforms"] as unknown[]).map(String).join(", ") : "",
    Array.isArray(coverage["currencies"]) ? (coverage["currencies"] as unknown[]).map(String).join(", ") : "",
    Array.isArray(coverage["date_range"]) ? (coverage["date_range"] as unknown[]).map(String).join(" – ") : "",
  ].filter(Boolean).join(" · ");
  return (
    <div style={{ marginTop: 12 }}>
      <h4 className="panel-title" style={{ fontSize: 13 }}>{vu("findingsTitle")}</h4>
      <p className="panel-sub">
        {vu("analyzedWith", {
          model: String(block["model"] || "—"),
          version: String(block["version"] || "—"),
        })}
      </p>
      <div className="detail-list" style={{ marginTop: 8 }}>
        <div>
          <p className="panel-sub" style={{ fontWeight: 700 }}>{vu("measuredTitle")}</p>
          <p className="panel-sub" style={{ marginTop: 0 }}>
            {vu("measuredSummary", {
              impressions: num(totals["impressions"]),
              clicks: num(totals["link_clicks"]),
              ctr: typeof ctr === "number" ? ctr : "—",
            })}
          </p>
        </div>
        {analysis.transcript ? (
          <div>
            <p className="panel-sub" style={{ fontWeight: 700 }}>{vu("transcriptTitle")}</p>
            <p className="panel-sub" style={{ marginTop: 0, whiteSpace: "pre-wrap" }}>
              {analysis.transcript}
            </p>
          </div>
        ) : null}
        {coverageText ? (
          <div>
            <p className="panel-sub" style={{ fontWeight: 700 }}>{vu("coverageTitle")}</p>
            <p className="panel-sub" style={{ marginTop: 0 }}>{coverageText}</p>
          </div>
        ) : null}
      </div>
      {measureWarnings.length ? (
        <div style={{ marginTop: 8 }}>
          <h4 className="panel-title" style={{ fontSize: 13 }}>{vu("reviewWarningsTitle")}</h4>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {measureWarnings.map((w, i) => (
              <li key={i} className="panel-sub">{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {moments.length ? (
        <>
          <h4 className="panel-title" style={{ fontSize: 13, marginTop: 10 }}>
            {vu("momentsTitle")}
          </h4>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {moments.map((m, i) => (
              <li key={`${m.t}-${i}`} className="panel-sub">
                {onSeek ? (
                  <button
                    type="button" className="link-teal"
                    onClick={() => onSeek(m.t)}
                    aria-label={vu("seekBtn", { t: m.t })}
                  >
                    {vu("momentLabel", {
                      t: Math.round(m.t * 10) / 10,
                      label: m.label || "—",
                      flags: m.flags.length ? ` (${m.flags.join(", ")})` : "",
                    })}
                  </button>
                ) : (
                  vu("momentLabel", {
                    t: Math.round(m.t * 10) / 10,
                    label: m.label || "—",
                    flags: m.flags.length ? ` (${m.flags.join(", ")})` : "",
                  })
                )}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {tests.length ? (
        <>
          <h4 className="panel-title" style={{ fontSize: 13, marginTop: 10 }}>
            {vu("suggestedTitle")}
          </h4>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {tests.map((suggestion, i) => {
              const testId = String(suggestion["id"] ?? i);
              const testStatus = String(suggestion["status"] ?? "suggested");
              return (
                <li key={testId} className="panel-sub">
                  <strong>{String(suggestion["hypothesis"] ?? "")}</strong>
                  {suggestion["why"] ? ` — ${String(suggestion["why"])}` : ""}
                  {testStatus !== "suggested" ? ` [${testStatus}]` : ""}
                  {correction && suggestion["id"] ? (
                    <span className="chip-row" style={{ marginTop: 4 }}>
                      <button
                        type="button" className="btn-outline"
                        disabled={busy !== null || testStatus === "accepted"}
                        onClick={() => void submitCorrection(`test-${testId}`, {
                          tests: [{ id: testId, status: "accepted" }],
                        })}
                      >
                        {vu("acceptTestBtn")}
                      </button>
                      <button
                        type="button" className="btn-outline"
                        disabled={busy !== null || testStatus === "rejected"}
                        onClick={() => void submitCorrection(`test-${testId}`, {
                          tests: [{ id: testId, status: "rejected" }],
                        })}
                      >
                        {vu("rejectTestBtn")}
                      </button>
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
      {correction ? (
        <div style={{ marginTop: 10 }}>
          <button
            type="button" className="btn-outline"
            onClick={() => { setEditing((v) => !v); setCorrectError(""); }}
            aria-expanded={editing}
          >
            {vu("correctBtn")}
          </button>
          {editing ? (
            <>
              <p className="panel-sub">{vu("correctHint")}</p>
              {correctError ? <p role="alert" className="muted">{correctError}</p> : null}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  void submitCorrection("transcript", {
                    transcript: String(data.get("transcript") ?? ""),
                  });
                }}
              >
                <div className="field" style={{ marginTop: 8 }}>
                  <label htmlFor="vu-correct-transcript">{vu("transcriptEditLabel")}</label>
                  <textarea
                    id="vu-correct-transcript" name="transcript" rows={3}
                    defaultValue={analysis.transcript || ""}
                  />
                </div>
                <div className="chip-row" style={{ marginTop: 8 }}>
                  <LoadingButton
                    type="submit" className="btn-outline"
                    loading={busy === "transcript"}
                    loadingLabel={vu("savingLabel")}
                    disabled={busy !== null}
                  >
                    {vu("saveCorrectionBtn")}
                  </LoadingButton>
                </div>
              </form>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  const conf = Number(data.get("hook_confidence"));
                  void submitCorrection("hook", {
                    hook_type: String(data.get("hook_type") || hookType),
                    hook_confidence: Number.isFinite(conf) ? conf : hookConf,
                  });
                }}
              >
                <div className="detail-cols-2" style={{ marginTop: 8 }}>
                  <div className="field">
                    <label htmlFor="vu-correct-hook">{vu("hookTypeEditLabel")}</label>
                    <select id="vu-correct-hook" name="hook_type" defaultValue={hookType}>
                      {HOOK_TYPE_OPTIONS.map((h) => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="vu-correct-hook-conf">{vu("hookConfEditLabel")}</label>
                    <input
                      id="vu-correct-hook-conf" name="hook_confidence" type="number"
                      min={0} max={1} step={0.05} defaultValue={hookConf}
                    />
                  </div>
                </div>
                <div className="chip-row" style={{ marginTop: 8 }}>
                  <LoadingButton
                    type="submit" className="btn-outline"
                    loading={busy === "hook"}
                    loadingLabel={vu("savingLabel")}
                    disabled={busy !== null}
                  >
                    {vu("saveCorrectionBtn")}
                  </LoadingButton>
                </div>
              </form>
              {rawMoments.length ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const data = new FormData(e.currentTarget);
                    const frame_labels = rawMoments.map((f, i) => {
                      const t = Number(data.get(`moment-t-${i}`));
                      return {
                        t_sec: Number.isFinite(t) ? t : Number(f["t_sec"]),
                        label: String(data.get(`moment-label-${i}`) ?? f["label"] ?? ""),
                        brand_visible: Boolean(f["brand_visible"]),
                        product_visible: Boolean(f["product_visible"]),
                        logo_visible: Boolean(f["logo_visible"]),
                        text_overlay: typeof f["text_overlay"] === "string"
                          ? String(f["text_overlay"]) : "",
                        cta_visible: Boolean(f["cta_visible"]),
                        end_frame: Boolean(f["end_frame"]),
                      };
                    });
                    void submitCorrection("moments", { frame_labels });
                  }}
                >
                  <h4 className="panel-title" style={{ fontSize: 13, marginTop: 10 }}>
                    {vu("momentsTitle")}
                  </h4>
                  {rawMoments.map((f, i) => (
                    <div className="detail-cols-2" key={`correct-moment-${i}`} style={{ marginTop: 6 }}>
                      <div className="field">
                        <label htmlFor={`vu-moment-t-${i}`}>
                          {vu("momentTimeEditLabel", { n: i + 1 })}
                        </label>
                        <input
                          id={`vu-moment-t-${i}`} name={`moment-t-${i}`} type="number"
                          min={0} step={0.1} defaultValue={Number(f["t_sec"])}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor={`vu-moment-label-${i}`}>
                          {vu("momentLabelEditLabel", { n: i + 1 })}
                        </label>
                        <input
                          id={`vu-moment-label-${i}`} name={`moment-label-${i}`} type="text"
                          defaultValue={String(f["label"] ?? "")} maxLength={200}
                        />
                      </div>
                    </div>
                  ))}
                  <div className="chip-row" style={{ marginTop: 8 }}>
                    <LoadingButton
                      type="submit" className="btn-outline"
                      loading={busy === "moments"}
                      loadingLabel={vu("savingLabel")}
                      disabled={busy !== null}
                    >
                      {vu("saveCorrectionBtn")}
                    </LoadingButton>
                  </div>
                </form>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function VideoUploadPanel({ open, employeeId, onClose }: PanelProps) {
  const { t, locale } = useLocale();
  const vu = (key: string, vars?: Record<string, string | number>): string =>
    t(`dashboard.videoUpload.${key}`, vars);
  const [draft, setDraft] = useState<DraftView | null>(null);
  const [spec, setSpec] = useState<VideoUploadSpec>({});
  const [bootError, setBootError] = useState("");
  const [stage, setStage] = useState<UploadStage>("video");
  const [status, setStatus] = useState("");
  const [toast, setToast] = useState("");
  const [limits, setLimits] = useState<VideoLimits | null>(null);
  const [limitsError, setLimitsError] = useState("");
  // Stage A state
  const [creativeKey, setCreativeKey] = useState("");
  const [stagedName, setStagedName] = useState("");
  const [videoBusy, setVideoBusy] = useState(false);
  // Stage B state
  const [client, setClient] = useState("");
  const [campaign, setCampaign] = useState("");
  // Stage C state
  const [platform, setPlatform] = useState("meta");
  const [csvText, setCsvText] = useState("");
  const [xlsxB64, setXlsxB64] = useState("");
  const [datasetFile, setDatasetFile] = useState("");
  const [sheets, setSheets] = useState<string[]>([]);
  const [sheet, setSheet] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  // Stage D state
  const [method, setMethod] = useState<string>("manual");
  const [match, setMatch] = useState<DraftMatch | null>(null);
  const [matchBusy, setMatchBusy] = useState<"propose" | "confirm" | null>(null);
  const [rows, setRows] = useState<MatchSnapshot[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [rowsBusy, setRowsBusy] = useState(false);
  const [rowsError, setRowsError] = useState("");
  const [findings, setFindings] = useState<DraftAnalysis | null>(null);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [switchingDataset, setSwitchingDataset] = useState(false);
  const [customClient, setCustomClient] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const reviewVideoRef = useRef<HTMLVideoElement | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<Element | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const datasetInputRef = useRef<HTMLInputElement>(null);
  const stagedFileRef = useRef<File | null>(null);
  const draftRef = useRef<DraftView | null>(null);
  const specRef = useRef<VideoUploadSpec>({});
  draftRef.current = draft;
  specRef.current = spec;
  const meta = useCampaignMeta();

  const snapshots: MatchSnapshot[] = useMemo(() => parseSnapshots(match), [match]);
  /** Row ids backing propose/confirm: the explicit checkbox selection
   *  (default: every candidate row). Ids always come from the server's
   *  candidates listing for this draft's dataset version — never typed
   *  in, never cached across versions. */
  const knownRowIds: number[] = picked;

  /** Mirror a server match row into working state. */
  const applyServerMatch = (server: DraftMatch | null | undefined): void => {
    if (!server) {
      setMatch(null);
      return;
    }
    setMatch(server);
    if (server.method) setMethod(server.method);
    const rows = parseSnapshots(server);
    setSpec((prev) => ({
      ...prev,
      match: {
        method: server.method || "manual",
        adRowIds: rows.map((r) => r.id).filter((n) => Number.isInteger(n)),
        matchedCount: rows.length,
        confirmed: server.confirmed === 1,
      },
    }));
  };

  /** (Re)load matchable rows for the draft's dataset version. */
  const loadRows = async (draftId: string, selectAll: boolean): Promise<MatchSnapshot[]> => {
    setRowsBusy(true);
    setRowsError("");
    try {
      const res = await getCandidates(draftId);
      const listed = Array.isArray(res.candidates) ? res.candidates : [];
      setRows(listed);
      if (selectAll) {
        setPicked(listed.map((r) => r.id).filter((n) => Number.isInteger(n)));
      } else {
        setPicked((prev) => prev.filter((id) => listed.some((r) => r.id === id)));
      }
      return listed;
    } catch (e) {
      setRowsError(e instanceof Error ? e.message : String(e));
      setRows([]);
      setPicked([]);
      return [];
    } finally {
      setRowsBusy(false);
    }
  };

  /** Switch back to an already-imported dataset version. A version
   *  superseded by a later import may hold no rows: the server is
   *  the source of truth and the row count shown comes from it. */
  const switchDatasetVersion = async (version: string): Promise<void> => {
    const current = draftRef.current;
    if (!current || !version || switchingDataset) return;
    setSwitchingDataset(true);
    setStatus("");
    try {
      const updated = await patchDraft(current.id, { dataset_version: version });
      setDraft(updated);
      const row = (updated.datasets ?? []).find((d) => d.version === version);
      const listed = await loadRows(current.id, true);
      setSpec((prev) => ({
        ...prev,
        dataset: row
          ? {
            dataset_id: row.id, version: row.version, rows: listed.length,
            inserted: 0, updated: 0, quarantined: 0, filename: row.filename,
          }
          : undefined,
        match: undefined,
      }));
      setMatch(null);
      setStatus(vu("datasetSwitchedMsg", {
        filename: row?.filename || version, count: listed.length,
      }));
    } catch (e) {
      setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setSwitchingDataset(false);
    }
  };

  /** The stored analysis block behind the on-screen findings. */
  const findingsBlock = ((findings?.annotation ?? {}) as Record<string, unknown>)["analysis"] as
    Record<string, unknown> | undefined;

  /** Human corrections to the stored findings. The server applies
   *  them to the annotation (fresh revision, locked dimensions) and
   *  invalidates any prior review, so the screen reloads the analysis
   *  and the corrected content must be re-reviewed. */
  const runCorrection = async (corrections: DraftCorrections): Promise<void> => {
    const current = draftRef.current;
    if (!current) return;
    const res = await correctDraft(current.id, corrections);
    setDraft(res.draft);
    const reading = await getAnalysis(current.id).catch(() => null);
    if (reading) setFindings(reading);
    setToast(vu("correctDoneMsg"));
    setStatus(vu("correctDoneMsg"));
  };

  /** Version-bound human review of the findings on screen. */
  const runReview = async (version: string, revision: string): Promise<void> => {
    const current = draftRef.current;
    if (!current || !version || reviewBusy) return;
    setReviewBusy(true);
    try {
      const res = await reviewDraft(current.id, version, reviewNote.trim(), revision);
      setDraft(res.draft);
      setReviewNote("");
      setToast(vu("reviewedMsg"));
      setStatus(vu("reviewedMsg"));
    } catch (e) {
      setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setReviewBusy(false);
    }
  };

  const seekMoment = (t: number): void => {
    const video = reviewVideoRef.current;
    if (!video || !Number.isFinite(t)) return;
    try {
      video.currentTime = Math.max(0, t);
      void video.play().catch(() => undefined);
    } catch {
      /* seeking is best-effort */
    }
  };

  // Bootstrap the draft on open: reuse the requested draft, else the
  // pinned in-progress draft for this account, else create one — so a
  // new upload never orphans the draft the user was already filling.
  // A pin is reused only when it still exists, belongs to this
  // account, and is still in progress (finished drafts stay frozen).
  useEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement;
    let live = true;
    setDraft(null);
    setSpec({});
    setMatch(null);
    setStatus("");
    setBootError("");
    setCsvText("");
    setXlsxB64("");
    setDatasetFile("");
    setSheets([]);
    setSheet("");
    setRows([]);
    setPicked([]);
    setRowsError("");
    setFindings(null);
    stagedFileRef.current = null;
    setStagedName("");
    const boot = async () => {
      try {
        let existing = open.draftId ? await getDraft(open.draftId) : null;
        if (!existing && !open.draftId) {
          try {
            const pinned = window.localStorage.getItem(draftKey(employeeId));
            if (pinned) {
              const recovered = await getDraft(pinned);
              const resumable = recovered.owner_employee_id === employeeId
                && recovered.status !== "ready_for_review"
                && recovered.status !== "reviewed";
              existing = resumable ? recovered : null;
            }
          } catch {
            existing = null;
          }
          if (!existing) {
            try {
              window.localStorage.removeItem(draftKey(employeeId));
            } catch {
              /* recovery pin is best-effort */
            }
          }
        }
        const created = existing ?? await createDraft({});
        if (!live) return;
        try {
          window.localStorage.setItem(draftKey(employeeId), created.id);
        } catch {
          /* recovery pin is best-effort */
        }
        const next = specFromDraft(created);
        setDraft(created);
        setSpec(next);
        // Hydrate the server's match rows (proposed or confirmed) so a
        // reopened draft recovers without re-doing the match.
        const serverMatch = created.matches?.[0] ?? null;
        applyServerMatch(serverMatch);
        const serverIds = parseSnapshots(serverMatch)
          .map((r) => r.id).filter((n) => Number.isInteger(n));
        if (created.dataset_version) {
          await loadRows(created.id, !serverIds.length);
          if (!live) return;
          if (serverIds.length) setPicked(serverIds);
        }
        if (created.status === "ready_for_review" || created.status === "reviewed") {
          const reading = await getAnalysis(created.id).catch(() => null);
          if (live && reading) setFindings(reading);
        }
        setCreativeKey(next.creative_key || "");
        setClient(next.client || "");
        setCampaign(next.campaign || "");
        setPlatform(next.platform || "meta");
        setStage(open.stage ?? stageForSpec(next));
        if (open.file) {
          stagedFileRef.current = open.file;
          setStagedName(open.file.name);
          if (!next.creative_key) setCreativeKey(slugKey(open.file.name));
        }
      } catch (e) {
        if (live) setBootError(e instanceof Error ? e.message : String(e));
      }
    };
    void boot();
    getVideoLimits()
      .then((l) => live && setLimits(l))
      .catch((e: unknown) => {
        if (live) setLimitsError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, employeeId]);

  // Focus trap + Escape close; focus returns to the opener on unmount.
  useEffect(() => {
    if (!open) return;
    const card = cardRef.current;
    const focusables = (): HTMLElement[] => {
      if (!card) return [];
      const nodes = card.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      );
      return [...nodes].filter((el) => el.offsetParent !== null || el === document.activeElement);
    };
    const first = card?.querySelector<HTMLElement>("button");
    if (first) first.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose(true);
        return;
      }
      if (e.key !== "Tab" || !card) return;
      const items = focusables();
      if (!items.length) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault();
        lastItem.focus();
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      if (openerRef.current instanceof HTMLElement) openerRef.current.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  /** Persist the working spec. Any spec change clears confirmed matches
   *  server-side, so the local match is dropped unless the caller is
   *  saving the post-confirm state (no-op: callers never persist after
   *  confirm — the status-only Analyze patch preserves it). */
  const persistSpec = async (next: VideoUploadSpec, opts?: { silent?: boolean }): Promise<boolean> => {
    const current = draftRef.current;
    if (!current) return false;
    // The server clears confirmed matches on any spec change, so the
    // local mirror goes with it — otherwise the UI would offer Analyze
    // on a confirmation the server just dropped.
    const clean: VideoUploadSpec = { ...next, match: undefined };
    setSaving(true);
    try {
      const updated = await patchDraft(current.id, { spec: clean });
      setDraft(updated);
      setSpec({ ...(updated.spec ?? clean) });
      setMatch(null);
      if (!opts?.silent) {
        setToast(t("dashboard.videoUpload.savedMsg"));
        setStatus(t("dashboard.videoUpload.savedMsg"));
      }
      return true;
    } catch (e) {
      setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveDraft = async (): Promise<void> => {
    // A spec PATCH clears the server confirmation, so a confirmed match
    // is transparently re-confirmed on the unchanged record set instead
    // of being silently dropped by an explicit Save.
    const prior = match;
    const priorIds = parseSnapshots(prior)
      .map((r) => r.id).filter((n) => Number.isInteger(n));
    const priorKey = (specRef.current.creative_key || "").trim();
    const priorMethod = method;
    const ok = await persistSpec({ ...specRef.current });
    if (ok && prior?.confirmed === 1 && priorIds.length && priorKey) {
      const current = draftRef.current;
      if (!current) return;
      try {
        const restored = await confirmMatch(current.id, {
          creative_key: priorKey, method: priorMethod, ad_rowids: priorIds,
        });
        applyServerMatch(restored);
        setStatus(vu("savedMsg"));
      } catch (e) {
        setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
      }
    }
  };

  /** Creative-key edit writes through to the working spec and drops
   *  any confirmed/proposed match: the server binds confirmations to
   *  validated video keys, so a stale confirmation under the old key
   *  must never reach Analyze (same pattern as client/campaign). */
  const pickCreativeKey = (v: string): void => {
    setCreativeKey(v);
    const prevKey = (specRef.current.creative_key || "").trim();
    if (prevKey && v.trim() !== prevKey && match) {
      setMatch(null);
      setSpec((prev) => ({ ...prev, creative_key: v.trim() || undefined, match: undefined }));
      setStatus(vu("keyClearsMatchNote"));
    } else if (v.trim() !== prevKey) {
      setSpec((prev) => ({ ...prev, creative_key: v.trim() || undefined }));
    }
  };

  const stageFile = (file: File | null): void => {
    if (!file) return;
    if (!isVideoFile(file)) {
      setStatus(vu("wrongType"));
      return;
    }
    stagedFileRef.current = file;
    setStagedName(file.name);
    if (!creativeKey.trim()) setCreativeKey(slugKey(file.name));
    setStatus("");
  };

  const uploadStaged = async (): Promise<void> => {
    const file = stagedFileRef.current;
    const current = draftRef.current;
    const key = creativeKey.trim();
    if (!file || !current || !key) return;
    setVideoBusy(true);
    setStatus(vu("uploadingLabel"));
    try {
      const media = await uploadMedia(key, file);
      setStatus(vu("validatingLabel"));
      const verdict = await validateVideo(media.id, current.id);
      const next: VideoUploadSpec = {
        ...specRef.current,
        creative_key: key,
        media: {
          id: media.id, filename: media.filename || file.name,
          bytes: media.bytes ?? file.size, sha256: media.sha256 || "",
          url: media.url || `/media/${media.id}`,
        },
        video: {
          video_id: verdict.video_id,
          duration_s: verdict.duration_s ?? 0,
          width: verdict.width ?? 0,
          height: verdict.height ?? 0,
          status: verdict.validation?.status === "valid" ? "valid" : "invalid",
          reason: verdict.validation?.reason,
        },
        match: undefined,
      };
      stagedFileRef.current = null;
      setStagedName("");
      const updated = await patchDraft(current.id, { spec: next });
      setDraft(updated);
      setSpec({ ...(updated.spec ?? next) });
      setMatch(null);
      const video = (updated.spec ?? next).video;
      if (video?.status === "valid") {
        setStatus(vu("validMsg", {
          width: video.width, height: video.height,
          duration: Math.round(video.duration_s * 10) / 10,
        }));
      } else {
        setStatus(vu("invalidMsg", { reason: video?.reason || "unknown" }));
      }
    } catch (e) {
      setStatus(vu("uploadFailed", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setVideoBusy(false);
    }
  };

  const removeVideo = async (): Promise<void> => {
    // Explicit backend removal first: clearing the form alone would
    // leave the stored relationship, resurrecting the video on
    // reopen. Only then is the working spec cleared.
    const current = draftRef.current;
    if (current) {
      try {
        await deleteDraftVideos(current.id);
      } catch (e) {
        setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
        return;
      }
    }
    const next: VideoUploadSpec = { ...specRef.current, media: undefined, video: undefined, match: undefined };
    stagedFileRef.current = null;
    setStagedName("");
    setMatch(null);
    await persistSpec(next, { silent: true });
    setStatus("");
  };

  const confirmClientCampaign = async (): Promise<void> => {
    const c = client.trim();
    const camp = campaign.trim();
    if (!c || !camp) return;
    const next: VideoUploadSpec = {
      ...specRef.current, client: c, campaign: camp, clientConfirmed: true, match: undefined,
    };
    const ok = await persistSpec(next, { silent: true });
    if (ok) {
      setSpec({ ...next });
      setStatus(vu("confirmedMsg", { client: c, campaign: camp }));
    }
  };

  const pickClient = (v: string): void => {
    setClient(v);
    if (specRef.current.clientConfirmed) {
      const next: VideoUploadSpec = {
        ...specRef.current, client: v, clientConfirmed: false, match: undefined,
      };
      setSpec(next);
      setStatus(vu("clearsMatchNote"));
    }
  };

  const pickCampaign = (v: string): void => {
    setCampaign(v);
    if (specRef.current.clientConfirmed) {
      const next: VideoUploadSpec = {
        ...specRef.current, campaign: v, clientConfirmed: false, match: undefined,
      };
      setSpec(next);
      setStatus(vu("clearsMatchNote"));
    }
  };

  const datasetFilePicked = async (file: File | null): Promise<void> => {
    if (!file) return;
    setDatasetFile(file.name);
    setSheets([]);
    setSheet("");
    if (/\.xlsx$/i.test(file.name)) {
      try {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(new Error("read"));
          reader.readAsDataURL(file);
        });
        const b64 = dataUrl.includes(",") ? dataUrl.slice(dataUrl.indexOf(",") + 1) : dataUrl;
        setXlsxB64(b64);
        setCsvText("");
      } catch {
        setStatus(vu("errorGeneric", { error: file.name }));
      }
    } else {
      try {
        const text = await file.text();
        setCsvText(text);
        setXlsxB64("");
      } catch {
        setStatus(vu("errorGeneric", { error: file.name }));
      }
    }
  };

  const runImport = async (): Promise<void> => {
    const current = draftRef.current;
    const payload = xlsxB64
      ? { xlsx_b64: xlsxB64 }
      : { csv: csvText };
    if (!current || (!xlsxB64 && !csvText.trim())) return;
    setImportBusy(true);
    setStatus(vu("importingLabel"));
    try {
      const res = await importDataset({
        draft_id: current.id,
        platform: platform.trim() || "meta",
        filename: datasetFile || (xlsxB64 ? "upload.xlsx" : "upload.csv"),
        ...payload,
        ...(sheet ? { sheet } : {}),
      });
      const next: VideoUploadSpec = {
        ...specRef.current,
        platform: platform.trim() || "meta",
        dataset: {
          dataset_id: res.dataset_id, version: res.version, rows: res.rows,
          inserted: res.inserted, updated: res.updated,
          quarantined: res.quarantined, sheet: res.sheet || undefined,
          filename: datasetFile || "",
        },
        match: undefined,
      };
      const updated = await patchDraft(current.id, { spec: next });
      setDraft(updated);
      setSpec({ ...(updated.spec ?? next) });
      setMatch(null);
      // Fresh version, fresh row list: select everything by default.
      await loadRows(current.id, true);
      setSheets([]);
      const summary = vu("rowsSummary", {
        rows: res.rows, inserted: res.inserted, updated: res.updated,
      });
      setStatus(res.quarantined > 0
        ? `${summary} · ${vu("quarantinedNote", { count: res.quarantined })}`
        : summary);
    } catch (e) {
      if (e instanceof SheetConflictError) {
        setSheets(e.sheets);
        setStatus(vu("sheetConflict"));
      } else {
        setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
      }
    } finally {
      setImportBusy(false);
    }
  };

  const runPropose = async (): Promise<void> => {
    const current = draftRef.current;
    const key = (specRef.current.creative_key || "").trim();
    if (!current || !key || !knownRowIds.length || matchBusy) return;
    setMatchBusy("propose");
    setStatus(vu("proposingLabel"));
    try {
      const proposed = await proposeMatch(current.id, {
        creative_key: key, method, ad_rowids: knownRowIds,
      });
      applyServerMatch(proposed);
      const rows = parseSnapshots(proposed);
      setStatus(vu("matchedMsg", { count: rows.length, method: proposed.method || method }));
    } catch (e) {
      setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setMatchBusy(null);
    }
  };

  const runConfirm = async (): Promise<void> => {
    const current = draftRef.current;
    const key = (specRef.current.creative_key || "").trim();
    if (!current || !key || !knownRowIds.length || matchBusy) return;
    setMatchBusy("confirm");
    setStatus(vu("confirmingLabel"));
    try {
      const confirmed = await confirmMatch(current.id, {
        creative_key: key, method, ad_rowids: knownRowIds,
      });
      // Local mirror only: persisting spec here would clear the
      // just-made confirmation server-side (spec PATCH => clear_matches).
      applyServerMatch(confirmed);
      setStatus(vu("matchConfirmedMsg"));
    } catch (e) {
      setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setMatchBusy(null);
    }
  };

  const metaRows = meta.data?.campaigns ?? [];
  const metaClients = useMemo(
    () => [...new Set(metaRows.map((r) => (r.client || "").trim()).filter(Boolean))].sort(),
    [metaRows],
  );
  const metaCampaigns = useMemo(() => {
    const rows = client.trim()
      ? metaRows.filter((r) => (r.client || "").trim() === client.trim())
      : metaRows;
    return [...new Set(rows.map((r) => (r.name || "").trim()).filter(Boolean))].sort();
  }, [metaRows, client]);

  const videoValid = spec.video?.status === "valid";
  const matchConfirmed = (match?.confirmed === 1) || spec.match?.confirmed === true;
  const matchedCount = snapshots.length || spec.match?.matchedCount || 0;
  const matchedMethod = match?.method || spec.match?.method || method;
  const datasetVersion = spec.dataset?.version || draft?.dataset_version || "";
  /** Display rows: live server candidates when present, else the
   *  frozen snapshots of a proposed/confirmed match. */
  const candidates: DatasetCandidate[] = useMemo(() => {
    const source: MatchSnapshot[] = rows.length ? rows : snapshots;
    return source.map((s) => ({
      ad_name: s.ad_name || "", campaign: s.campaign || "", adset: s.adset || "",
      impressions: s.impressions != null ? String(s.impressions) : "",
      clicks: s.link_clicks != null ? String(s.link_clicks) : s.clicks != null ? String(s.clicks) : "",
      creative_key: s.creative_key || "",
    }));
  }, [rows, snapshots]);
  const canMatch = videoValid && Boolean(datasetVersion) && knownRowIds.length > 0;
  const grantConfirmed =
    spec.clientConfirmed && spec.client === client.trim() && spec.campaign === campaign.trim()
    && client.trim() !== "" && campaign.trim() !== "";
  // Guided order: video, then confirmed client/campaign destination,
  // then dataset match — the server binds in the same order.
  const canAnalyze = videoValid && grantConfirmed && matchConfirmed
    && draft?.status !== "queued" && draft?.status !== "analyzing";
  const analyzeReason = !videoValid
    ? vu("blockedNoVideo")
    : !grantConfirmed
      ? vu("blockedNoClient")
      : !matchConfirmed
        ? vu("blockedNoMatch")
        : draft?.status === "queued" || draft?.status === "analyzing"
          ? vu("queuedMsg")
          : "";
  const limitsText = limits
    ? vu("limitsNote", {
      containers: limits.containers.join(" / ").toUpperCase(),
      size: formatBytes(limits.max_bytes, locale),
      duration: limits.max_duration_s,
    })
    : limitsError
      ? vu("errorGeneric", { error: limitsError })
      : vu("limitsLoading");
  const warnings: string[] = [];
  if (!spec.clientConfirmed) warnings.push(vu("warnNoClient"));
  if (!spec.dataset) warnings.push(vu("warnNoDataset"));

  const clientCampaignConfirmed = grantConfirmed;

  const runAnalyze = async (): Promise<void> => {
    const current = draftRef.current;
    if (!current || !canAnalyze) return;
    setAnalyzing(true);
    setStatus(vu("analyzingLabel"));
    try {
      // The real Analyze contract: bind the immutable snapshot and
      // enqueue the worker job. 409 carries the honest reason
      // (preconditions, provider readiness, duplicate submit).
      const res = await analyzeDraft(current.id);
      setDraft({ ...current, status: res.status || "analyzing", live_job_id: res.job_id });
      try {
        window.localStorage.removeItem(draftKey(employeeId));
      } catch {
        /* ignore */
      }
      setToast(vu("queuedWithModel", { model: res.model || res.provider || "…" }));
      setStatus(vu("queuedMsg"));
      onClose(true);
    } catch (e) {
      setStatus(vu("errorGeneric", { error: e instanceof Error ? e.message : String(e) }));
    } finally {
      setAnalyzing(false);
    }
  };

  if (!open) return null;
  const stageIndex = STAGES.indexOf(stage);
  const stepName = (s: UploadStage): string =>
    s === "video" ? vu("stepVideo")
    : s === "client" ? vu("stepClient")
    : s === "dataset" ? vu("stepDataset")
    : vu("stepReview");

  return (
    <div className="modal-overlay" onClick={() => onClose(true)}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="vu-panel-title"
        ref={cardRef}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head panel-head dialog-head">
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <h2 className="panel-title" id="vu-panel-title">{vu("panelTitle")}</h2>
          </div>
          <button type="button" className="icon-btn" aria-label={vu("closeBtn")} onClick={() => onClose(true)}>
            <Icon name="x" size={18} />
          </button>
        </div>
        <ol className="chip-row vu-steps" aria-label={vu("stepsLabel")}
          style={{ listStyle: "none", margin: "0 0 14px", padding: 0 }}>
          {STAGES.map((s, i) => (
            <li key={s}>
              <span
                className="chip-static"
                aria-current={s === stage ? "step" : undefined}
                style={s === stage
                  ? { background: "var(--shell-teal)", color: "#fff", borderColor: "var(--shell-teal)" }
                  : undefined}
              >
                {`${i + 1}. ${stepName(s)}`}
              </span>
            </li>
          ))}
        </ol>
        <div role="status" aria-live="polite" className="panel-sub" style={{ minHeight: status ? undefined : 0 }}>
          {status || ""}
        </div>
        {bootError ? <p role="alert" className="muted">{vu("errorGeneric", { error: bootError })}</p> : null}
        {!draft && !bootError ? <div className="skel" style={{ height: 220 }} aria-hidden="true" /> : null}

        {draft && stage === "video" ? (
          <section aria-labelledby="vu-stage-video">
            <h3 id="vu-stage-video" className="panel-title" style={{ marginBottom: 10 }}>{vu("stageVideoTitle")}</h3>
            <p className="panel-sub" style={{ marginTop: 0 }}>{limitsText}</p>
            <div className="field" style={{ marginTop: 10 }}>
              <label htmlFor="vu-creative-key">{vu("creativeKeyLabel")}</label>
              <input
                id="vu-creative-key" type="text" value={creativeKey}
                onChange={(e) => pickCreativeKey(e.target.value)}
                placeholder="video-upload-sample"
              />
              <p className="panel-sub">{vu("creativeKeyHint")}</p>
            </div>
            <div className="field">
              <label htmlFor="vu-file">{vu("fileLabel")}</label>
              <input
                id="vu-file" ref={fileInputRef} type="file" accept="video/mp4,video/quicktime,.mp4,.mov"
                onChange={(e) => {
                  stageFile(e.target.files?.[0] ?? null);
                  e.target.value = "";
                }}
              />
            </div>
            {stagedName ? (
              <div className="chip-row" style={{ marginTop: 8 }}>
                <span className="chip-static">{stagedName}</span>
                <LoadingButton
                  type="button" className="btn-primary" loading={videoBusy}
                  loadingLabel={vu("uploadingLabel")} disabled={!creativeKey.trim()}
                  onClick={() => void uploadStaged()}
                >
                  {spec.media ? vu("replaceBtn") : vu("uploadButton")}
                </LoadingButton>
              </div>
            ) : null}
            {spec.media ? (
              <div className="vu-media" style={{ marginTop: 12 }}>
                <MediaPreview
                  src={spec.media.url}
                  creativeKey={spec.creative_key || creativeKey}
                  testId="vu-video-preview"
                />
                <dl className="detail-list" style={{ marginTop: 8 }}>
                  <div>
                    <dt>{vu("fileLabel")}</dt>
                    <dd>{spec.media.filename || stagedName || spec.creative_key}</dd>
                  </div>
                  <div>
                    <dt>{vu("durationLabel")}</dt>
                    <dd>{spec.video ? `${Math.round(spec.video.duration_s * 10) / 10}s` : "—"}</dd>
                  </div>
                  <div>
                    <dt>{vu("sizeLabel")}</dt>
                    <dd>{spec.media.bytes ? formatBytes(spec.media.bytes, locale) : "—"}</dd>
                  </div>
                </dl>
                <div className="chip-row" style={{ marginTop: 8 }}>
                  <button type="button" className="btn-outline" onClick={() => fileInputRef.current?.click()}>
                    {vu("replaceBtn")}
                  </button>
                  <button type="button" className="btn-outline" onClick={() => void removeVideo()}>
                    {vu("removeBtn")}
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {draft && stage === "client" ? (
          <section aria-labelledby="vu-stage-client">
            <h3 id="vu-stage-client" className="panel-title" style={{ marginBottom: 10 }}>{vu("stageClientTitle")}</h3>
            {meta.error ? <p className="muted">{vu("errorGeneric", { error: meta.error })}</p> : null}
            <div className="detail-cols-2">
              <MetaSelect
                id="vu-client" label={vu("clientLabel")} allLabel={vu("allLabel")}
                values={metaClients} value={client} onPick={pickClient}
              />
              <MetaSelect
                id="vu-campaign" label={vu("campaignLabel")} allLabel={vu("allLabel")}
                values={metaCampaigns} value={campaign} onPick={pickCampaign}
              />
            </div>
            <div className="chip-row" style={{ marginTop: 10 }}>
              <LoadingButton
                type="button" className="btn-primary" loading={saving}
                loadingLabel={vu("savingLabel")} disabled={!client.trim() || !campaign.trim()}
                onClick={() => void confirmClientCampaign()}
              >
                {vu("confirmSelectionBtn")}
              </LoadingButton>
              {clientCampaignConfirmed ? (
                <span className="pill pill-ok">
                  <Icon name="check" size={14} />
                  {vu("confirmedMsg", { client: client.trim(), campaign: campaign.trim() })}
                </span>
              ) : null}
            </div>
            <p className="panel-sub">{vu("clearsMatchNote")}</p>
            {!customClient ? (
              <p className="panel-sub">
                <button type="button" className="link-teal" onClick={() => setCustomClient(true)}>
                  {vu("customClientBtn")}
                </button>
              </p>
            ) : (
              <p className="panel-sub">
                <button type="button" className="link-teal" onClick={() => setCustomClient(false)}>
                  {vu("catalogueClientBtn")}
                </button>
              </p>
            )}
            {customClient ? (
              <div className="detail-cols-2" style={{ marginTop: 8 }}>
                <div className="field">
                  <label htmlFor="vu-client-custom">{vu("clientLabel")}</label>
                  <input
                    id="vu-client-custom" type="text" value={client}
                    onChange={(e) => pickClient(e.target.value)}
                    placeholder={vu("customClientPlaceholder")}
                  />
                </div>
                <div className="field">
                  <label htmlFor="vu-campaign-custom">{vu("campaignLabel")}</label>
                  <input
                    id="vu-campaign-custom" type="text" value={campaign}
                    onChange={(e) => pickCampaign(e.target.value)}
                    placeholder={vu("customCampaignPlaceholder")}
                  />
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {draft && stage === "dataset" ? (
          <section aria-labelledby="vu-stage-dataset">
            <h3 id="vu-stage-dataset" className="panel-title" style={{ marginBottom: 10 }}>{vu("stageDatasetTitle")}</h3>
            <div className="detail-cols-2">
              <div className="field">
                <label htmlFor="vu-platform">{vu("platformLabel")}</label>
                <select id="vu-platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>
                  <option value="meta">Meta</option>
                  <option value="tiktok">TikTok</option>
                </select>
              </div>
              <div className="field">
                <span className="field-label" aria-hidden="true">&nbsp;</span>
                <button type="button" className="btn-outline" onClick={() => datasetInputRef.current?.click()}>
                  <Icon name="download" size={15} /> {vu("fileBtn")}
                </button>
                <input
                  ref={datasetInputRef} type="file" accept=".csv,.xlsx,text/csv" hidden
                  aria-label={vu("fileBtn")}
                  onChange={(e) => {
                    void datasetFilePicked(e.target.files?.[0] ?? null);
                    e.target.value = "";
                  }}
                />
              </div>
            </div>
            <div className="field" style={{ marginTop: 10 }}>
              <label htmlFor="vu-csv">{vu("csvLabel")}</label>
              <textarea
                id="vu-csv" value={csvText} rows={6}
                placeholder={vu("csvPlaceholder")}
                onChange={(e) => { setCsvText(e.target.value); setXlsxB64(""); }}
              />
              {datasetFile ? <p className="panel-sub">{datasetFile}</p> : null}
            </div>
            {sheets.length ? (
              <div className="field">
                <label htmlFor="vu-sheet">{vu("sheetLabel")}</label>
                <select id="vu-sheet" value={sheet} onChange={(e) => setSheet(e.target.value)}>
                  <option value="">{vu("sheetPlaceholder")}</option>
                  {sheets.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            ) : null}
            <div className="chip-row" style={{ marginTop: 10 }}>
              <LoadingButton
                type="button" className="btn-primary" loading={importBusy}
                loadingLabel={vu("importingLabel")}
                disabled={(!xlsxB64 && !csvText.trim()) || (sheets.length > 0 && !sheet)}
                onClick={() => void runImport()}
              >
                {vu("importBtn")}
              </LoadingButton>
            </div>
            {(draft?.datasets ?? []).length > 1 ? (
              <div className="field" style={{ marginTop: 10 }}>
                <label htmlFor="vu-dataset-version">{vu("datasetVersionLabel")}</label>
                <select
                  id="vu-dataset-version"
                  value={spec.dataset?.version || draft?.dataset_version || ""}
                  disabled={switchingDataset}
                  onChange={(e) => void switchDatasetVersion(e.target.value)}
                >
                  {(draft?.datasets ?? []).map((d) => {
                    const active = d.version
                      === (spec.dataset?.version || draft?.dataset_version || "");
                    return (
                      <option key={d.id} value={d.version}>
                        {d.filename || d.version}{active ? " · current" : ""}
                      </option>
                    );
                  })}
                </select>
                <p className="panel-sub">{vu("datasetSwitchNote")}</p>
              </div>
            ) : null}
            {spec.dataset ? (
              <div style={{ marginTop: 10 }}>
                <p className="panel-sub" style={{ fontWeight: 700, color: "var(--shell-navy)" }}>
                  {vu("rowsSummary", {
                    rows: spec.dataset.rows, inserted: spec.dataset.inserted,
                    updated: spec.dataset.updated,
                  })}
                </p>
                {spec.dataset.quarantined > 0 ? (
                  <p className="panel-sub">{vu("quarantinedNote", { count: spec.dataset.quarantined })}</p>
                ) : null}
                {spec.dataset.sheet ? (
                  <p className="panel-sub">{vu("sheetLabel")}: {spec.dataset.sheet}</p>
                ) : null}
              </div>
            ) : (
              <p className="panel-sub">{vu("noDatasetNote")}</p>
            )}
          </section>
        ) : null}

        {draft && stage === "review" ? (
          <section aria-labelledby="vu-stage-review">
            <h3 id="vu-stage-review" className="panel-title" style={{ marginBottom: 10 }}>{vu("stageReviewTitle")}</h3>
            {spec.media ? (
              <MediaPreview
                src={spec.media.url}
                creativeKey={spec.creative_key || creativeKey}
                testId="vu-review-preview"
                videoRef={reviewVideoRef}
                mutedPreview
              />
            ) : null}
            <dl className="detail-list" style={{ marginTop: 8 }}>
              <div>
                <dt>{vu("clientLabel")} / {vu("campaignLabel")}</dt>
                <dd>
                  {spec.client || spec.campaign
                    ? `${spec.client || "—"} / ${spec.campaign || "—"}`
                    : "—"}
                  {spec.clientConfirmed ? "" : ` (${vu("warnNoClient")})`}
                </dd>
              </div>
              <div>
                <dt>{vu("creativeKeyLabel")}</dt>
                <dd>{spec.creative_key || creativeKey || "—"}</dd>
              </div>
              <div>
                <dt>{vu("candidatesTitle")}</dt>
                <dd>
                  {matchConfirmed || snapshots.length
                    ? vu("matchedMsg", { count: matchedCount, method: matchedMethod })
                    : vu("noMatchNote")}
                </dd>
              </div>
              <div>
                <dt>{vu("methodLabel")}</dt>
                <dd>{matchedMethod}</dd>
              </div>
            </dl>
            {warnings.length ? (
              <div style={{ marginTop: 10 }}>
                <h4 className="panel-title" style={{ fontSize: 13 }}>{vu("reviewWarningsTitle")}</h4>
                <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                  {warnings.map((w) => <li key={w} className="panel-sub">{w}</li>)}
                </ul>
              </div>
            ) : null}
            {rowsBusy ? (
              <p className="panel-sub">{vu("loadingRows")}</p>
            ) : rowsError ? (
              <p className="muted">{vu("errorGeneric", { error: rowsError })}</p>
            ) : candidates.length ? (
              <div style={{ marginTop: 10 }}>
                <h4 className="panel-title" style={{ fontSize: 13 }}>
                  {vu("candidatesTitle")} · {vu("candidatesCount", { count: candidates.length })}
                </h4>
                <p className="panel-sub">{vu("candidatesVisibleNote", { count: knownRowIds.length })}</p>
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        {rows.length ? (
                          <th scope="col">
                            <span className="sr-only">{vu("selectRowsLabel")}</span>
                          </th>
                        ) : null}
                        <th scope="col">{vu("campaignLabel")}</th>
                        <th scope="col">{vu("adLabel")}</th>
                        <th scope="col">{vu("impressionsLabel")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.map((c, i) => {
                        const id = (rows.length ? rows : snapshots)[i]?.id;
                        // Every default-selected id is rendered: no slice,
                        // so propose/confirm can never bind rows the user
                        // never saw. Rows without an id cannot be proposed
                        // and render unchecked, never silently selected.
                        const checked = id != null && knownRowIds.includes(id);
                        return (
                          <tr key={`${c.ad_name}-${i}`}>
                            {rows.length ? (
                              <td>
                                <input
                                  type="checkbox"
                                  aria-label={vu("selectRowLabel", {
                                    name: c.ad_name || c.creative_key || String(id ?? i),
                                  })}
                                  checked={checked}
                                  onChange={() => {
                                    if (id == null) return;
                                    // The Analyze gate binds the confirmed
                                    // set, not the checkboxes: changing the
                                    // selection after confirmation drops the
                                    // stale approval so the visible
                                    // selection can never disagree with it.
                                    if (match?.confirmed === 1) {
                                      setMatch(null);
                                      setSpec((prev) => ({ ...prev, match: undefined }));
                                      setStatus(vu("selectionClearsMatchNote"));
                                    }
                                    setPicked((prev) => checked
                                      ? prev.filter((n) => n !== id)
                                      : [...prev, id]);
                                  }}
                                />
                              </td>
                            ) : null}
                            <td>{c.campaign || "—"}</td>
                            <td>{c.ad_name || c.creative_key || "—"}</td>
                            <td>{c.impressions || c.clicks || "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
            {findings?.annotation ? (
              <FindingsView
                key={String(
                  ((findings.annotation as Record<string, unknown>)["analysis"] as
                    Record<string, unknown> | undefined)?.["revision"] ?? "norev",
                )}
                analysis={findings} vu={vu} onSeek={seekMoment}
                correction={{ onCorrect: runCorrection }}
              />
            ) : null}
            {draft?.status === "ready_for_review" && findings?.annotation ? (
              <div style={{ marginTop: 10 }}>
                <h4 className="panel-title" style={{ fontSize: 13 }}>{vu("reviewTitle")}</h4>
                <p className="panel-sub">
                  {vu("reviewVersionLabel", {
                    version: String(findingsBlock?.["version"] ?? "—"),
                  })}
                </p>
                {draft?.review?.by ? (
                  <p className="panel-sub">
                    {vu("reviewedByMsg", {
                      by: draft.review.by, at: draft.review.at,
                      version: draft.review.analysis_version,
                    })}
                    {draft.review.note ? ` — ${draft.review.note}` : ""}
                  </p>
                ) : (
                  <>
                    <div className="field" style={{ marginTop: 8 }}>
                      <label htmlFor="vu-review-note">{vu("reviewNoteLabel")}</label>
                      <input
                        id="vu-review-note" type="text" value={reviewNote}
                        onChange={(e) => setReviewNote(e.target.value)}
                        placeholder={vu("reviewNotePlaceholder")}
                      />
                    </div>
                    <div className="chip-row" style={{ marginTop: 8 }}>
                      <LoadingButton
                        type="button" className="btn-primary" loading={reviewBusy}
                        loadingLabel={vu("reviewingLabel")}
                        disabled={!String(findingsBlock?.["version"] ?? "")}
                        onClick={() => void runReview(
                          String(findingsBlock?.["version"] ?? ""),
                          String(findingsBlock?.["revision"] ?? ""))}
                      >
                        {vu("markReviewedBtn")}
                      </LoadingButton>
                    </div>
                  </>
                )}
              </div>
            ) : null}
            <div className="field" style={{ marginTop: 10, maxWidth: 320 }}>
              <label htmlFor="vu-method">{vu("methodLabel")}</label>
              <select id="vu-method" value={method} onChange={(e) => setMethod(e.target.value)}>
                {MATCH_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div className="chip-row" style={{ marginTop: 10 }}>
              <LoadingButton
                type="button" className="btn-outline" loading={matchBusy === "propose"}
                loadingLabel={vu("proposingLabel")} disabled={!canMatch || matchBusy !== null}
                onClick={() => void runPropose()}
              >
                {vu("proposeBtn")}
              </LoadingButton>
              <LoadingButton
                type="button" className="btn-outline" loading={matchBusy === "confirm"}
                loadingLabel={vu("confirmingLabel")} disabled={!canMatch || matchBusy !== null}
                onClick={() => void runConfirm()}
              >
                {vu("confirmMatchBtn")}
              </LoadingButton>
            </div>
            {!canMatch ? <p className="panel-sub">{vu("matchNeedsIds")}</p> : null}
          </section>
        ) : null}

        {draft ? (
          <div style={{
            display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
            marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--shell-line)",
          }}>
            <span style={{ flex: "1 1 auto" }} />
            {stageIndex > 0 ? (
              <button type="button" className="btn-outline" onClick={() => setStage(STAGES[stageIndex - 1])}>
                {vu("backBtn")}
              </button>
            ) : null}
            <LoadingButton
              type="button" className="btn-outline" loading={saving}
              loadingLabel={vu("savingLabel")} onClick={() => void saveDraft()}
            >
              {vu("saveDraftBtn")}
            </LoadingButton>
            {stageIndex < STAGES.length - 1 ? (
              <button type="button" className="btn-primary" onClick={() => setStage(STAGES[stageIndex + 1])}>
                {vu("continueStepBtn")}
              </button>
            ) : (
              <span style={{ display: "inline-flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
                <LoadingButton
                  type="button" className="btn-primary" loading={analyzing}
                  loadingLabel={vu("analyzingLabel")} disabled={!canAnalyze}
                  onClick={() => void runAnalyze()}
                >
                  {vu("analyzeBtn")}
                </LoadingButton>
                {!canAnalyze && analyzeReason ? (
                  <span className="panel-sub" role="note">{analyzeReason}</span>
                ) : null}
              </span>
            )}
          </div>
        ) : null}
        {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      </div>
    </div>
  );
}
