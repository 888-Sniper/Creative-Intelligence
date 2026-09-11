import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { useFilters } from "@/state/FilterContext";

interface AskAnswer {
  answer: string;
  sources?: string[];
  scope?: string;
  review_id?: number | null;
}

/** Ask Foap Creative Intelligence (POST /api/ask with the active scope). */
export function AskBar() {
  const { scope } = useFilters();
  const [question, setQuestion] = useState("");
  const [output, setOutput] = useState<AskAnswer | { error: string } | null>(null);

  const ask = async () => {
    if (!question.trim()) {
      setOutput({ error: "Type A Question First." });
      return;
    }
    const filters: Record<string, string[]> = {};
    for (const [k, v] of scope) {
      const list = filters[k] ?? [];
      list.push(v);
      filters[k] = list;
    }
    try {
      const res = await api<AskAnswer>("POST", "/api/ask", { question, filters });
      setOutput(res);
    } catch (err) {
      setOutput({ error: err instanceof ApiError ? err.message : "Ask Failed." });
    }
  };

  return (
    <div className="ask-bar">
      <h3>Ask Foap Creative Intelligence</h3>
      <div className="ask-row">
        <input
          type="text"
          placeholder="Ask Foap Creative Intelligence about your campaign data…"
          aria-label="Ask about your campaign data"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void ask();
          }}
        />
        <button type="button" className="action" onClick={() => void ask()}>
          Ask
        </button>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
        Try: What hooks are performing best? · Which TikTok format has the lowest CPA? · Does showing the product early improve VTR? · Which campaigns should we scale?
      </div>
      <div className="muted">
        {output === null ? (
          "Answers Cite Your Uploaded Data First."
        ) : "error" in output ? (
          <p className="muted">{output.error}</p>
        ) : (
          <>
            <p>{output.answer}</p>
            <p className="muted">
              Sources: {(output.sources ?? []).join(", ") || "—"} · Scope: {output.scope || "All data"}
              {output.review_id ? ` · Review ${output.review_id} Opened — Export Stays Blocked Until Reviews Are Marked Reviewed` : ""}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
