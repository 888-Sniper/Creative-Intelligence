import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { applySavedView, VIEW_ROUTES, type SavedView } from "@/components/savedViews";
import { useFilters } from "@/state/FilterContext";
import { useLocale } from "@/i18n";
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



function dayLabel(fmtDate: (iso: string, opts?: Intl.DateTimeFormatOptions) => string, iso: string | null | undefined): string {
  if (!iso) return "";
  return fmtDate(iso, { month: "short", day: "numeric", year: "numeric" });
}

/** Finding titles come from backend signal copy (lowercase by
 *  convention): display them sentence-cased so cards read like titles
 *  without altering the underlying data. */
export function signalTitle(t: (key: string) => string, s: string | null | undefined): string {
  if (!s) return t("pageInsights.untitledFinding");
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
  const { t, tp, fmtDate } = useLocale();
  const navigate = useNavigate();
  const location = useLocation();
  /* Global header search deep-links here: ?find= pre-fills the search
   * so the hit is visible immediately. */
  const [search, setSearch] = useState(
    () => new URLSearchParams(location.search).get("find") ?? "");
  const [client, setClient] = useState("");
  const [platform, setPlatform] = useState("");
  const [market, setMarket] = useState("");
  const [itype, setItype] = useState("all");
  const [dateSaved, setDateSaved] = useState("all");
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
    if (dateSaved === "all") return true;
    return withinDays(iso, dateSaved === "d7" ? 7 : 30);
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

  const [deletingId, setDeletingId] = useState<number | null>(null);

  const deleteView = async (v: SavedView) => {
    setDeletingId(v.id);
    setSaveStatus("");
    try {
      await api("POST", "/api/views/delete", { id: v.id });
      setViews((prev) => (prev ?? []).filter((x) => x.id !== v.id));
      setSaveStatus(t("pageInsights.deleted", { name: v.name }));
    } catch (e) {
      setSaveStatus(e instanceof Error ? e.message : t("pageInsights.deleteFailed"));
    } finally {
      setDeletingId(null);
    }
  };

  const savedCards = useMemo(() => {
    // Item 31: saved-view cards carry no badge — only conversations
    // and findings keep theirs. The card keeps item, title,
    // description and Open Insight.
    const out: Array<{ key: string; badge: string; title: string; body: string; meta: string; to: string; apply?: SavedView }> = [];
    if (itype === "all" || itype === "conversations") {
      for (const c of conversations ?? []) {
        if (!matchDate(c.updated_at)) continue;
        const title = c.title || t("pageInsights.untitledConv");
        if (needle && !`${title} ${c.objective ?? ""}`.toLowerCase().includes(needle)) continue;
        out.push({
          key: `c-${c.id}`,
          badge: t("pageInsights.badgeConversation"),
          title,
          body: c.objective ? t("pageInsights.objectiveBody", { objective: c.objective }) : t("pageInsights.analystConvBody"),
          meta: c.updated_at ? t("pageInsights.updatedLabel", { date: dayLabel(fmtDate, c.updated_at) }) : "",
          to: "/analyst",
        });
      }
    }
    if (itype === "all" || itype === "views") {
      for (const v of views ?? []) {
        if (!matchViewAxes(v)) continue;
        if (needle && !v.name.toLowerCase().includes(needle)) continue;
        const axes = Object.keys(v.state?.filters ?? {}).length;
        const route = v.state?.view ? (VIEW_ROUTES[v.state.view] ?? v.state.view) : "";
        out.push({
          key: `v-${v.id}`,
          badge: "",
          title: v.name,
          body: t("pageInsights.setupBody", { across: axes ? tp("pageInsights.across", axes, { count: axes }) : "" }),
          meta: route ? t("pageInsights.opensLabel", { route }) : "",
          to: route || "/",
          apply: v,
        });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversations, views, itype, needle, dateSaved, client, platform, market, t, tp, fmtDate]);

  /* Shared restore: comparison deep link (full selection) when one
   * applies, otherwise the saved route — every stored scope axis and
   * the saved KPI travel along either way. */
  const applyView = (v: SavedView) => applySavedView(v, setFilter, navigate);

  const saveInsight = async () => {
    setSaving(true);
    setSaveStatus("");
    try {
      const name = t("pageInsights.saveName", {
        date: fmtDate(new Date().toISOString(), { month: "short", day: "numeric", year: "numeric" }),
      });
      await api("POST", "/api/views", {
        name,
        state: { filters: scopeBody(scope), kpi: filters.kpi, view: "main" },
      });
      const list = await api<SavedView[]>("GET", "/api/views");
      setViews(Array.isArray(list) ? list : []);
      setSaveStatus(t("pageInsights.savedMsg", { name }));
    } catch (e) {
      setSaveStatus(e instanceof Error ? e.message : t("pageInsights.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const recent = useMemo(() => (conversations ?? []).slice(0, 5), [conversations]);

  return (
    <>
      <PageHeader
        title={t("pageInsights.title")}
        sub={t("pageInsights.sub")}
        actions={(
          <LoadingButton type="button" className="btn-primary" loading={saving} loadingLabel={t("common.saving")} disabled={saving} onClick={() => void saveInsight()}>
            <Icon name="plus" size={16} /> {t("pageInsights.save")}
          </LoadingButton>
        )}
      />
      {saveStatus ? <p className="panel-sub" role="status" style={{ margin: "0 0 12px" }}>{saveStatus}</p> : null}
      <section className="panel" aria-label={t("pageInsights.filtersLabel")}>
        <div className="filter-grid fg-6">
          <div className="field">
            <label htmlFor="in-search">{t("pageInsights.search")}</label>
            <input id="in-search" placeholder={t("pageInsights.searchPlaceholder")} value={search}
              onChange={(e) => setSearch(e.target.value)} />
          </div>
          <MetaSelect id="in-client" label={t("filters.client")} allLabel={t("filters.allClients")}
            values={metaClients} value={client} onPick={setClient} />
          <div className="field">
            <label htmlFor="in-platform">{t("filters.platform")}</label>
            <select id="in-platform" aria-label={t("filters.platform")} value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="">{t("filters.allPlatforms")}</option>
              <option value="meta">Meta</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <MetaSelect id="in-market" label={t("filters.market")} allLabel={t("filters.allMarkets")}
            values={metaMarkets} value={market} onPick={setMarket} />
          <div className="field">
            <label htmlFor="in-type">{t("pageInsights.typeLabel")}</label>
            <select id="in-type" aria-label={t("pageInsights.typeLabel")} value={itype} onChange={(e) => setItype(e.target.value)}>
              {(["all", "conversations", "views", "findings"] as const).map((o) => <option key={o} value={o}>{t(`pageInsights.types.${o}`)}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="in-date">{t("pageInsights.dateLabel")}</label>
            <select id="in-date" aria-label={t("pageInsights.dateLabel")} value={dateSaved} onChange={(e) => setDateSaved(e.target.value)}>
              {(["all", "d7", "d30"] as const).map((o) => <option key={o} value={o}>{t(`pageInsights.dates.${o}`)}</option>)}
            </select>
          </div>
        </div>
      </section>
      <div className="main-rail">
        <div className="rail-stack">
          <Panel title={t("pageInsights.pinnedTitle")} sub={t("pageInsights.pinnedSub")}>
            {cards.data ? (
              findings.pinned.filter(matchAxes).length ? (
                <div style={{ background: "var(--shell-teal-soft)", borderRadius: 10, padding: 10 }}>
                  <div className="cards-3" style={{ gap: 10 }}>
                    {findings.pinned.filter(matchAxes).map((c) => (
                      <div className="cmp-card" key={c.creative_key} style={{ padding: 12 }}>
                        <h4 style={{ margin: "0 0 6px", fontSize: 13.5 }}>{signalTitle(t, c.finding?.primary_signal)}</h4>
                        <p className="panel-sub" style={{ margin: 0 }}>{c.finding?.diagnosis}</p>
                        <p className="panel-sub" style={{ margin: "4px 0 0" }}>{[c.platform, c.campaign].filter(Boolean).join(" · ")}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon="spark"
                  title={t("pageInsights.noPinnedTitle")}
                  text={t("pageInsights.noPinnedBody")}
                  action={<Link className="btn-soft" to="/analyst">{t("pageInsights.openAnalyst")}</Link>}
                />
              )
            ) : <Skeleton height={120} />}
          </Panel>
          <Panel title={t("pageInsights.savedTitle", { count: savedCards.length })} style={{ flex: "1 0 auto" }}>
            {conversations === null || views === null ? <Skeleton height={160} /> : (
              savedCards.length ? (
                <div className="cards-3">
                  {savedCards.map((s) => (
                    <div className="cmp-card" key={s.key} style={{ padding: 14 }}>
                      {s.badge ? <span className="badge-demo">{s.badge}</span> : null}
                      <h4 style={{ margin: s.badge ? "8px 0 6px" : "0 0 6px", fontSize: 13.5 }}>{s.title}</h4>
                      <p className="panel-sub" style={{ margin: 0 }}>{s.body}</p>
                      <p className="panel-sub" style={{ margin: "4px 0 8px" }}>{s.meta}</p>
                      {s.apply ? (
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <button type="button" className="btn-soft" onClick={() => applyView(s.apply as SavedView)}>
                            {t("pageInsights.openInsight")}
                          </button>
                          <button type="button" className="btn-outline"
                            disabled={deletingId === (s.apply as SavedView).id}
                            onClick={() => void deleteView(s.apply as SavedView)}
                            aria-label={t("pageInsights.deleteInsight", { name: s.title })}>
                            {deletingId === (s.apply as SavedView).id ? t("pageInsights.deleting") : t("pageInsights.delete")}
                          </button>
                        </div>
                      ) : (
                        <Link className="btn-soft" to={s.to}>{t("pageInsights.openInsight")}</Link>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  compact
                  icon="bookmark"
                  title={t("pageInsights.noPinnedTitle")}
                  text={t("pageInsights.noPinnedBody")}
                  action={<Link className="btn-soft" to="/analyst">{t("pageInsights.openAnalyst")}</Link>}
                />
              )
            )}
          </Panel>
          {(itype === "all" || itype === "findings") && findings.rest.filter(matchAxes).length ? (
            <Panel title={t("pageInsights.findingsTitle")}>
              <div className="cards-3">
                {findings.rest.filter(matchAxes).slice(0, 6).map((c) => (
                  <div className="cmp-card" key={c.creative_key} style={{ padding: 14 }}>
                    <span className="badge-demo">{t("pageInsights.findingBadge")}</span>
                    <h4 style={{ margin: "8px 0 6px", fontSize: 13.5 }}>{signalTitle(t, c.finding?.primary_signal)}</h4>
                    <p className="panel-sub" style={{ margin: "0 0 8px" }}>{c.finding?.diagnosis}</p>
                    <Link className="btn-soft" to="/analyst">{t("pageInsights.openInAnalyst")}</Link>
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}
        </div>
        <div className="rail-stack">
          <Panel title={t("pageInsights.activityTitle")}>
            {conversations === null ? <Skeleton height={160} /> : (
              recent.length ? (
                <div>
                  {recent.map((c) => (
                    <div className="insight" key={c.id}>
                      <span className="insight-ico">
                        <Icon name="chat" size={20} />
                      </span>
                      <div>
                        <h4>{c.title || t("pageInsights.untitledConv")}</h4>
                        <p>{c.updated_at ? dayLabel(fmtDate, c.updated_at) : ""}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState compact icon="clock" title={t("pageInsights.noActivityTitle")} text={t("pageInsights.noActivityBody")} />
            )}
          </Panel>
          <Panel title={t("pageInsights.relatedTitle")} style={{ flex: "1 0 auto" }}>
            {cards.data ? (
              findings.rest.filter(matchAxes).length ? (
              <div>
                {findings.rest.filter(matchAxes).slice(0, 4).map((c) => (
                  <div className="insight" key={c.creative_key}>
                    <span className="insight-ico">
                      <Icon name="spark" size={20} />
                    </span>
                    <div>
                      <h4>{signalTitle(t, c.finding?.primary_signal)}</h4>
                      <p>{c.finding?.recommended_iteration ?? c.finding?.diagnosis}</p>
                    </div>
                  </div>
                ))}
              </div>
              ) : (
              <div className="empty-center">
                <EmptyState compact verbatim icon="spark" title={t("pageInsights.noRelatedBody")} />
              </div>
              )
            ) : <Skeleton height={160} />}
          </Panel>
        </div>
      </div>
    </>
  );
}
