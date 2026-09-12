import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { TrendChart } from "@/components/charts";
import {
  EmptyState,
  KpiCard,
  PageHeader,
  Panel,
  Skeleton,
  fmtCompact,
  fmtMoney,
  fmtMult,
  scopeBody,
  useCompare,
  useDaily,
  useScopedApi,
} from "@/components/product";

interface AskAnswer {
  answer: string;
  sources?: string[];
  scope?: string;
  review_id?: number | null;
}

interface BenchGroup {
  impressions: number;
  clicks: number;
  spend: number;
  revenue: number;
  ctr: number | null;
  roas: number | null;
}

interface Conversation {
  id: string;
  title?: string | null;
  objective?: string | null;
  updated_at?: string | null;
}

const PROMPTS = [
  "What drove our CTR increase?",
  "Which creatives perform best?",
  "Compare performance by platform",
  "Summarise last month",
];

const SUGGESTED = [
  "What were the top performing creatives for these campaigns?",
  "Compare ROI by platform",
  "Which audience segments performed best?",
  "Why did our CTR increase?",
  "Show me underperforming creatives",
  "Summarise last month's performance",
];

const FOLLOW_UPS = [
  "Which hook type should we test next?",
  "How does video length affect CTR?",
  "Which campaign should we scale first?",
];

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function bucket(points: Array<{ date: string; revenue: number }>): { labels: string[]; values: number[] } {
  if (points.length <= 12) {
    return {
      labels: points.map((p) => p.date.slice(5)),
      values: points.map((p) => num(p.revenue)),
    };
  }
  const size = Math.ceil(points.length / 12);
  const labels: string[] = [];
  const values: number[] = [];
  for (let i = 0; i < points.length; i += size) {
    const chunk = points.slice(i, i + size);
    labels.push(chunk[0].date.slice(5));
    values.push(chunk.reduce((t, p) => t + num(p.revenue), 0));
  }
  return { labels, values };
}

export function AskPage() {
  const { scope } = useFilters();
  const [question, setQuestion] = useState("Which campaigns had the highest ROI last month and what drove the results?");
  const [asked, setAsked] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [chats, setChats] = useState<Conversation[] | null>(null);

  const compare = useCompare();
  const daily = useDaily(90);
  const platforms = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=platform");
  const hooks = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=hook_type");

  useEffect(() => {
    let live = true;
    api<{ conversations: Conversation[] }>("GET", "/api/analyst/conversations")
      .then((r) => live && setChats(r.conversations ?? []))
      .catch(() => live && setChats([]));
    return () => { live = false; };
  }, []);

  const ask = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    setAsked(text);
    try {
      const res = await api<AskAnswer>("POST", "/api/ask", {
        question: text,
        filters: scopeBody(scope),
      });
      setAnswer(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ask Failed.");
    } finally {
      setBusy(false);
    }
  };

  const roi = useMemo(() => bucket(daily ?? []), [daily]);

  const takeaways = useMemo(() => {
    const out: string[] = [];
    const rows = Object.entries(platforms.data ?? {})
      .map(([key, g]) => ({ key, roas: g.roas ?? null }))
      .filter((r) => r.roas != null)
      .sort((a, b) => (b.roas ?? 0) - (a.roas ?? 0));
    if (rows[0]?.roas != null) {
      out.push(`${rows[0].key === "meta" ? "Meta" : rows[0].key === "tiktok" ? "TikTok" : rows[0].key} leads the current scope at ${rows[0].roas.toFixed(1)}x ROAS.`);
    }
    const hookRows = Object.entries(hooks.data ?? {})
      .map(([key, g]) => ({ key, ctr: g.ctr == null ? null : g.ctr * 100 }))
      .filter((r) => r.ctr != null)
      .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    if (hookRows[0]?.ctr != null) {
      out.push(`${hookRows[0].key.replace(/_/g, " ")} hooks average ${(hookRows[0].ctr ?? 0).toFixed(1)}% CTR across the current scope.`);
    }
    if (answer?.sources?.length) {
      out.push(`Grounded in ${answer.sources.join(", ")} for the scope “${answer.scope || "All data"}”.`);
    }
    return out.slice(0, 3);
  }, [platforms.data, hooks.data, answer]);

  const kpis = compare ? [
    { label: "Total Spend", metric: "spend", display: fmtMoney(num(compare.metrics.spend?.current)) },
    { label: "Conversions", metric: "conversions", display: fmtCompact(num(compare.metrics.conversions?.current)) },
    { label: "Average CPA", metric: "cpa", display: fmtMoney(num(compare.metrics.cpa?.current)) },
    { label: "Average ROAS", metric: "roas", display: fmtMult(num(compare.metrics.roas?.current)) },
  ] : [];

  return (
    <>
      <PageHeader
        title="Ask The Data"
        sub="Get instant, data-backed answers about your marketing performance."
      />
      <div className="main-rail">
        <div className="rail-stack">
          <Panel title="Ask a Question">
            <div className="composer">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void ask(); }}
                placeholder="Ask a question about your marketing data…"
                aria-label="Ask a question about your marketing data"
              />
              <LoadingButton type="button" className="btn-primary" loading={busy} loadingLabel="Asking…" disabled={busy || !question.trim()} onClick={() => void ask()}>
                <Icon name="chat" size={16} /> Ask
              </LoadingButton>
            </div>
            <div className="prompt-chips">
              {PROMPTS.map((p) => (
                <button key={p} type="button" className="chip" onClick={() => { setQuestion(p); void ask(p); }}>
                  {p}
                </button>
              ))}
            </div>
          </Panel>
          {asked ? (
            <Panel title={asked} sub="Today">
              {busy ? <Skeleton height={120} /> : error ? (
                <EmptyState text={error} />
              ) : answer ? (
                <>
                  <p style={{ fontSize: 14, lineHeight: 1.6 }}>{answer.answer}</p>
                  <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
                    {kpis.map((k) => (
                      <KpiCard
                        key={k.metric}
                        label={k.label}
                        display={k.display}
                        icon={k.metric === "spend" ? "coin" : k.metric === "conversions" ? "click" : k.metric === "cpa" ? "users" : "bars"}
                        tint="#E7F1FB"
                        metricLabel={k.metric === "roas" ? "ROAS" : k.metric === "cpa" ? "CPA" : k.label.replace("Average ", "").replace("Total ", "")}
                        compare={compare}
                      />
                    ))}
                  </div>
                  <Panel title="ROI Trend by Top Campaigns">
                    {daily ? (
                      <TrendChart
                        series={[{ label: "Revenue", color: "#00B3A0", soft: "#DDF3F0", points: roi.values }]}
                        labels={roi.labels}
                      />
                    ) : <Skeleton height={200} />}
                  </Panel>
                  <Panel title="Suggested Follow-Ups">
                    <div className="prompt-chips">
                      {FOLLOW_UPS.map((f) => (
                        <button key={f} type="button" className="chip" onClick={() => { setQuestion(f); void ask(f); }}>
                          {f}
                        </button>
                      ))}
                    </div>
                  </Panel>
                  <div className="cols-2">
                    <Panel title="Source & Data Context">
                      <p className="panel-sub">Sources: {(answer.sources ?? []).join(", ") || "—"}</p>
                      <p className="panel-sub">Scope: {answer.scope || "All data"}</p>
                      {answer.review_id ? <p className="panel-sub">Review #{answer.review_id} opened.</p> : null}
                    </Panel>
                    <Panel title="Benchmark Context">
                      {platforms.data ? (
                        <p className="panel-sub">
                          {Object.entries(platforms.data).map(([k, g]) =>
                            `${k === "meta" ? "Meta" : k === "tiktok" ? "TikTok" : k}: ${g.roas == null ? "—" : `${g.roas.toFixed(1)}x`} ROAS`,
                          ).join(" · ") || "No platform benchmarks in scope."}
                        </p>
                      ) : <Skeleton height={60} />}
                    </Panel>
                  </div>
                  {takeaways.length ? (
                    <div className="takeaways" style={{ marginTop: 16 }}>
                      <h5>Key Takeaways</h5>
                      <ul>
                        {takeaways.map((t) => (
                          <li key={t}><Icon name="check" size={13} /><span>{t}</span></li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </>
              ) : null}
            </Panel>
          ) : (
            <Panel title="Ask a Question to Begin">
              <p className="panel-sub">Answers cite your uploaded data first and always show their scope.</p>
            </Panel>
          )}
        </div>
        <div className="rail-stack">
          <Panel title="Suggested Questions">
            <div className="rail-stack" style={{ gap: 8 }}>
              {SUGGESTED.map((s) => (
                <button key={s} type="button" className="btn-outline" style={{ justifyContent: "space-between", textAlign: "left" }}
                  onClick={() => { setQuestion(s); void ask(s); }}>
                  <span style={{ minWidth: 0, whiteSpace: "normal" }}>{s}</span>
                  <span style={{ flex: "none" }} aria-hidden="true"><Icon name="chev" size={14} /></span>
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Recent Chats" action={<Link className="link-teal" to="/analyst">View all</Link>}>
            {chats === null ? <Skeleton height={140} /> : (
              chats.length ? (
                <div>
                  {chats.slice(0, 5).map((c) => (
                    <div className="insight" key={c.id}>
                      <span className="insight-ico" style={{ background: "#E7F1FB" }}>
                        <Icon name="chat" size={18} />
                      </span>
                      <div>
                        <h4>{c.title || "Untitled Conversation"}</h4>
                        <p>{c.updated_at ? c.updated_at.slice(0, 10) : ""}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="No analyst chats yet." />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
