import { useEffect, useMemo, useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";

const KPI_LOWER_BETTER = ["cpa", "cpc", "cpm"];

/** A15: VTR is completions-based; the plays-based number reads Play rate. */
const KPI_LABELS: Record<string, string> = {
  vtr: "VTR (completed)",
  view_rate: "Play rate",
};
const kpiLabel = (k: string): string => KPI_LABELS[k] ?? k.toUpperCase();
const SUMMARY_METRICS = [
  "spend",
  "impressions",
  "clicks",
  "conversions",
  "cpm",
  "vtr",
  "view_rate",
  "ctr",
  "cpc",
  "cpa",
  "roas",
] as const;

interface CampaignGroup {
  n_ads: number;
  spend: number;
  ctr: number | null;
  cpc: number | null;
  cpa: number | null;
  [k: string]: number | null | undefined;
}

interface CreativeMetrics {
  cpa: number | null;
  ctr: number | null;
  roas: number | null;
  [k: string]: number | null | undefined;
}

interface CreativeAnnotation {
  hook_type?: string;
  creator_vs_branded?: string;
  duration_s?: number;
}

interface Creative {
  creative_key: string;
  name?: string;
  platform?: string;
  duration_s?: number;
  campaigns?: string[];
  metrics?: CreativeMetrics;
  annotation?: CreativeAnnotation | null;
}

interface RecoBullet {
  text: string;
}

interface RecoSection {
  title: string;
  bullets?: RecoBullet[];
}

interface RecoResponse {
  notice?: string;
  sections?: RecoSection[];
}

function rankVal(v: number | null | undefined, lower: boolean): number {
  if (v == null) return lower ? Infinity : -Infinity;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function kpi(v: number | null | undefined, money?: boolean): string {
  if (v == null) return "—";
  return (money ? "$" : "") + String(v);
}

export function CampaignsPage() {
  const { filters, scope } = useFilters();
  const scopeKey = scope.toString();
  const [groups, setGroups] = useState<Record<string, CampaignGroup> | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [creatives, setCreatives] = useState<Creative[] | null>(null);
  const [bench, setBench] = useState<Record<string, Record<string, number | null>> | null>(null);
  const [reco, setReco] = useState<RecoResponse | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const rankKpi = filters.kpi && filters.kpi !== "all" ? filters.kpi : "cpa";

  useEffect(() => {
    let live = true;
    setGroups(null);
    setListError(null);
    api<Record<string, CampaignGroup>>(
      "GET",
      scopedPath("/api/campaigns", scope),
    )
      .then((c) => {
        if (live) setGroups(c);
      })
      .catch((e: unknown) => {
        if (live) setListError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey]);

  const entries = useMemo(() => {
    if (!groups) return [];
    const needle = filters.campaign.trim().toLowerCase();
    let rows = Object.entries(groups).filter(([k]) =>
      !needle ? true : k.toLowerCase().includes(needle),
    );
    if (filters.kpi && filters.kpi !== "all") {
      const k = filters.kpi;
      const lower = KPI_LOWER_BETTER.includes(k);
      rows = rows.slice().sort((a, b) => {
        const va = rankVal(a[1][k], lower);
        const vb = rankVal(b[1][k], lower);
        return lower ? va - vb : vb - va;
      });
    }
    return rows;
  }, [groups, filters.campaign, filters.kpi]);

  useEffect(() => {
    if (!selected) return;
    let live = true;
    setDetailLoading(true);
    setDetailError(null);
    setCreatives(null);
    setBench(null);
    setReco(null);
    const k = rankKpi;
    Promise.all([
      api<Creative[]>("GET", scopedPath("/api/creatives", scope)),
      api<Record<string, Record<string, number | null>>>(
        "GET",
        scopedPath("/api/benchmarks?group_by=campaign", scope),
      ),
    ])
      .then(([rows, b]) => {
        if (!live) return;
        setCreatives(rows);
        setBench(b);
        return api<RecoResponse>(
          "GET",
          scopedPath(
            `/api/campaigns/recommendations?name=${encodeURIComponent(selected)}&rank_by=${encodeURIComponent(k)}`,
            scope,
          ),
        )
          .then((r) => {
            if (live) setReco(r);
          })
          .catch(() => {
            if (live) setReco(null);
          });
      })
      .catch((e: unknown) => {
        if (live) setDetailError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (live) setDetailLoading(false);
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, scopeKey, rankKpi]);

  const detail = useMemo(() => {
    if (!selected || !creatives || !bench) return null;
    const inCamp = creatives.filter((r) => (r.campaigns ?? []).includes(selected));
    if (!inCamp.length) return { empty: true as const };
    const k = rankKpi;
    const lower = KPI_LOWER_BETTER.includes(k);
    const ranked = inCamp.slice().sort((a, b) => {
      const va = rankVal(a.metrics?.[k], lower);
      const vb = rankVal(b.metrics?.[k], lower);
      return lower ? va - vb : vb - va;
    });
    const best = ranked[0];
    const worst = ranked[ranked.length - 1];
    const med = bench[selected] ? bench[selected][k] : null;
    const sym = ["spend", "cpa", "cpc", "cpm"].includes(k) ? "$" : "";
    const delta = med != null ? ` vs campaign-benchmark ${k.toUpperCase()} ${sym}${String(med)}` : "";
    const hooks: Record<string, number> = {};
    inCamp.forEach((r) => {
      const h = r.annotation?.hook_type;
      if (h) hooks[h] = (hooks[h] ?? 0) + 1;
    });
    const topHook = Object.entries(hooks).sort((a, b) => b[1] - a[1])[0];
    const summary = SUMMARY_METRICS.map((m) => ({
      m,
      v: String((bench[selected] ?? {})[m] ?? "—"),
    }));
    const rankList = ranked.map((r, i) => ({
      key: r.creative_key,
      label: r.name || r.creative_key,
      value: String(r.metrics?.[k] ?? "—"),
      index: i,
    }));
    const legacyReco: string[] = [
      `Scale: ${best.name || best.creative_key} leads on ${k.toUpperCase()} (${String(best.metrics?.[k] ?? "—")}).`,
    ];
    if (worst.creative_key !== best.creative_key) {
      legacyReco.push(
        `Review or replace: ${worst.name || worst.creative_key} trails on ${k.toUpperCase()} (${String(worst.metrics?.[k] ?? "—")}).`,
      );
    }
    if (topHook && inCamp.length > 1 && topHook[1] >= Math.ceil(inCamp.length / 2)) {
      legacyReco.push(
        `Hook concentration: ${topHook[1]} of ${inCamp.length} creatives use ${topHook[0]} — the next test should break from it.`,
      );
    }
    return { empty: false as const, ranked, best, worst, delta, topHook, summary, rankList, legacyReco };
  }, [selected, creatives, bench, rankKpi]);

  const perfCard = (r: Creative, tag: "Best" | "Watch" | "Only creative", cls: string) => {
    const a = r.annotation ?? {};
    const m: CreativeMetrics = r.metrics ?? { cpa: null, ctr: null, roas: null };
    return (
      <div className={`creative-card ${cls}`}>
        <div className="media">
          {a.hook_type || "untagged hook"} · {String(a.duration_s ?? r.duration_s ?? "—")}s
        </div>
        <div className="body">
          <div className="title">{r.name || r.creative_key}</div>
          <span className={`badge ${tag === "Watch" ? "bad" : "good"}`}>{tag}</span>
          <span style={{ fontSize: 13 }}>
            CPA {kpi(m.cpa as number | null, true)} · CTR {kpi(m.ctr as number | null)} · ROAS{" "}
            {kpi(m.roas as number | null)}
          </span>
          <span className="muted" style={{ fontSize: 13 }}>
            {a.creator_vs_branded || "—"} · {r.platform || "—"}
          </span>
        </div>
      </div>
    );
  };

  return (
    <>
      <h1 className="page-title">Campaigns</h1>
      <p className="page-sub">Select a campaign for best and worst creatives, benchmark comparison and learnings.</p>
      <div id="campaign-detail">
        {detailLoading && <p className="muted">Loading campaign detail…</p>}
        {detailError && <p className="muted">{detailError}</p>}
        {!detailLoading && !detailError && detail && detail.empty && selected && (
          <p className="muted">No creatives for {selected}.</p>
        )}
        {!detailLoading && !detailError && detail && !detail.empty && selected && (
          <div className="card">
            <h3>
              {selected}
              {detail.delta}
            </h3>
            <div className="cmp-grid">
              <div>
                <h4>Campaign totals (scoped)</h4>
                <table>
                  <tbody>
                    {detail.summary.map((s) => (
                      <tr key={s.m}>
                        <th>{kpiLabel(s.m)}</th>
                        <td>{s.v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h4>Creatives ranked by {rankKpi.toUpperCase()}</h4>
                <ul className="plain">
                  {detail.rankList.map((r) => (
                    <li key={r.key}>
                      #{r.index + 1} {r.label} — {rankKpi.toUpperCase()} {r.value}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="creative-grid" style={{ marginTop: 12 }}>
              {detail.best.creative_key === detail.worst.creative_key
                ? perfCard(detail.best, "Only creative", "selected")
                : perfCard(detail.best, "Best", "selected")}
              {detail.best.creative_key !== detail.worst.creative_key &&
                perfCard(detail.worst, "Watch", "")}
            </div>
            <div className="insight-panel">
              <h4>Creative learning</h4>
              <p style={{ margin: 0 }}>
                {detail.topHook
                  ? `${detail.topHook[0]} hooks lead ${detail.topHook[1]} of ${detail.ranked.length} creatives here`
                  : "No hook labels yet — annotate creatives to unlock learnings."}
              </p>
            </div>
            <div className="insight-panel">
              <h4>Recommendations</h4>
              {reco && Array.isArray(reco.sections) ? (
                <>
                  {reco.notice ? <p className="muted">{reco.notice}</p> : null}
                  {reco.sections.map((s) => (
                    <div key={s.title}>
                      <h4>{s.title}</h4>
                      <ul className="plain">
                        {(s.bullets ?? []).map((b) => (
                          <li key={b.text}>{b.text}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </>
              ) : (
                <ul className="plain">
                  {detail.legacyReco.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
      <div id="campaigns">
        {groups === null && !listError && <p className="muted">Loading campaigns…</p>}
        {listError && <p className="muted">{listError}</p>}
        {groups !== null && (
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Ads</th>
                <th>Spend</th>
                <th>CTR</th>
                <th>CPC</th>
                <th>CPA</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([k, g]) => (
                <tr key={k}>
                  <td>
                    <button type="button" className="link-btn" onClick={() => setSelected(k)}>
                      {k}
                    </button>
                  </td>
                  <td>{String(g.n_ads)}</td>
                  <td>${String(g.spend)}</td>
                  <td>{kpi(g.ctr)}</td>
                  <td>{kpi(g.cpc, true)}</td>
                  <td>{kpi(g.cpa, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
