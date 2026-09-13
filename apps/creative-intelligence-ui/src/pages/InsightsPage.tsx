import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useFilters } from "@/state/FilterContext";
import { Icon } from "@/components/icons";
import { LoadingButton } from "@/components/LoadingButton";
import {
  EmptyState,
  MetaSelect,
  PageHeader,
  Panel,
  Skeleton,
  scopeBody,
  useCampaignMeta,
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

/** Finding titles come from backend signal copy (lowercase by
 *  convention): display them sentence-cased so cards read like titles
 *  without altering the underlying data. */
export function signalTitle(s: string | null | undefined): string {
  if (!s) return "Untitled Finding";
  return s.charAt(0).toUpperCase() + s.slice(1);
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
  const location = useLocation();
  /* Global header search deep-links here: ?find= pre-fills the search
   * so the hit is visible immediately. */
  const [search, setSearch] = useState(
    () => new URLSearchParams(location.search).get("find") ?? "");
  const [client, setClient] = useState("");
  const [platform, setPlatform] = useState("");
  const [market, setMarket] = useState("");
  const [itype, setItype] = useState("All Types");
  const [dateSaved, setDateSaved] = useState("All Time");
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [views, setViews] = useState<SavedView[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const cards = useScopedApi<{ creatives: AnalystCard[] }>("/api/analyst/creatives?objective=reach");
  const meta = useCampaignMeta();
  const metaRows = meta.data?.campaigns ?? [];
  const metaClients = [...new Set(metaRows.map((r) => r.client.trim()).filter(Boolean))].sort();
  const metaMarkets = [...new Set(metaRows.flatMap((r) => r.markets).map((s) => s.trim()).filter(Boolean))].sort();
  const metaByCampaign = useMemo(() => {
    const m = new Map<string, { client: string; markets: string[] }>();
    for (const r of metaRows) {
      if (!m.has(r.name)) m.set(r.name, { client: r.client, markets: r.markets });
    }
    return m;
  }, [metaRows]);

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
  /* Every visible axis filter affects content. Creative findings
   *  carry platform + campaign, so client/market resolve through the
   *  campaign metadata (honest: no invented per-finding attributes). */
  const matchAxes = (c: AnalystCard) => {
    if (platform && (c.platform ?? "").toLowerCase() !== platform.toLowerCase()) return false;
    if (client || market) {
      const attr = c.campaign ? metaByCampaign.get(c.campaign) : undefined;
      if (client && (attr?.client ?? "").toLowerCase() !== client.toLowerCase()) return false;
      if (market && !(attr?.markets ?? []).some((m) => m.toLowerCase() === market.toLowerCase())) return false;
    }
    return true;
  };

  /* Saved views match by their stored filter state: a view with no
   * constraint on an axis covers every value of that axis. */
  const matchViewAxes = (v: SavedView) => {
    const f = v.state?.filters ?? {};
    const has = (axis: string, want: string) => {
      if (!want) return true;
      const vals = f[axis] ?? [];
      if (!vals.length) return true;
      return vals.some((x) => x.toLowerCase() === want.toLowerCase() || x.toLowerCase() === "all");
    };
    return has("client", client) && has("platform", platform) && has("market", market);
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
        if (!matchViewAxes(v)) continue;
        if (needle && !v.name.toLowerCase().includes(needle)) continue;
        const axes = Object.keys(v.state?.filters ?? {}).length;
        const route = v.state?.view ? (VIEW_ROUTES[v.state.view] ?? v.state.view) : "";
        out.push({
          key: `v-${v.id}`,
          badge: "Saved View",
          title: v.name,
          body: `Saved analysis setup${axes ? ` across ${axes} filter ${axes === 1 ? "axis" : "axes"}` : ""}.`,
          meta: route ? `Opens ${route}` : "",
          to: route || "/",
          apply: v,
        });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversations, views, itype, needle, dateSaved, client, platform, market]);

  /* Saved views restore the FULL saved scope: every stored axis plus
   * the saved KPI. The global scope model is single-value per axis,
   * so the first stored value wins when several were saved (documented
   * here, not silently dropped elsewhere). */
  const SCOPE_KEYS = ["client", "project", "team", "campaign", "platform",
    "vertical", "market", "funnel", "objective", "status", "spend_min",
    "spend_max", "hook_type", "creator_vs_branded", "format", "date",
    "date_from", "date_to"] as const;
  const applyView = (v: SavedView) => {
    const f = v.state?.filters ?? {};
    for (const k of SCOPE_KEYS) {
      setFilter(k, (f[k] ?? [])[0] ?? "");
    }
    if (v.state?.kpi) setFilter("kpi", v.state.kpi);
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
      <section className="panel" aria-label="Find insights">
        <div className="filter-grid fg-6">
          <div className="field">
            <label htmlFor="in-search">Search</label>
            <input id="in-search" placeholder="Search saved insights…" value={search}
              onChange={(e) => setSearch(e.target.value)} />
          </div>
          <MetaSelect id="in-client" label="Client" allLabel="All Clients"
            values={metaClients} value={client} onPick={setClient} />
          <div className="field">
            <label htmlFor="in-platform">Platform</label>
            <select id="in-platform" aria-label="Platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="">All Platforms</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <MetaSelect id="in-market" label="Market" allLabel="All Markets"
            values={metaMarkets} value={market} onPick={setMarket} />
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
      <div className="main-rail">
        <div className="rail-stack">
          <Panel title="Pinned Learnings" sub="Your most important insights, always within reach.">
            {cards.data ? (
              findings.pinned.filter(matchAxes).length ? (
                <div style={{ background: "#E5F5F2", borderRadius: 10, padding: 10 }}>
                  <div className="cards-3" style={{ gap: 10 }}>
                    {findings.pinned.filter(matchAxes).map((c) => (
                      <div className="cmp-card" key={c.creative_key} style={{ padding: 12 }}>
                        <h4 style={{ margin: "0 0 6px", fontSize: 13.5 }}>{signalTitle(c.finding?.primary_signal)}</h4>
                        <p className="panel-sub" style={{ margin: 0 }}>{c.finding?.diagnosis}</p>
                        <p className="panel-sub" style={{ margin: "4px 0 0" }}>{[c.platform, c.campaign].filter(Boolean).join(" · ")}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon="spark"
                  title="No saved insights yet"
                  text="Run AI Analyst or save a finding to start building your insight library."
                  action={<Link className="btn-soft" to="/analyst">Open AI Analyst</Link>}
                />
              )
            ) : <Skeleton height={120} />}
          </Panel>
          <Panel title={`Your Saved Insights (${savedCards.length})`}>
            {conversations === null || views === null ? <Skeleton height={160} /> : (
              savedCards.length ? (
                <div className="cards-3">
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
              ) : (
                <EmptyState
                  compact
                  icon="bookmark"
                  title="No saved insights yet"
                  text="Run AI Analyst or save a finding to start building your insight library."
                  action={<Link className="btn-soft" to="/analyst">Open AI Analyst</Link>}
                />
              )
            )}
          </Panel>
          {(itype === "All Types" || itype === "Creative Findings") && findings.rest.filter(matchAxes).length ? (
            <Panel title="Creative Findings">
              <div className="cards-3">
                {findings.rest.filter(matchAxes).slice(0, 6).map((c) => (
                  <div className="cmp-card" key={c.creative_key} style={{ padding: 14 }}>
                    <span className="badge-demo">Creative Finding</span>
                    <h4 style={{ margin: "8px 0 6px", fontSize: 13.5 }}>{signalTitle(c.finding?.primary_signal)}</h4>
                    <p className="panel-sub" style={{ margin: "0 0 8px" }}>{c.finding?.diagnosis}</p>
                    <Link className="btn-soft" to="/analyst">Open in Analyst →</Link>
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}
        </div>
        <div className="rail-stack">
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
              ) : <EmptyState compact icon="clock" title="No recent activity" text="Analyst conversations will appear here." />
            )}
          </Panel>
          <Panel title="Recommended Related Insights">
            {cards.data ? (
              findings.rest.filter(matchAxes).length ? (
              <div>
                {findings.rest.filter(matchAxes).slice(0, 4).map((c) => (
                  <div className="insight" key={c.creative_key}>
                    <span className="insight-ico" style={{ background: "#E5F5F2" }}>
                      <Icon name="spark" size={20} />
                    </span>
                    <div>
                      <h4>{signalTitle(c.finding?.primary_signal)}</h4>
                      <p>{c.finding?.recommended_iteration ?? c.finding?.diagnosis}</p>
                    </div>
                  </div>
                ))}
              </div>
              ) : <EmptyState text="No recommendations match the current filters." />
            ) : <Skeleton height={160} />}
          </Panel>
        </div>
      </div>
    </>
  );
}
