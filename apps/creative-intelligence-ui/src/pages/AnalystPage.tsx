import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";

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

const OBJECTIVES = ["reach", "video_views", "traffic", "conversions", ""] as const;

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

export function AnalystPage({ accountKey = "" }: { accountKey?: string }) {
  const { filters, scope } = useFilters();
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

  async function send(maxPoints?: number) {
    const question = input.trim();
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

  function renderTable(table: AnalystTable, key: number) {
    return (
      <div key={key} className="analyst-table-wrap">
        {table.title ? <h4>{table.title}</h4> : null}
        <table className="analyst-table">
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

  return (
    <div className="analyst-layout">
      <aside className="analyst-sidebar" aria-label="Saved Analyst Conversations">
        <button type="button" onClick={() => void startConversation()}>
          New Conversation
        </button>
        <ul>
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={c.id === activeId ? "active" : ""}
                onClick={() => {
                  setActiveId(c.id);
                  setMessages([]);
                }}
                title={c.objective ? `Objective: ${c.objective}` : undefined}
              >
                {c.title || "Untitled Conversation"}
                {typeof c.message_count === "number" ? ` (${c.message_count})` : ""}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="analyst-main" aria-label="Foap Analyst Conversation">
        <p className="eyebrow">AI Analyst</p>
        <h1 className="page-title">Your Creative Partner</h1>
        <p className="page-sub">Ask questions, uncover insights, and get recommendations from your creative data.</p>
        <div className="analyst-controls">
          <label>
            Objective{" "}
            <select value={objective} onChange={(e) => setObjective(e.target.value)}>
              {OBJECTIVES.map((o) => (
                <option key={o} value={o}>
                  {(o || "auto").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                </option>
              ))}
            </select>
          </label>
          <label>
            Language{" "}
            <select value={locale} onChange={(e) => setLocale(e.target.value)}>
              <option value="auto">Auto</option>
              <option value="pl">Polski</option>
              <option value="en">English</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void downloadReport("one-pager")}
            disabled={busy}
            title="Sectioned Findings Report (Markdown)"
          >
            Report
          </button>
          <button
            type="button"
            onClick={() => void downloadReport("xlsx")}
            disabled={busy}
            title="Sectioned Findings Report (Excel)"
          >
            Report XLSX
          </button>
          <a href="/api/analyst/workbook">Blank Workbook</a>
          {(lastScope || datasetVersion) && (
            <p className="muted">
              {lastScope}
              {datasetVersion ? ` · Data v${datasetVersion}` : ""}
            </p>
          )}
        </div>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="analyst-messages">
          {messages.map((m, i) => (
            <article key={i} className={`analyst-message ${m.role}`}>
              <p className="analyst-text">{m.text}</p>
              {m.role === "assistant" && m.answer ? (
                <>
                  {(m.answer.tables ?? []).map((t, k) => renderTable(t, k))}
                  {(m.answer.findings_stored ?? []).map((f) => (
                    <div key={f.finding_id} className="analyst-finding">
                      <p>
                        <strong>{f.primary_signal || f.finding_id}</strong>
                        {f.priority ? ` · Priority: ${f.priority}` : ""}
                        {f.confidence_level ? ` · Confidence: ${f.confidence_level}` : ""}
                        {f.status && f.status !== "proposed" ? ` · ${f.status}` : ""}
                      </p>
                      {f.diagnosis ? <p>Diagnosis: {f.diagnosis}</p> : null}
                      {f.creative_hypothesis ? <p>Hypothesis: {f.creative_hypothesis}</p> : null}
                      {f.recommended_iteration ? (
                        <p>Iteration: {f.recommended_iteration}</p>
                      ) : null}
                      {f.element_to_preserve || f.element_to_change ? (
                        <p>
                          Preserve: {f.element_to_preserve || "—"} · Change:{" "}
                          {f.element_to_change || "—"}
                        </p>
                      ) : null}
                      {(!f.status || f.status === "proposed") && (
                        <div className="analyst-finding-actions">
                          <button
                            type="button"
                            onClick={() => void decideFinding(f.finding_id, "accepted")}
                          >
                            Save To Next-Flight Plan
                          </button>
                          <button
                            type="button"
                            onClick={() => void decideFinding(f.finding_id, "rejected")}
                          >
                            Dismiss
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {(m.answer.follow_ups ?? []).length > 0 && (
                    <ul className="analyst-followups">
                      {(m.answer.follow_ups ?? []).map((q) => (
                        <li key={q}>
                          <button
                            type="button"
                            onClick={() => {
                              setInput(q);
                            }}
                          >
                            {q}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {(m.answer.warnings ?? []).length > 0 && (
                    <ul className="analyst-warnings">
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
        <form
          className="analyst-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about hooks, hold, brand delivery, costs…"
            aria-label="Ask Foap Analyst"
          />
          <button type="submit" disabled={busy || !input.trim()}>
            {busy ? "Analysing…" : "Ask"}
          </button>
          <button
            type="button"
            disabled={busy || !input.trim()}
            onClick={() => void send(3)}
            title="Condense The Answer To 3 Points"
          >
            3 Points
          </button>
        </form>
      </section>
    </div>
  );
}
