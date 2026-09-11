import { useState } from "react";
import { api, scopedPath } from "@/api/client";
import { useFilters } from "@/state/FilterContext";

interface CompareAnnotation {
  hook_type?: string | null;
  creator_vs_branded?: string | null;
  edit_style?: string | null;
  status?: string | null;
}

interface CreativeSide {
  spend?: number | null;
  impressions?: number | null;
  clicks?: number | null;
  conversions?: number | null;
  cpm?: number | null;
  vtr?: number | null;
  view_rate?: number | null;
  ctr?: number | null;
  cpc?: number | null;
  cpa?: number | null;
  roas?: number | null;
  annotation?: CompareAnnotation | null;
}

/** A15: VTR is completions-based; the plays-based number reads Play rate. */
const KPI_LABELS: Record<string, string> = {
  vtr: "VTR (completed)",
  view_rate: "Play rate",
};
const kpiLabel = (k: string): string => KPI_LABELS[k] ?? k.toUpperCase();

interface AttributeRow {
  attribute: string;
  values?: Record<string, string | number | null>;
}

interface CompareResponse {
  keys: string[];
  ranking?: string[];
  winner?: string | null;
  rank_by?: string;
  scope?: string;
  why?: { top?: string | null; differences?: string[] };
  attributes?: AttributeRow[];
  [key: string]: unknown;
}

interface CampaignCompareResponse {
  kpis: Record<string, Record<string, number | null>>;
  ranking: string[];
  winner?: string | null;
  rank_by?: string;
  why?: { top?: string | null; differences?: string[] };
  scope?: string;
}

interface PeriodSide {
  label: string;
  from: string;
  to: string;
  n_ads: number;
  kpis: Record<string, number | null>;
}

interface PeriodResponse {
  a: PeriodSide;
  b: PeriodSide;
  delta: Record<string, number | null>;
  scope?: string;
}

const CREATIVE_RANKS = ["cpa", "cpm", "vtr", "ctr", "cpc", "roas"];
const CAMPAIGN_RANKS = ["cpa", "cpm", "ctr", "vtr", "roas"];
const CAMPAIGN_KPIS = [
  "spend",
  "impressions",
  "clicks",
  "conversions",
  "cpm",
  "vtr",
  "view_rate",
  "ctr",
  "cpa",
  "roas",
];
const PERIOD_KPIS = [
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
];
const MONEY_METRICS = new Set(["spend", "cpm", "cpc", "cpa"]);

/** Legacy kpi(): missing stays missing, money gets a $ prefix. */
function fmtKpi(value: unknown, money: boolean): string {
  if (value === null || value === undefined) return "—";
  return (money ? "$" : "") + String(value);
}

function fmtCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return String(value);
}

function sideOf(data: CompareResponse, key: string): CreativeSide {
  const v = data[key];
  if (typeof v === "object" && v !== null) return v as CreativeSide;
  return {};
}

export function ComparePage() {
  const { scope } = useFilters();

  const [keyA, setKeyA] = useState("");
  const [keyB, setKeyB] = useState("");
  const [keyExtra, setKeyExtra] = useState("");
  const [creativeRank, setCreativeRank] = useState("cpa");
  const [creativeKeys, setCreativeKeys] = useState<string[]>([]);
  const [creativeData, setCreativeData] = useState<CompareResponse | null>(null);
  const [creativeLoading, setCreativeLoading] = useState(false);
  const [creativeError, setCreativeError] = useState("");

  const [campaignInput, setCampaignInput] = useState("");
  const [campaignRank, setCampaignRank] = useState("cpa");
  const [campaignData, setCampaignData] = useState<CampaignCompareResponse | null>(null);
  const [campaignLoading, setCampaignLoading] = useState(false);
  const [campaignError, setCampaignError] = useState("");

  const [aFrom, setAFrom] = useState("");
  const [aTo, setATo] = useState("");
  const [bFrom, setBFrom] = useState("");
  const [bTo, setBTo] = useState("");
  const [periodData, setPeriodData] = useState<PeriodResponse | null>(null);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [periodError, setPeriodError] = useState("");

  async function compareCreatives(): Promise<void> {
    const keys = [keyA.trim(), keyB.trim(), ...keyExtra.split(",").map((s) => s.trim()).filter(Boolean)];
    const seen = [...new Set(keys.filter(Boolean))].slice(0, 6);
    if (seen.length < 2) {
      setCreativeData(null);
      setCreativeKeys([]);
      setCreativeError("Enter at least two creative keys (up to six).");
      return;
    }
    setCreativeLoading(true);
    setCreativeError("");
    try {
      const params = new URLSearchParams();
      seen.forEach((k) => params.append("key", k));
      params.set("rank_by", creativeRank);
      const r = await api<CompareResponse>("GET", scopedPath(`/api/compare?${params.toString()}`, scope));
      // Display the backend ranking order, never the entered key order:
      // columns and the winner both follow the selected rank_by.
      const ranked = Array.isArray(r.ranking) ? r.ranking : [];
      const sameSet =
        ranked.length === seen.length && ranked.every((k) => seen.includes(k));
      setCreativeKeys(sameSet ? ranked : seen);
      setCreativeData(r);
    } catch (e) {
      setCreativeData(null);
      setCreativeError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setCreativeLoading(false);
    }
  }

  async function compareCampaigns(): Promise<void> {
    setCampaignLoading(true);
    setCampaignError("");
    try {
      const params = new URLSearchParams();
      params.set("rank_by", campaignRank);
      const list = campaignInput.trim();
      if (list) params.set("campaigns", list);
      const r = await api<CampaignCompareResponse>(
        "GET",
        scopedPath(`/api/compare/campaigns?${params.toString()}`, scope),
      );
      setCampaignData(r);
    } catch (e) {
      setCampaignData(null);
      setCampaignError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setCampaignLoading(false);
    }
  }

  async function comparePeriods(): Promise<void> {
    if (!aFrom || !aTo || !bFrom || !bTo) {
      setPeriodError("Fill all four period dates.");
      return;
    }
    setPeriodLoading(true);
    setPeriodError("");
    try {
      const params = new URLSearchParams({ a_from: aFrom, a_to: aTo, b_from: bFrom, b_to: bTo });
      const r = await api<PeriodResponse>(
        "GET",
        scopedPath(`/api/compare/periods?${params.toString()}`, scope),
      );
      setPeriodData(r);
    } catch (e) {
      setPeriodData(null);
      setPeriodError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setPeriodLoading(false);
    }
  }

  // One winner, controlled by the selected rank_by: the backend pins
  // why.top to the rank winner, and this page reads winner everywhere.
  const creativeWinner = creativeData?.winner ?? null;
  const creativeRankBy = creativeData?.rank_by ?? creativeRank;
  const creativeHead = creativeWinner
    ? creativeKeys.length > 2
      ? `${creativeWinner} leads the comparison`
      : `Why ${creativeWinner} won`
    : "Insufficient data / no winner";
  const creativeRankLine = creativeData?.winner
    ? `Winner by ${creativeRankBy.toUpperCase()}: ${creativeData.winner} — order: ${creativeKeys.join(" · ")}`
    : "No winner: the selected KPI is unmeasurable for every side.";

  const campaignWinner = campaignData?.winner ?? null;
  const campaignRankBy = campaignData?.rank_by ?? campaignRank;
  const campaignRankLine = campaignWinner
    ? `Winner by ${campaignRankBy.toUpperCase()}: ${campaignWinner}`
    : "No winner: the selected KPI is unmeasurable for every campaign.";

  return (
    <>
      <h1 className="page-title">Compare</h1>
      <p className="page-sub">Two modes: creatives side-by-side, or campaigns ranked with why-analysis.</p>

      <div className="card">
        <label>
          Creative A <input placeholder="creative A key" value={keyA} onChange={(e) => setKeyA(e.target.value)} />
        </label>{" "}
        <label>
          Creative B <input placeholder="creative B key" value={keyB} onChange={(e) => setKeyB(e.target.value)} />
        </label>{" "}
        <label>
          More creatives{" "}
          <input
            placeholder="more keys, comma-separated (up to 4 more)"
            style={{ width: "60%" }}
            value={keyExtra}
            onChange={(e) => setKeyExtra(e.target.value)}
          />
        </label>{" "}
        <label>
          Rank by{" "}
          <select aria-label="Rank creatives by" value={creativeRank} onChange={(e) => setCreativeRank(e.target.value)}>
            {CREATIVE_RANKS.map((r) => (
              <option key={r} value={r}>
                {r.toUpperCase()}
              </option>
            ))}
          </select>
        </label>{" "}
        <button className="action" onClick={() => void compareCreatives()}>
          Compare creatives
        </button>
        <div className="muted" style={{ fontSize: 12 }}>
          GET /api/compare — 2 to 6 creatives, side by side with per-metric leaders. Every side is computed over
          the current top filter bar scope.
        </div>
      </div>

      <div className="card">
        <h3>Campaign compare</h3>
        <label>
          Campaigns{" "}
          <input
            placeholder="campaigns, comma-separated (blank = all)"
            style={{ width: "60%" }}
            value={campaignInput}
            onChange={(e) => setCampaignInput(e.target.value)}
          />
        </label>{" "}
        <label>
          Rank by{" "}
          <select aria-label="Rank campaigns by" value={campaignRank} onChange={(e) => setCampaignRank(e.target.value)}>
            {CAMPAIGN_RANKS.map((r) => (
              <option key={r} value={r}>
                {r.toUpperCase()}
              </option>
            ))}
          </select>
        </label>{" "}
        <button className="action" onClick={() => void compareCampaigns()}>
          Compare campaigns
        </button>
        <div className="muted" style={{ fontSize: 12 }}>
          GET /api/compare/campaigns — full KPI set plus why-analysis.
        </div>
      </div>

      <div id="cmp-out">
        {creativeLoading ? <p className="muted">Loading…</p> : null}
        {creativeError && !creativeLoading ? <p className="muted">{creativeError}</p> : null}
        {creativeData && !creativeLoading ? (
          <>
            <div className="cmp-grid">
              {creativeKeys.map((key) => {
                const d = sideOf(creativeData, key);
                const ann = d.annotation ?? {};
                return (
                  <div className="card" key={key}>
                    <h3>
                      {key || "(empty)"}
                      {creativeWinner === key && key ? " (top)" : ""}
                    </h3>
                    <div className="muted" style={{ fontSize: 12 }}>
                      Scope: {creativeData.scope ?? "All data"} — KPIs computed over scoped rows only
                    </div>
                    <table>
                      <tbody>
                        {(["spend", "impressions", "clicks", "conversions", "cpm", "vtr", "view_rate", "ctr", "cpc", "cpa", "roas"] as const).map(
                          (m) => (
                            <tr key={m}>
                              <th scope="row">{kpiLabel(m)}</th>
                              <td>{fmtKpi(d[m], MONEY_METRICS.has(m))}</td>
                            </tr>
                          ),
                        )}
                        <tr>
                          <th scope="row">Hook</th>
                          <td>{ann.hook_type ?? "—"}</td>
                        </tr>
                        <tr>
                          <th scope="row">Format</th>
                          <td>{ann.creator_vs_branded ?? "—"}</td>
                        </tr>
                        <tr>
                          <th scope="row">Edit style</th>
                          <td>{ann.edit_style ?? "—"}</td>
                        </tr>
                        <tr>
                          <th scope="row">Status</th>
                          <td>{ann.status ?? "—"}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                );
              })}
            </div>
            <div className="insight-panel">
              <h4>{creativeHead}</h4>
              <p className="muted" style={{ fontSize: 12 }}>
                Scope: {creativeData.scope ?? "All data"} · Ranked by {creativeRankBy.toUpperCase()}
              </p>
              <p>{creativeRankLine}</p>
              <ul className="plain">
                {(creativeData.why?.differences ?? []).map((d) => (
                  <li key={d}>{d}</li>
                ))}
                {(creativeData.why?.differences ?? []).length === 0 ? <li>—</li> : null}
              </ul>
            </div>
            {(creativeData.attributes ?? []).length > 0 ? (
              <div className="card">
                <h4>Attributes side-by-side</h4>
                <table>
                  <thead>
                    <tr>
                      <th>Attribute</th>
                      {creativeKeys.map((k) => (
                        <th key={k}>{k || "(empty)"}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(creativeData.attributes ?? []).map((row) => (
                      <tr key={row.attribute}>
                        <th scope="row">{row.attribute}</th>
                        {creativeKeys.map((k) => (
                          <td key={k}>{fmtCell(row.values?.[k])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      <div id="cmp-camp-out">
        {campaignLoading ? <p className="muted">Loading…</p> : null}
        {campaignError && !campaignLoading ? <p className="muted">{campaignError}</p> : null}
        {campaignData && !campaignLoading ? (
          <div className="card">
            <h4>Ranked by {campaignData.rank_by ?? ""}</h4>
            <p className="muted" style={{ fontSize: 12 }}>
              Scope: {campaignData.scope ?? "All data"}
            </p>
            <p>{campaignRankLine}</p>
            <table>
              <thead>
                <tr>
                  <th>Campaign</th>
                  {CAMPAIGN_KPIS.map((k) => (
                    <th key={k}>{kpiLabel(k)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(campaignData.ranking ?? []).map((c, i) => (
                  <tr key={c} className={i === 0 && campaignWinner ? "row-top" : undefined}>
                    <td>
                      {c}
                      {i === 0 && campaignWinner ? " (top)" : ""}
                    </td>
                    {CAMPAIGN_KPIS.map((k) => (
                      <td key={k}>{fmtCell(campaignData.kpis[c]?.[k])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="insight-panel">
              <h4>{campaignWinner ? `Why ${campaignWinner} won` : "Insufficient data / no winner"}</h4>
              <ul className="plain">
                {(campaignData.why?.differences ?? []).map((d) => (
                  <li key={d}>{d}</li>
                ))}
                {(campaignData.why?.differences ?? []).length === 0 ? <li>—</li> : null}
              </ul>
            </div>
          </div>
        ) : null}
      </div>

      <div className="card">
        <h3>Period comparison</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          Period A vs Period B over the identical scoped population (GET /api/compare/periods follows the top
          filter bar, except its own dates).
        </div>
        <div className="filter-grid">
          <label>
            A from
            <input type="date" aria-label="A from" value={aFrom} onChange={(e) => setAFrom(e.target.value)} />
          </label>
          <label>
            A to
            <input type="date" aria-label="A to" value={aTo} onChange={(e) => setATo(e.target.value)} />
          </label>
          <label>
            B from
            <input type="date" aria-label="B from" value={bFrom} onChange={(e) => setBFrom(e.target.value)} />
          </label>
          <label>
            B to
            <input type="date" aria-label="B to" value={bTo} onChange={(e) => setBTo(e.target.value)} />
          </label>
        </div>
        <div style={{ marginTop: 8 }}>
          <button className="action" onClick={() => void comparePeriods()}>
            Compare periods
          </button>
        </div>
        <div id="per-out" className="muted" style={{ marginTop: 8 }}>
          {periodLoading ? <p className="muted">Loading…</p> : null}
          {periodError && !periodLoading ? <p className="muted">{periodError}</p> : null}
          {periodData && !periodLoading ? (
            <>
              <p className="muted" style={{ fontSize: 12 }}>
                Scope: {periodData.scope ?? "All data"}
              </p>
              <table>
                <thead>
                  <tr>
                    <th>KPI</th>
                    <th>
                      {periodData.a.label} ({periodData.a.from}..{periodData.a.to}, n={periodData.a.n_ads})
                    </th>
                    <th>
                      {periodData.b.label} ({periodData.b.from}..{periodData.b.to}, n={periodData.b.n_ads})
                    </th>
                    <th>B−A</th>
                  </tr>
                </thead>
                <tbody>
                  {PERIOD_KPIS.map((m) => (
                    <tr key={m}>
                      <td>{kpiLabel(m)}</td>
                      <td>{fmtCell(periodData.a.kpis[m])}</td>
                      <td>{fmtCell(periodData.b.kpis[m])}</td>
                      <td>{fmtCell(periodData.delta[m])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : !periodLoading && !periodError ? (
            "—"
          ) : null}
        </div>
      </div>
    </>
  );
}
