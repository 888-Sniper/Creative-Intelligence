import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/api/client";

interface JobRun {
  last_run_at: string;
  last_finished_at: string;
  last_status: string;
  last_inserted: number;
  last_updated: number;
  last_error: string;
}

interface SyncJob {
  id: string;
  source: string;
  name: string;
  params: Record<string, unknown>;
  owner_employee_id: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_run: JobRun | null;
}

const SOURCES = ["meta", "tiktok", "sheets", "drive"] as const;

/** Mask secret-shaped param values in read-only display (item 26: safe
 *  handling for account tokens). Editing replaces the whole params
 *  document, so masked values are never round-tripped. */
export function displayParams(params: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    out[k] = /token|secret|key|password/i.test(k) ? "•••" : v;
  }
  return out;
}

function runSummary(run: JobRun | null): string {
  if (!run) return "never run";
  const when = run.last_finished_at || run.last_run_at || "—";
  if (run.last_status === "ok") {
    return `ok @ ${when} (+${run.last_inserted}/~${run.last_updated})`;
  }
  return `${run.last_status} @ ${when}${run.last_error ? `: ${run.last_error}` : ""}`;
}

/** Scheduled sync-job administration (item 26): list, create, enable,
 *  disable, run now, edit, delete, last-run history and owner. */
export function SyncJobs() {
  const [jobs, setJobs] = useState<SyncJob[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [source, setSource] = useState<string>("meta");
  const [name, setName] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editParams, setEditParams] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api<{ jobs: SyncJob[] }>("GET", "/api/sync/jobs");
      setJobs(res.jobs);
      setError("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load sync jobs.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const parseParams = (text: string): Record<string, unknown> => {
    const value: unknown = JSON.parse(text) as unknown;
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error("Params must be a JSON object.");
    }
    return value as Record<string, unknown>;
  };

  const create = async () => {
    setError("");
    setNotice("");
    let params: Record<string, unknown>;
    try {
      params = parseParams(paramsText);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid params.");
      return;
    }
    try {
      await api("POST", "/api/sync/jobs", { source, name, params });
      setName("");
      setParamsText("{}");
      setNotice("Job created.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create job.");
    }
  };

  const toggle = async (job: SyncJob) => {
    setError("");
    try {
      await api("PATCH", `/api/sync/jobs/${encodeURIComponent(job.id)}`, { enabled: !job.enabled });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update job.");
    }
  };

  const runNow = async (job: SyncJob) => {
    setError("");
    setNotice("");
    try {
      const res = await api<{ inserted?: number; updated?: number }>(
        "POST", `/api/sync/jobs/${encodeURIComponent(job.id)}/run`, {});
      setNotice(`Run finished (+${res.inserted ?? 0}/~${res.updated ?? 0}).`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Run failed.");
    }
  };

  const remove = async (job: SyncJob) => {
    setError("");
    if (!window.confirm(`Delete sync job "${job.name}"? Scheduled runs stop immediately; already-imported rows stay.`)) {
      return;
    }
    try {
      await api("DELETE", `/api/sync/jobs/${encodeURIComponent(job.id)}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete job.");
    }
  };

  const startEdit = (job: SyncJob) => {
    setEditing(job.id);
    setEditName(job.name);
    setEditParams(JSON.stringify(job.params, null, 2));
  };

  const saveEdit = async (job: SyncJob) => {
    setError("");
    let params: Record<string, unknown>;
    try {
      params = parseParams(editParams);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid params.");
      return;
    }
    try {
      await api("PATCH", `/api/sync/jobs/${encodeURIComponent(job.id)}`, { name: editName, params });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save job.");
    }
  };

  return (
    <div className="card">
      <h3>Scheduled sync jobs</h3>
      {error ? <p className="muted" role="alert">{error}</p> : null}
      {notice ? <p className="muted" role="status">{notice}</p> : null}
      {jobs === null ? (
        <p className="muted">Loading sync jobs…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">No scheduled jobs yet — create one below.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Source</th>
                <th>On</th>
                <th>Owner</th>
                <th>Last run</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.name}</td>
                  <td>{job.source}</td>
                  <td>{job.enabled ? "yes" : "no"}</td>
                  <td className="muted">{job.owner_employee_id || "—"}</td>
                  <td className="muted">{runSummary(job.last_run)}</td>
                  <td>
                    <button type="button" className="secondary" onClick={() => void runNow(job)}>
                      Run now
                    </button>{" "}
                    <button type="button" className="secondary" onClick={() => void toggle(job)}>
                      {job.enabled ? "Disable" : "Enable"}
                    </button>{" "}
                    <button type="button" className="secondary" onClick={() => startEdit(job)}>
                      Edit
                    </button>{" "}
                    <button type="button" className="secondary" onClick={() => void remove(job)}>
                      Delete
                    </button>
                    <div className="muted" style={{ fontSize: 12 }}>
                      params: {JSON.stringify(displayParams(job.params))}
                    </div>
                    {editing === job.id ? (
                      <div style={{ marginTop: 6 }}>
                        <input type="text" aria-label="Job name" value={editName} onChange={(e) => setEditName(e.target.value)} />
                        <textarea aria-label="Job params JSON" rows={4} value={editParams} onChange={(e) => setEditParams(e.target.value)} style={{ width: "100%" }} />
                        <button type="button" className="action" onClick={() => void saveEdit(job)}>
                          Save
                        </button>{" "}
                        <button type="button" className="secondary" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h4>New job</h4>
      <div>
        <label>
          Source{" "}
          <select aria-label="New job source" value={source} onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>{" "}
        <label>
          Name{" "}
          <input type="text" aria-label="New job name" placeholder="Meta Account A" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
      </div>
      <div>
        <label>
          Params (JSON object; secret values are masked in the list and must be re-entered on edit)
          <textarea aria-label="New job params JSON" rows={3} value={paramsText} onChange={(e) => setParamsText(e.target.value)} style={{ width: "100%" }} />
        </label>
        {(source === "sheets" || source === "drive") && (
          <p className="muted">
            Private files need your Google account: connect it in Settings, then add{" "}
            <code>&quot;google_auth&quot;: true</code> to the params.
          </p>
        )}
      </div>
      <button type="button" className="action" onClick={() => void create()}>
        Create job
      </button>
    </div>
  );
}
