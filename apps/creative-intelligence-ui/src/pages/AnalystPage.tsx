import { useCallback, useEffect, useState } from "react";
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

export function AnalystPage() {
  const { filters, scope } = useFilters();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [objective, setObjective] = useState(filters.objective || "reach");
  const [locale, setLocale] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastScope, setLastScope] = useState("");
  const [datasetVersion, setDatasetVersion] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    try {
      const data = await api<{ conversations: ConversationSummary[] }>(
        "GET",
        "/api/analyst/conversations",
      );
      setConversations(data.conversations ?? []);
    } catch {
      /* sidebar is optional; chat still works */
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  async function startConversation() {
    setError(null);
    try {
      const data = await api<{ id: string }>("POST", "/api/analyst/conversations", {
        objective: objective || undefined,
      });
      setActiveId(data.id);
      setMessages([]);
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start a conversation");
    }
  }

  async function send(maxPoints?: number) {
    const question = input.trim();
    if (!question || busy) return;
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
        locale,
        max_points: maxPoints,
      });
      if (!activeId) setActiveId(data.conversation_id);
      setLastScope(fmtScope(data.scope_snapshot));
      setDatasetVersion(data.dataset_version ?? null);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.answer.text, answer: data.answer },
      ]);
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyst request failed");
    } finally {
      setBusy(false);
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
              locale,
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
                      locale,
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
      setError(e instanceof Error ? e.message : "Report export failed");
    }
  }

  async function decideFinding(findingId: string, decision: "accepted" | "rejected") {
    setError(null);
    try {
      await api("POST", `/api/analyst/findings/${encodeURIComponent(findingId)}/decision`, {
        decision,
      });
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
      setError(e instanceof Error ? e.message : "Could not save the decision");
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
      <aside className="analyst-sidebar" aria-label="Saved analyst conversations">
        <button type="button" onClick={() => void startConversation()}>
          New conversation
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
                {c.title || "Untitled conversation"}
                {typeof c.message_count === "number" ? ` (${c.message_count})` : ""}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="analyst-main" aria-label="Foap Analyst conversation">
        <div className="analyst-controls">
          <label>
            Objective{" "}
            <select value={objective} onChange={(e) => setObjective(e.target.value)}>
              {OBJECTIVES.map((o) => (
                <option key={o} value={o}>
                  {o || "auto"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Language{" "}
            <select value={locale} onChange={(e) => setLocale(e.target.value)}>
              <option value="auto">auto</option>
              <option value="pl">polski</option>
              <option value="en">English</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void downloadReport("one-pager")}
            disabled={busy}
            title="Sectioned findings report (markdown)"
          >
            Report
          </button>
          <button
            type="button"
            onClick={() => void downloadReport("xlsx")}
            disabled={busy}
            title="Sectioned findings report (Excel)"
          >
            Report XLSX
          </button>
          <a href="/api/analyst/workbook">Blank workbook</a>
          {(lastScope || datasetVersion) && (
            <p className="muted">
              {lastScope}
              {datasetVersion ? ` · data v${datasetVersion}` : ""}
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
                        {f.priority ? ` · priority: ${f.priority}` : ""}
                        {f.confidence_level ? ` · confidence: ${f.confidence_level}` : ""}
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
                            Save to next-flight plan
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
            title="Condense the answer to 3 points"
          >
            3 points
          </button>
        </form>
      </section>
    </div>
  );
}
