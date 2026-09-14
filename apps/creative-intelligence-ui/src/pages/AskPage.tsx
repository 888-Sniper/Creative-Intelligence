import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import { TrendChart } from "@/components/charts";
import {
  EmptyState,
  KpiCard,
  PageHeader,
  Panel,
  Skeleton,
  KpiKind,
  kpiDisplay,
  kpiPlaceholderNote,
  scopeBody,
  useCampaignMeta,
  useCompareState,
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

const PROMPT_KEYS = ["p0", "p1", "p2", "p3"] as const;
const SUGGESTED_KEYS = ["s0", "s1", "s2", "s3", "s4", "s5"] as const;
const FOLLOW_UP_KEYS = ["f0", "f1", "f2"] as const;

function num(v: unknown): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function friendlyDate(fmtDate: (iso: string, opts?: Intl.DateTimeFormatOptions) => string, raw?: string | null): string {
  if (!raw) return "";
  return fmtDate(raw, { month: "short", day: "numeric", year: "numeric" });
}

/** Bucket daily revenue into at most 12 EQUAL-TIME spans. Fixed-count
 *  chunking leaves a short final bucket whose smaller sum reads as a
 *  revenue cliff; equal time spans keep every bucket comparable. */
export function bucket(points: Array<{ date: string; revenue: number }>): { labels: string[]; values: number[] } {
  const pts = points.filter((p) => typeof p.date === "string" && p.date.length >= 8);
  if (pts.length <= 12) {
    return {
      labels: pts.map((p) => p.date.slice(5)),
      values: pts.map((p) => num(p.revenue)),
    };
  }
  const N = 12;
  const t0 = Date.parse(pts[0].date);
  const t1 = Date.parse(pts[pts.length - 1].date);
  const width = (Math.max(t1, t0) - t0 + 86400000) / N;
  const labels = new Array<string>(N).fill("");
  const values = new Array<number>(N).fill(0);
  for (const p of pts) {
    const i = Math.min(N - 1, Math.max(0, Math.floor((Date.parse(p.date) - t0) / width)));
    values[i] += num(p.revenue);
    if (!labels[i]) labels[i] = p.date.slice(5);
  }
  return { labels, values };
}

export function AskPage() {
  const { scope } = useFilters();
  const { t, fmtDate } = useLocale();
  const defaultQuestion = t("ask.defaultQuestion");
  const [question, setQuestion] = useState(defaultQuestion);
  const [asked, setAsked] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [chats, setChats] = useState<Conversation[] | null>(null);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  // The opening answered example fires exactly once per mount.
  const autoRan = useRef(false);

  const { data: compare, error: compareError } = useCompareState();
  const daily = useDaily(90);
  const platforms = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=platform");
  const hooks = useScopedApi<Record<string, BenchGroup>>("/api/benchmarks?group_by=hook_type");
  /* The opening sample auto-runs in DEMO workspaces only: a normal
   * production visit must never POST /api/ask on its own. */
  const demoMode = useCampaignMeta().data?.demo === true;

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
        filters: scopeBody(scopeRef.current),
      });
      setAnswer(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("ask.failedMsg"));
    } finally {
      setBusy(false);
    }
  };
  const askRef = useRef(ask);
  askRef.current = ask;

  // Demo workspaces open with a representative answered example
  // already on screen; everything shown comes from the live backend
  // scope. Production workspaces open on the empty composer. The demo
  // flag resolves asynchronously, so this fires when it turns true.
  useEffect(() => {
    if (autoRan.current || !demoMode) return;
    autoRan.current = true;
    void askRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoMode]);

  const roi = useMemo(() => bucket(daily ?? []), [daily]);

  const takeaways = useMemo(() => {
    const out: string[] = [];
    const rows = Object.entries(platforms.data ?? {})
      .map(([key, g]) => ({ key, roas: g.roas ?? null }))
      .filter((r) => r.roas != null)
      .sort((a, b) => (b.roas ?? 0) - (a.roas ?? 0));
    if (rows[0]?.roas != null) {
      // Ties at one decimal are declared honestly instead of crowning
      // the first row of a tied sort.
      const top = rows[0].roas as number;
      const tied = rows.filter((r) => (r.roas ?? -1).toFixed(1) === top.toFixed(1));
      const name = (k: string) => (k === "meta" ? "Meta" : k === "tiktok" ? "TikTok" : k);
      out.push(tied.length > 1
        ? t("ask.takeTie", { a: name(tied[0].key), b: tied.slice(1).map((r) => name(r.key)).join(", "), roas: top.toFixed(1) })
        : t("ask.takeLead", { a: name(rows[0].key), roas: top.toFixed(1) }));
    }
    const hookRows = Object.entries(hooks.data ?? {})
      .map(([key, g]) => ({ key, ctr: g.ctr == null ? null : g.ctr * 100 }))
      .filter((r) => r.ctr != null)
      .sort((a, b) => (b.ctr ?? 0) - (a.ctr ?? 0));
    if (hookRows[0]?.ctr != null) {
      const raw = hookRows[0].key;
      const hit = t(`filters.hooks.${raw}`);
      const hook = hit === `filters.hooks.${raw}` ? raw.replace(/_/g, " ") : hit;
      const cap = hook.charAt(0).toUpperCase() + hook.slice(1);
      out.push(t("ask.takeHook", { hook: cap, ctr: (hookRows[0].ctr ?? 0).toFixed(1) }));
    }
    if (answer?.sources?.length) {
      out.push(t("ask.takeGrounded", { sources: answer.sources.join(", "), scope: answer.scope || t("ask.allData") }));
    }
    return out.slice(0, 3);
  }, [platforms.data, hooks.data, answer, t]);

  const emptyScope = compare ? compare.current_n_ads === 0 : false;
  const kpiDefs: Array<{ label: string; metric: string; kind: KpiKind; value: number | null | undefined }> = compare ? [
    { label: t("dashboard.totalSpend"), metric: "spend", kind: "money", value: compare.metrics.spend?.current },
    { label: t("filters.kpis.conversions"), metric: "conversions", kind: "count", value: compare.metrics.conversions?.current },
    { label: t("ask.avgCpa"), metric: "cpa", kind: "money", value: compare.metrics.cpa?.current },
    { label: t("dashboard.averageRoas"), metric: "roas", kind: "mult", value: compare.metrics.roas?.current },
  ] : [];
  const kpis = kpiDefs.map((k) => ({
    ...k,
    display: kpiDisplay(k.kind, k.value, emptyScope),
    note: kpiPlaceholderNote(k.kind, k.value, emptyScope),
  }));

  return (
    <>
      <PageHeader
        title={t("ask.title")}
        sub={t("ask.sub")}
      />
      <div className="main-rail">
        <div className="rail-stack">
          <section className="panel" aria-label={t("ask.composerLabel")}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void ask();
              }}
            >
              <div className="composer ask-composer">
                <Icon name="chat" size={18} />
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={t("ask.inputPlaceholder")}
                  aria-label={t("ask.inputPlaceholder")}
                />
                <LoadingButton type="submit" className="btn-send" loading={busy} loadingLabel={t("common.sending")} spinnerClass="spinner" disabled={busy || !question.trim()} aria-label={t("ask.askBtn")}>
                  <Icon name="send" size={17} />
                </LoadingButton>
              </div>
            </form>
            <div className="prompt-chips" style={{ marginTop: 10 }}>
              {PROMPT_KEYS.map((k) => {
                const p = t(`ask.prompts.${k}`);
                return (
                  <button key={k} type="button" className="chip" onClick={() => { setQuestion(p); void ask(p); }}>
                    {p}
                  </button>
                );
              })}
            </div>
          </section>
          {asked ? (
            <Panel title={asked} sub={t("ask.todaySub")} style={{ flex: "1 0 auto" }}>
              {busy ? <Skeleton height={120} /> : error ? (
                <EmptyState text={error} />
              ) : answer ? (
                <>
                  <p style={{ fontSize: 14, lineHeight: 1.6, marginTop: 0 }}>{answer.answer}</p>
                  {compare ? (
                    <div className="kpi-grid">
                      {kpis.map((k) => (
                        <KpiCard
                          key={k.metric}
                          label={k.label}
                          display={k.display}
                          note={k.note}
                          icon={k.metric === "spend" ? "coin" : k.metric === "conversions" ? "click" : k.metric === "cpa" ? "users" : "bars"}
                          tint="var(--shell-blue-soft)"
                          metricLabel={t(`filters.kpis.${k.metric}`)}
                          compare={compare}
                        />
                      ))}
                    </div>
                  ) : compareError ? (
                    <EmptyState text={compareError} />
                  ) : <Skeleton height={118} />}
                  <Panel title={t("ask.trendTitle")}>
                    {daily ? (
                      <TrendChart
                        series={[{ label: t("filters.kpis.revenue"), color: "var(--glyph-teal)", soft: "#E5F5F2", points: roi.values }]}
                        labels={roi.labels}
                      />
                    ) : <Skeleton height={200} />}
                  </Panel>
                  <div className="cols-2">
                    <Panel title={t("ask.contextTitle")}>
                      <p className="panel-sub">{t("ask.sourcesLabel", { sources: (answer.sources ?? []).join(", ") || "—" })}</p>
                      <p className="panel-sub">{t("ask.scopeLabel", { scope: answer.scope || t("ask.allData") })}</p>
                      {answer.review_id ? <p className="panel-sub">{t("ask.reviewSaved", { id: answer.review_id })}</p> : null}
                    </Panel>
                    <Panel title={t("ask.extraContextTitle")}>
                      {platforms.data ? (
                        <p className="panel-sub">
                          {Object.entries(platforms.data).map(([k, g]) =>
                            `${k === "meta" ? "Meta" : k === "tiktok" ? "TikTok" : k}: ${g.roas == null ? "—" : `${g.roas.toFixed(1)}x`} ROAS`,
                          ).join(" · ") || t("ask.noPlatforms")}
                        </p>
                      ) : <Skeleton height={60} />}
                    </Panel>
                  </div>
                  {takeaways.length ? (
                    <div className="takeaways">
                      <h5>{t("ask.takeawaysTitle")}</h5>
                      <ul>
                        {takeaways.map((item) => (
                          <li key={item}><Icon name="check" size={13} /><span>{item}</span></li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <Panel title={t("ask.followUpsTitle")}>
                    <div className="prompt-chips" style={{ marginTop: 0 }}>
                      {FOLLOW_UP_KEYS.map((k) => {
                        const f = t(`ask.followups.${k}`);
                        return (
                          <button key={k} type="button" className="chip chip-sugg" onClick={() => { setQuestion(f); void ask(f); }}>
                            {f}
                          </button>
                        );
                      })}
                    </div>
                  </Panel>
                </>
              ) : null}
            </Panel>
          ) : (
            <Panel title={t("ask.beginTitle")} style={{ flex: "1 0 auto" }}>
              <EmptyState
                icon="chat"
                title={t("ask.firstTitle")}
                text={t("ask.firstBody")}
              />
            </Panel>
          )}
        </div>
        <div className="rail-stack">
          <Panel title={t("ask.suggestedTitle")}>
            <div className="rail-stack" style={{ gap: 6 }}>
              {SUGGESTED_KEYS.map((k) => {
                const s = t(`ask.suggested.${k}`);
                return (
                <button key={k} type="button" className="btn-outline chip-sugg" style={{ justifyContent: "space-between", textAlign: "left", minHeight: 30, padding: "6px 12px", fontSize: 12.5 }}
                  onClick={() => { setQuestion(s); void ask(s); }}>
                  <span style={{ minWidth: 0, whiteSpace: "normal" }}>{s}</span>
                  <span style={{ flex: "none" }} aria-hidden="true"><Icon name="chev" size={14} /></span>
                </button>
                );
              })}
            </div>
          </Panel>
          <Panel title={t("ask.recentTitle")} action={<Link className="link-teal" to="/analyst">{t("common.viewAll")}</Link>} style={{ flex: "1 0 auto" }}>
            {chats === null ? <Skeleton height={120} /> : (
              chats.length ? (
                <div>
                  {chats.slice(0, 5).map((c) => (
                    <Link key={c.id} to={`/analyst?conversation=${encodeURIComponent(c.id)}`}
                      style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 0", borderBottom: "1px solid var(--shell-line)", textDecoration: "none" }}>
                      <span className="insight-ico" style={{ background: "var(--shell-blue-soft)", width: 30, height: 30, borderRadius: 9 }}>
                        <Icon name="chat" size={15} />
                      </span>
                      <div style={{ minWidth: 0 }}>
                        <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "var(--shell-navy)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {c.title || t("pageInsights.untitledConv")}
                        </p>
                        <p className="panel-sub" style={{ margin: 0, fontSize: 11.5 }}>{friendlyDate(fmtDate, c.updated_at)}</p>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : <EmptyState compact icon="chat" title={t("ask.noChatsTitle")} text={t("ask.noChatsBody")} />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
