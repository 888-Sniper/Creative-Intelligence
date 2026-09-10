import type { Gate } from "@/types/auth";

export class ApiError extends Error {
  gate: Gate | "";
  status: number;
  constructor(message: string, status: number, gate: Gate | "" = "") {
    super(message);
    this.status = status;
    this.gate = gate;
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
    throw new ApiError(message, res.status, gate);
  }
  return body as T;
}

/** Same-origin JSON API client. Auth rides the HttpOnly session cookie;
 *  the raw token is never exposed to JavaScript (item 9). */
export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parse<T>(res);
}

/** Append the shared top-filter-bar scope to scoped analytics endpoints,
 *  mirroring the legacy filtered_path() behaviour. */
export function scopedPath(path: string, scope: URLSearchParams): string {
  const isScoped =
    path === "/api/campaigns" ||
    path.startsWith("/api/benchmarks") ||
    path === "/api/creatives" ||
    path.startsWith("/api/compare") ||
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
