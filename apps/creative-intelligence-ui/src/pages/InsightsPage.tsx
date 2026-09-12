import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  EmptyState,
  PageHeader,
  Panel,
  Skeleton,
  scopeBody,
  useScopedApi,
} from "@/components/product";

interface Conversation {
  id: string;
  title?: string | null;
  objective?: string | null;
  updated_at?: string | null;
}

interface SavedView {
  id: number;
  name: string;
  state: {
    filters?: Record<string, string[]>;
    kpi?: string;
    view?: string;
  };
}

interface AnalystCard {
  creative_key: string;
  name?: string;
  platform?: string;
  campaign?: string;
  finding?: {
    primary_signal?: string;
    diagnosis?: string;
    priority?: string;
    confidence_level?: string;
    recommended_iteration?: string;
  } | null;
}

const VIEW_ROUTES: Record<string, string> = {
  main: "/",
  campaign: "/campaigns",
  creative: "/creatives",
  compare: "/compare",
  benchmark: "/benchmarks",
  report: "/reports",
  profile: "/profile",
  admin: "/admin",
};

function dayLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function withinDays(iso: string | null | undefined, days: number): boolean {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return false;
  return Date.now() - t <= days * 86400000;
}

export function InsightsPage() {
  const { filters, setFilter, scope } = useFilters();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [client, setClient] = useState("All Clients");
  const [platform, setPlatform] = useState("All Platforms");
  const [market, setMarket] = useState("All Markets");
  const [itype, setItype] = useState("All Types");
  const [dateSaved, setDateSaved] = useState("All Time");
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [views, setViews] = useState<SavedView[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const cards = useScopedApi<{ creatives: AnalystCard[] }>("/api/analyst/creatives?objective=reach");

  useEffect(() => {
    let live = true;
    api<{ conversations: Conversation[] }>("GET", "/api/analyst/conversations")
      .then((r) => live && setConversations(r.conversations ?? []))
      .catch(() => live && setConversations([]));
    api<SavedView[]>("GET", "/api/views")
      .then((r) => live && setViews(Array.isArray(r) ? r : []))
      .catch(() => live && setViews([]));
    return () => { live = false; };
  }, []);

  const findings = useMemo(() => {
    const rows = cards.data?.creatives ?? [];
    const withSignal = rows.filter((c) => c.finding?.primary_signal);
    const pinned = withSignal.filter((c) => c.finding?.priority === "high").slice(0, 3);
    const rest = withSignal.filter((c) => !(c.finding?.priority === "high")).slice(0, 6);
    return { pinned: pinned.length ? pinned : withSignal.slice(0, 3), rest };
  }, [cards.data]);

  const needle = search.trim().toLowerCase();
  const matchDate = (iso: string | null | undefined) => {
    if (dateSaved === "All Time") return true;
    return withinDays(iso, dateSaved === "Last 7 Days" ? 7 : 30);
  };
  const matchAxes = (c: AnalystCard) => {
    if (platform !== "All Platforms" && (c.platform ?? "").toLowerCase() !== platform.toLowerCase()) {
      if (platform !== "All Platforms") {
        const want = platform.toLowerCase();
        if ((c.platform ?? "").toLowerCase() !== want) return false;
      }
    }
    void client;
    void market;
    return true;
  };

  const savedCards = useMemo(() => {
    const out: Array<{ key: string; badge: string; title: string; body: string; meta: string; to: string; apply?: SavedView }> = [];
    if (itype === "All Types" || itype === "Conversations") {
      for (const c of conversations ?? []) {
        if (!matchDate(c.updated_at)) continue;
        const title = c.title || "Untitled Conversation";
        if (needle && !`${title} ${c.objective ?? ""}`.toLowerCase().includes(needle)) continue;
        out.push({
          key: `c-${c.id}`,
          badge: "Conversation",
          title,
          body: c.objective ? `Objective: ${c.objective}` : "Analyst conversation.",
          meta: c.updated_at ? `Updated ${dayLabel(c.updated_at)}` : "",
          to: "/analyst",
        });
      }
    }
    if (itype === "All Types" || itype === "Saved Views") {
      for (const v of views ?? []) {
        if (needle && !v.name.toLowerCase().includes(needle)) continue;
        const axes = Object.keys(v.state?.filters ?? {}).length;
        out.push({
          key: `v-${v.id}`,
          badge: "Saved View",
          title: v.name,
          body: `Saved analysis setup${axes ? ` across ${axes} filter axes` : ""}.`,
          meta: v.state?.view ? `Opens ${(VIEW_ROUTES[v.state.view] ?? v.state.view)}` : "",
          to: v.state?.view ? (VIEW_ROUTES[v.state.view] ?? "/") : "/",
          apply: v,
        });
      }
    }
    return out;
  }, [conversations, views, itype, needle, dateSaved]);

  const applyView = (v: SavedView) => {
    const f = v.state?.filters ?? {};
    for (const k of ["client", "project", "campaign", "platform", "vertical", "market", "objective", "date", "date_from", "date_to"] as const) {
      const val = (f[k] ?? [])[0] ?? "";
      setFilter(k, k === "platform" && val && !["all", "meta", "tiktok"].includes(val) ? "all" : val);
    }
    navigate(v.state?.view ? (VIEW_ROUTES[v.state.view] ?? "/") : "/");
  };

  const saveInsight = async () => {
    setSaving(true);
    setSaveStatus("");
    try {
      const name = `Insight — ${new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`;
      await api("POST", "/api/views", {
        name,
        state: { filters: scopeBody(scope), kpi: filters.kpi, view: "main" },
      });
      const list = await api<SavedView[]>("GET", "/api/views");
      setViews(Array.isArray(list) ? list : []);
      setSaveStatus(`Saved ${name}.`);
    } catch (e) {
      setSaveStatus(e instanceof Error ? e.message : "Could Not Save Insight.");
    } finally {
      setSaving(false);
    }
  };

  const recent = useMemo(() => (conversations ?? []).slice(0, 5), [conversations]);

  return (
    <>
      <PageHeader
        title="Saved Insights"
        sub="Your saved insights, key learnings, and creative findings all in one place."
        actions={(
          <LoadingButton type="button" className="btn-primary" loading={saving} loadingLabel="Saving…" disabled={saving} onClick={() => void saveInsight()}>
            <Icon name="plus" size={16} /> Save Insight
          </LoadingButton>
        )}
      />
      {saveStatus ? <p className="panel-sub" role="status" style={{ margin: "0 0 12px" }}>{saveStatus}</p> : null}
      <section className="panel" aria-label="Find insights" style={{ padding: "12px 16px" }}>
        <div className="filter-grid" style={{ gridTemplateColumns: "repeat(6,minmax(0,1fr))", marginTop: 0 }}>
          <div className="field">
            <label htmlFor="in-search">Search</label>
            <input id="in-search" placeholder="Search saved insights…" value={search}
              onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="in-client">Client</label>
            <select id="in-client" value={client} onChange={(e) => setClient(e.target.value)}>
              {["All Clients"].map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="in-platform">Platform</label>
            <select id="in-platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {["All Platforms", "Meta", "TikTok"].map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="in-market">Market</label>
            <select id="in-market" value={market} onChange={(e) => setMarket(e.target.value)}>
              {["All Markets"].map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="in-type">Insight Type</label>
            <select id="in-type" value={itype} onChange={(e) => setItype(e.target.value)}>
              {["All Types", "Conversations", "Saved Views", "Creative Findings"].map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="in-date">Date Saved</label>
            <select id="in-date" value={dateSaved} onChange={(e) => setDateSaved(e.target.value)}>
              {["All Time", "Last 7 Days", "Last 30 Days"].map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
        </div>
      </section>
      <div className="main-rail" style={{ marginTop: 12, gap: 12 }}>
        <div className="rail-stack" style={{ gap: 12 }}>
          <Panel title="Pinned Learnings" sub="Your most important insights, always within reach.">
            {cards.data ? (
              findings.pinned.length ? (
                <div style={{ background: "#DFF5F1", borderRadius: 10, padding: 10 }}>
                  <div className="cards-4" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 10 }}>
                    {findings.pinned.map((c) => (
                      <div className="cmp-card" key={c.creative_key} style={{ padding: 12 }}>
                        <h4 style={{ margin: "0 0 6px", fontSize: 13.5 }}>{c.finding?.primary_signal}</h4>
                        <p className="panel-sub" style={{ margin: 0 }}>{c.finding?.diagnosis}</p>
                        <p className="panel-sub" style={{ margin: "4px 0 0" }}>{[c.platform, c.campaign].filter(Boolean).join(" · ")}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : <EmptyState text="No pinned learnings yet. Run the AI Analyst to generate findings." />
            ) : <Skeleton height={120} />}
          </Panel>
          <Panel title={`Your Saved Insights (${savedCards.length})`}>
            {conversations === null || views === null ? <Skeleton height={160} /> : (
              savedCards.length ? (
                <div className="cards-4" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 12 }}>
                  {savedCards.map((s) => (
                    <div className="cmp-card" key={s.key} style={{ padding: 14 }}>
                      <span className="badge-demo">{s.badge}</span>
                      <h4 style={{ margin: "8px 0 6px", fontSize: 13.5 }}>{s.title}</h4>
                      <p className="panel-sub" style={{ margin: 0 }}>{s.body}</p>
                      <p className="panel-sub" style={{ margin: "4px 0 8px" }}>{s.meta}</p>
                      {s.apply ? (
                        <button type="button" className="btn-soft" onClick={() => applyView(s.apply as SavedView)}>
                          Open Insight →
                        </button>
                      ) : (
                        <Link className="btn-soft" to={s.to}>Open Insight →</Link>
                      )}
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="No saved insights match the current search and filters." />
            )}
          </Panel>
          {(itype === "All Types" || itype === "Creative Findings") && findings.rest.filter(matchAxes).length ? (
            <Panel title="Creative Findings">
              <div className="cards-4" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 12 }}>
                {findings.rest.filter(matchAxes).slice(0, 6).map((c) => (
                  <div className="cmp-card" key={c.creative_key} style={{ padding: 14 }}>
                    <span className="badge-demo">Creative Finding</span>
                    <h4 style={{ margin: "8px 0 6px", fontSize: 13.5 }}>{c.finding?.primary_signal}</h4>
                    <p className="panel-sub" style={{ margin: "0 0 8px" }}>{c.finding?.diagnosis}</p>
                    <Link className="btn-soft" to="/analyst">Open in Analyst →</Link>
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}
        </div>
        <div className="rail-stack" style={{ gap: 12 }}>
          <Panel title="Recent Activity">
            {conversations === null ? <Skeleton height={160} /> : (
              recent.length ? (
                <div>
                  {recent.map((c) => (
                    <div className="insight" key={c.id}>
                      <span className="insight-ico" style={{ background: "#E7F1FB" }}>
                        <Icon name="chat" size={20} />
                      </span>
                      <div>
                        <h4>{c.title || "Untitled Conversation"}</h4>
                        <p>{c.updated_at ? dayLabel(c.updated_at) : ""}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState text="No recent analyst activity yet." />
            )}
          </Panel>
          <Panel title="Recommended Related Insights">
            {cards.data ? (
              <div>
                {findings.rest.slice(0, 4).map((c) => (
                  <div className="insight" key={c.creative_key}>
                    <span className="insight-ico" style={{ background: "#DFF5F1" }}>
                      <Icon name="spark" size={20} />
                    </span>
                    <div>
                      <h4>{c.finding?.primary_signal}</h4>
                      <p>{c.finding?.recommended_iteration ?? c.finding?.diagnosis}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : <Skeleton height={160} />}
          </Panel>
        </div>
      </div>
    </>
  );
}
