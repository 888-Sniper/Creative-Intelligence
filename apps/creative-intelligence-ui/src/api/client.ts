import type { Gate } from "@/types/auth";

export class ApiError extends Error {
  gate: Gate | "";
  status: number;
  /** Parsed error envelope (for structured errors like sheet lists). */
  body?: Record<string, unknown>;
  constructor(message: string, status: number, gate: Gate | "" = "",
              body?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.gate = gate;
    this.body = body;
  }
}

type GateHandler = (gate: Gate) => void;

let gateHandler: GateHandler | null = null;

/** AuthProvider registers a re-gate callback so a mid-session 401/403 with
 *  a gate envelope (revoke/suspend elsewhere) returns the app to the right
 *  screen instead of stranding it on stale data (legacy boot() parity). */
export function setGateHandler(fn: GateHandler | null): void {
  gateHandler = fn;
}

async function parse<T>(res: Response): Promise<T> {
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const detail = body["detail"];
    const err =
      typeof detail === "object" && detail !== null
        ? (detail as Record<string, unknown>)
        : body;
    const message =
      typeof err["error"] === "string" ? err["error"] : `Request failed (${res.status})`;
    const gate =
      typeof err["gate"] === "string" ? (err["gate"] as Gate) : "";
    if (gate === "login" || gate === "pending" || gate === "suspended" || gate === "revoked") {
      gateHandler?.(gate);
    }
    if (res.status === 401 && !gate) gateHandler?.("login");
    throw new ApiError(message, res.status, gate, body);
  }
  return body as T;
}

export interface ApiOptions {
  /** Bound the request: abort it after this many milliseconds so a
   *  stalled call surfaces as a failure (retryable) instead of
   *  hanging its loading state forever (§11). */
  timeoutMs?: number;
  /** Caller cancellation (unmount, superseded request). */
  signal?: AbortSignal;
}

/** Same-origin JSON API client. Auth rides the HttpOnly session cookie;
 *  the raw token is never exposed to JavaScript (item 9). */
export async function api<T>(method: string, path: string, body?: unknown, opts?: ApiOptions): Promise<T> {
  // Honor an already-aborted caller signal instead of issuing a request
  // whose result can never be consumed.
  if (opts?.signal?.aborted) {
    throw new DOMException(`Request aborted (${path})`, "AbortError");
  }
  const ctrl = new AbortController();
  const forward = () => ctrl.abort();
  opts?.signal?.addEventListener("abort", forward);
  // A timeout rejects the race even when the underlying fetch never
  // settles or ignores the abort signal (unit-test doubles); the
  // abort still releases a real in-flight request, and the extra
  // catch keeps its late rejection handled.
  let timer: ReturnType<typeof window.setTimeout> | null = null;
  let onTimeout = () => {};
  const timeout = new Promise<never>((_, reject) => {
    onTimeout = () => {
      ctrl.abort();
      reject(new Error(`Request timed out (${path})`));
    };
  });
  // The timeout covers the whole fetch-and-parse operation: fetch()
  // can resolve on response headers while the JSON body is still
  // streaming, so racing headers alone can leave parsing (and the
  // caller's loading state) pending forever.
  const run = async (): Promise<T> => {
    const req = fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
    void req.catch(() => {});
    const res = await req;
    return parse<T>(res);
  };
  try {
    if (opts?.timeoutMs && opts.timeoutMs > 0) {
      timer = window.setTimeout(onTimeout, opts.timeoutMs);
    }
    return timer ? await Promise.race([run(), timeout]) : await run();
  } finally {
    if (timer !== null) window.clearTimeout(timer);
    opts?.signal?.removeEventListener("abort", forward);
  }
}

/** Download a file through the same session/gate handling as api().
 *  Raw fetch() downloads used to save 401 error JSON as the file and
 *  never re-gated an expired session; this parses errors first and
 *  only returns a Blob for a real 2xx attachment. */
export async function apiBlob(method: string, path: string, body?: unknown): Promise<Blob> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const parsed = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const detail = parsed["detail"];
    const err = typeof detail === "object" && detail !== null ? (detail as Record<string, unknown>) : parsed;
    const gate = typeof err["gate"] === "string" ? (err["gate"] as Gate) : "";
    if (gate === "login" || gate === "pending" || gate === "suspended" || gate === "revoked") {
      gateHandler?.(gate);
    }
    if (res.status === 401 && !gate) gateHandler?.("login");
    throw new ApiError(typeof err["error"] === "string" ? err["error"] : `Request failed (${res.status})`, res.status, gate);
  }
  return res.blob();
}

/** Multipart upload with the same session/gate handling as api():
 *  an expired session re-gates instead of surfacing a bare 401, and
 *  error JSON is parsed rather than trusted blindly. */
export async function apiForm<T>(method: string, path: string, form: FormData): Promise<T> {
  const res = await fetch(path, { method, body: form });
  const raw = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  const data = (raw["detail"] && typeof raw["detail"] === "object"
    ? (raw["detail"] as Record<string, unknown>) : raw) as Record<string, unknown>;
  if (!res.ok) {
    const gate = typeof data["gate"] === "string" ? (data["gate"] as Gate) : "";
    if (gate === "login" || gate === "pending" || gate === "suspended" || gate === "revoked") {
      gateHandler?.(gate);
    }
    if (res.status === 401 && !gate) gateHandler?.("login");
    throw new ApiError(typeof data["error"] === "string" ? data["error"] : `Request failed (${res.status})`, res.status, gate);
  }
  return data as T;
}

/** Append the shared top-filter-bar scope to scoped analytics endpoints,
 *  mirroring the legacy filtered_path() behaviour. */
export function scopedPath(path: string, scope: URLSearchParams): string {
  // Exact static paths only. A campaign named meta-launch must still
  // receive the shared filters; a prefix check treats it as metadata.
  const bare = path.split("?", 1)[0];
  const isCampaignDetail =
    bare.startsWith("/api/campaigns/") &&
    bare !== "/api/campaigns/meta" &&
    bare !== "/api/campaigns/recommendations";
  const isScoped =
    path === "/api/campaigns" ||
    isCampaignDetail ||
    path.startsWith("/api/benchmarks") ||
    path === "/api/creatives" ||
    path.startsWith("/api/compare") ||
    path.startsWith("/api/kpis/") ||
    path.startsWith("/api/retention/patterns") ||
    path.startsWith("/api/analyst/creatives") ||
    path.startsWith("/api/campaigns/recommendations");
  if (!isScoped) return path;
  const [base, query] = path.split("?", 2);
  const params = new URLSearchParams(query ?? "");
  if (path.startsWith("/api/compare/campaigns")) {
    for (const [k, v] of scope) {
      if (k === "campaign" || k === "campaigns") continue;
      if (!params.has(k)) params.set(k, v);
    }
    return params.toString() ? `${base}?${params}` : base;
  }
  if (path.startsWith("/api/compare/periods")) {
    for (const [k, v] of scope) {
      if (k === "date" || k === "date_from" || k === "date_to") continue;
      if (!params.has(k)) params.set(k, v);
    }
    return params.toString() ? `${base}?${params}` : base;
  }
  for (const [k, v] of scope) {
    if (!params.has(k)) params.set(k, v);
  }
  return params.toString() ? `${base}?${params}` : base;
}
