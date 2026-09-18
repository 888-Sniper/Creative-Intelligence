import { api } from "@/api/client";

/** Backend errors arrive top-level ({error, ...}) via the app's
 *  HTTPException handler — never under a {"detail"} envelope. Read
 *  top-level first, tolerate the envelope for robustness. */
export function errorMessage(body: unknown, fallback: string): string {
  const top = (body ?? {}) as Record<string, unknown>;
  const detail = top["detail"];
  const src = (typeof detail === "object" && detail !== null
    ? (detail as Record<string, unknown>) : top);
  return typeof src["error"] === "string" ? String(src["error"]) : fallback;
}

function errorSheets(body: unknown): string[] | null {
  const top = (body ?? {}) as Record<string, unknown>;
  const detail = top["detail"];
  const src = (typeof detail === "object" && detail !== null
    ? (detail as Record<string, unknown>) : top);
  const sheets = src["sheets"];
  return Array.isArray(sheets) ? sheets.map(String) : null;
}

/* Dashboard Video Upload — typed client for the guided-flow routes.
 * Shapes mirror the BACKEND (Backend/ci_backend/routers/product.py +
 * creative_intel/drafts.py), which differs from the frozen contracts
 * doc in several places; each divergence is noted where it matters.
 * No backend routes are added or changed from here. */

export const DRAFT_KEY_PREFIX = "ci-video-draft:";

export function draftKey(employeeId: string): string {
  return `${DRAFT_KEY_PREFIX}${employeeId || ""}`;
}

export interface MediaRecord {
  id: number;
  creative_key: string;
  filename: string;
  mime: string;
  bytes: number;
  sha256: string;
  created_at: string;
  url: string;
  width?: number;
  height?: number;
}

/** Multipart upload: bytes ride outside JSON (the api() helper is
 *  JSON-only), mirroring the Campaigns export fetch style. */
export async function uploadMedia(creativeKey: string, file: File): Promise<MediaRecord> {
  const form = new FormData();
  form.append("creative_key", creativeKey);
  form.append("file", file, file.name);
  const res = await fetch("/api/media/upload", {
    method: "POST",
    credentials: "same-origin",
    body: form,
  });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(errorMessage(body, `Upload failed (${res.status})`));
  }
  return body as unknown as MediaRecord;
}

export interface VideoLimits {
  containers: string[];
  max_bytes: number;
  max_duration_s: number;
  note: string;
}

export function getVideoLimits(): Promise<VideoLimits> {
  return api<VideoLimits>("GET", "/api/videos/limits");
}

export interface VideoVerdict {
  status: "valid" | "invalid";
  reason?: string;
  duration_s: number;
  width: number;
  height: number;
  video_codec?: string;
  has_audio?: boolean;
  rotation?: number;
  bytes?: number;
  container?: string;
}

/** Backend key is `validation` (not `validation_json`); a video row is
 *  only stored (non-empty video_id) when the verdict is valid. */
export interface VideoValidateResp {
  video_id: string;
  media_id: number;
  creative_key: string;
  duration_s: number;
  width: number;
  height: number;
  validation: VideoVerdict;
}

export function validateVideo(mediaId: number, draftId?: string): Promise<VideoValidateResp> {
  return api<VideoValidateResp>("POST", "/api/videos/validate", {
    media_id: mediaId,
    ...(draftId ? { draft_id: draftId } : {}),
  });
}

/** Free-form draft working state. The create/patch handlers persist
 *  ONLY draft_id + spec (media_id/dataset_id top-level fields are
 *  accepted by the schema but ignored), so everything the panel needs
 *  across reloads rides here. */
export interface DatasetCandidate {
  ad_name: string;
  campaign: string;
  adset: string;
  impressions: string;
  clicks: string;
  creative_key: string;
}

export interface VideoUploadSpec {
  client?: string;
  campaign?: string;
  clientConfirmed?: boolean;
  creative_key?: string;
  platform?: string;
  media?: { id: number; filename: string; bytes: number; sha256: string; url: string };
  video?: {
    video_id: string; duration_s: number; width: number; height: number;
    status: "valid" | "invalid"; reason?: string;
  };
  dataset?: {
    dataset_id: string; version: string; rows: number; inserted: number;
    updated: number; quarantined: number; sheet?: string; filename: string;
    candidates?: DatasetCandidate[];
  };
  match?: { method: string; adRowIds: number[]; matchedCount: number; confirmed: boolean };
}

export interface DraftVideoRow {
  id: string;
  draft_id: string;
  creative_key: string;
  media_id: number;
  duration_s: number;
  width: number;
  height: number;
  sha256: string;
  validation_json: string;
  created_at: string;
}

export interface DraftDatasetRow {
  id: string;
  draft_id: string;
  filename: string;
  rows: number;
  version: string;
  sha256: string;
  created_at: string;
}

/** GET /api/drafts/{id} returns {draft: view} with parsed spec plus
 *  videos[]/datasets[]/matches[] and the live job id ("" when none). */
export interface DraftView {
  id: string;
  owner_employee_id: string;
  status: string;
  dataset_version: string;
  created_at: string;
  updated_at: string;
  spec: VideoUploadSpec;
  videos: DraftVideoRow[];
  datasets: DraftDatasetRow[];
  matches: DraftMatch[];
  live_job_id: string;
  review?: DraftReview | null;
}

export function createDraft(spec: VideoUploadSpec = {}, draftId?: string): Promise<DraftView> {
  return api<{ draft: DraftView }>("POST", "/api/drafts", {
    ...(draftId ? { draft_id: draftId } : {}),
    spec,
  }).then((r) => r.draft);
}

export function getDraft(draftId: string): Promise<DraftView> {
  return api<{ draft: DraftView }>("GET", `/api/drafts/${encodeURIComponent(draftId)}`)
    .then((r) => r.draft);
}

export function listDrafts(): Promise<DraftView[]> {
  return api<{ drafts: DraftView[] }>("GET", "/api/drafts").then((r) => r.drafts ?? []);
}

/** Matchable performance rows for the draft's dataset version —
 *  the only honest source of row ids for propose/confirm. */
export function getCandidates(draftId: string): Promise<{ candidates: MatchSnapshot[]; version: string }> {
  return api<{ candidates: MatchSnapshot[]; version: string }>(
    "GET", `/api/drafts/${encodeURIComponent(draftId)}/candidates`,
  );
}

export interface AnalyzeResp {
  job_id: string;
  status: string;
  draft_id: string;
  model: string;
  provider: string;
  sends: string;
  storage: string;
  poll: string;
}

/** Binds the immutable snapshot and enqueues the analysis job.
 *  Throws ApiError with the server's honest reason (preconditions,
 *  provider readiness, duplicate submit) on 409. */
export function analyzeDraft(draftId: string, brandTerms: string[] = []): Promise<AnalyzeResp> {
  return api<AnalyzeResp>(
    "POST", `/api/drafts/${encodeURIComponent(draftId)}/analyze`,
    { brand_terms: brandTerms },
  );
}

export function cancelAnalysisJob(jobId: string): Promise<void> {
  return api<{ job_id: string; status: string }>(
    "POST", `/api/pipeline/jobs/${encodeURIComponent(jobId)}/cancel`,
  ).then(() => undefined);
}

export interface DraftAnalysis {
  draft_id: string;
  status: string;
  creative_key: string;
  annotation: Record<string, unknown> | null;
  transcript: string;
}

export function getAnalysis(draftId: string): Promise<DraftAnalysis> {
  return api<DraftAnalysis>(
    "GET", `/api/drafts/${encodeURIComponent(draftId)}/analysis`,
  );
}

/** Patching spec (or dataset_version) clears confirmed matches
 *  server-side; a status-only patch (Analyze) preserves them. */
export function patchDraft(
  draftId: string,
  patch: { status?: string; spec?: VideoUploadSpec; dataset_version?: string },
): Promise<DraftView> {
  return api<{ draft: DraftView }>(
    "PATCH", `/api/drafts/${encodeURIComponent(draftId)}`, patch,
  ).then((r) => r.draft);
}

export function deleteDraft(draftId: string): Promise<void> {
  return api<{ ok: boolean }>(
    "DELETE", `/api/drafts/${encodeURIComponent(draftId)}`,
  ).then(() => undefined);
}

/** Explicit video removal: drops the draft's bound video row(s)
 *  server-side so a removed video cannot resurrect on reopen. */
export function deleteDraftVideos(draftId: string): Promise<number> {
  return api<{ ok: boolean; removed: number }>(
    "DELETE", `/api/drafts/${encodeURIComponent(draftId)}/videos`,
  ).then((r) => r.removed ?? 0);
}

export interface DraftReview {
  by: string;
  at: string;
  analysis_version: string;
  note: string;
}

/** Version-bound human review: approves exactly the analysis
 *  version the reviewer saw (reviewer + timestamp recorded). */
export function reviewDraft(
  draftId: string, analysisVersion: string, note = "",
): Promise<{ draft: DraftView; review: DraftReview }> {
  return api<{ draft: DraftView; review: DraftReview }>(
    "POST", `/api/drafts/${encodeURIComponent(draftId)}/review`,
    { analysis_version: analysisVersion, note },
  );
}

export interface DatasetImportResp {
  dataset_id: string;
  draft_id: string;
  rows: number;
  version: string;
  inserted: number;
  updated: number;
  quarantined: number;
  quarantine: Array<{ source_row?: number; reason?: string }>;
  sheet: string;
  sheets: string[];
}

/** A multi-sheet workbook without an explicit sheet rejects with 409
 *  plus a `sheets` catalogue — but the JSON api() helper drops that
 *  catalogue, so import goes over raw fetch to preserve it. */
export class SheetConflictError extends Error {
  sheets: string[];
  constructor(sheets: string[]) {
    super("sheet-conflict");
    this.name = "SheetConflictError";
    this.sheets = sheets;
  }
}

/** Platform is REQUIRED server-side. */
export async function importDataset(body: {
  draft_id: string; platform: string; filename?: string;
  csv?: string; xlsx_b64?: string; sheet?: string | number;
}): Promise<DatasetImportResp> {
  const res = await fetch("/api/datasets/import", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const sheets = errorSheets(data);
    if (sheets) {
      throw new SheetConflictError(sheets);
    }
    throw new Error(errorMessage(data, `Import failed (${res.status})`));
  }
  return data as unknown as DatasetImportResp;
}

export interface DraftMatch {
  draft_id: string;
  creative_key: string;
  method: string;
  record_json: string;
  confirmed: 0 | 1;
  confirmed_by: string;
  confirmed_at: string;
}

/** Frozen ad snapshots carried by a match response (each has the
 *  server-side row `id` plus display fields). */
export interface MatchSnapshot {
  id: number;
  import_id?: string;
  platform?: string;
  campaign?: string;
  adset?: string;
  ad_name?: string;
  creative_key?: string;
  spend?: number;
  impressions?: number;
  clicks?: number;
  link_clicks?: number;
  conversions?: number;
}

export function parseSnapshots(match: DraftMatch | null): MatchSnapshot[] {
  if (!match?.record_json) return [];
  try {
    const rows = JSON.parse(match.record_json) as unknown;
    return Array.isArray(rows) ? (rows as MatchSnapshot[]) : [];
  } catch {
    return [];
  }
}

export function proposeMatch(
  draftId: string, body: { creative_key: string; method: string; ad_rowids: number[] },
): Promise<DraftMatch> {
  return api<{ match: DraftMatch }>(
    "POST", `/api/drafts/${encodeURIComponent(draftId)}/matches/propose`, body,
  ).then((r) => r.match);
}

/** Confirm requires a VALID video on the draft (409 otherwise) and
 *  row ids from THIS draft's dataset version. */
export function confirmMatch(
  draftId: string, body: { creative_key: string; method: string; ad_rowids: number[] },
): Promise<DraftMatch> {
  return api<{ match: DraftMatch }>(
    "POST", `/api/drafts/${encodeURIComponent(draftId)}/matches/confirm`, body,
  ).then((r) => r.match);
}

export const MATCH_METHODS = [
  "platform_id",
  "exact_filename",
  "explicit_tag",
  "fuzzy_filename",
  "manual",
] as const;

/* Minimal CSV read for candidate display: split rows the way the
 * import pipeline maps them (header aliases for the display columns).
 * Quoted commas/quotes handled; the server remains the parser of
 * record — this only renders the user's own payload back. */
function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          quoted = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      cells.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  cells.push(cur);
  return cells.map((c) => c.trim());
}

const HEADER_ALIASES: Record<keyof DatasetCandidate, string[]> = {
  ad_name: ["ad", "ad name", "reklama", "nazwa reklamy"],
  campaign: ["campaign", "campaign name", "kampania", "nazwa kampanii"],
  adset: ["ad set", "ad set name", "zestaw reklam"],
  impressions: ["impressions", "wyświetlenia"],
  clicks: ["link clicks", "clicks", "kliknięcia"],
  creative_key: ["creative", "creative key", "creative name", "kreacja", "nazwa kreacji"],
};

function pickIndex(header: string[], keys: string[]): number {
  const norm = header.map((h) => h.toLowerCase().trim());
  for (const k of keys) {
    const i = norm.indexOf(k);
    if (i >= 0) return i;
  }
  return -1;
}

export function parseCsvCandidates(csv: string, limit = 200): DatasetCandidate[] {
  const lines = csv.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length < 2) return [];
  const header = splitCsvLine(lines[0]);
  const idx = {
    ad_name: pickIndex(header, HEADER_ALIASES.ad_name),
    campaign: pickIndex(header, HEADER_ALIASES.campaign),
    adset: pickIndex(header, HEADER_ALIASES.adset),
    impressions: pickIndex(header, HEADER_ALIASES.impressions),
    clicks: pickIndex(header, HEADER_ALIASES.clicks),
    creative_key: pickIndex(header, HEADER_ALIASES.creative_key),
  };
  const cell = (cells: string[], i: number): string => (i >= 0 && i < cells.length ? cells[i] : "");
  return lines.slice(1, 1 + limit).map((line) => {
    const cells = splitCsvLine(line);
    return {
      ad_name: cell(cells, idx.ad_name),
      campaign: cell(cells, idx.campaign),
      adset: cell(cells, idx.adset),
      impressions: cell(cells, idx.impressions),
      clicks: cell(cells, idx.clicks),
      creative_key: cell(cells, idx.creative_key),
    };
  });
}

export function formatBytes(bytes: number, locale = "en"): string {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u++;
  }
  try {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(v)} ${units[u]}`;
  } catch {
    return `${v.toFixed(1)} ${units[u]}`;
  }
}
