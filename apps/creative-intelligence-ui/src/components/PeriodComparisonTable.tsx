import type { SourceCurrencyTranslator } from "../i18n/sourceCurrency";
import { formatNativeMoney, knownSourceCurrency, type SourceCurrency } from "./sourceCurrency";

export const PERIOD_METRICS = ["spend", "impressions", "clicks", "conversions", "cpm", "vtr",
  "view_rate", "ctr", "cpc", "cpa", "roas"] as const;
export type PeriodMetric = (typeof PERIOD_METRICS)[number];
const MONEY = new Set<PeriodMetric>(["spend", "cpm", "cpc", "cpa"]);

export interface PeriodSide {
  label: string;
  from: string;
  to: string;
  n_ads: number;
  kpis: SourceCurrency & Partial<Record<PeriodMetric, number | null>>;
}

export interface PeriodResponse {
  a: PeriodSide;
  b: PeriodSide;
  delta: Partial<Record<PeriodMetric, number | null>>;
  delta_reasons?: Partial<Record<PeriodMetric, string>>;
  scope?: string;
}

/** Pure presentation: native side values and explicitly comparable B-minus-A. */
export function PeriodComparisonTable({ data, locale, headings, metricLabel, formatNonMoney, t }: {
  data: PeriodResponse;
  locale: string;
  headings: { metric: string; delta: string; unavailable: string };
  metricLabel: (metric: PeriodMetric) => string;
  formatNonMoney: (metric: PeriodMetric, value: number | null | undefined) => string;
  t: SourceCurrencyTranslator;
}) {
  const aCurrency = knownSourceCurrency(data.a.kpis);
  const bCurrency = knownSourceCurrency(data.b.kpis);
  const sameCurrency = aCurrency !== null && aCurrency === bCurrency;
  const moneyUnavailable = !sameCurrency || [...MONEY].some((metric) => data.delta_reasons?.[metric]);
  const format = (metric: PeriodMetric, value: number | null | undefined, currency: string | null) =>
    MONEY.has(metric) ? formatNativeMoney(value, currency, locale, headings.unavailable)
      : formatNonMoney(metric, value);
  const delta = (metric: PeriodMetric) => {
    const value = data.delta[metric];
    if (MONEY.has(metric) && (!sameCurrency || data.delta_reasons?.[metric])) return headings.unavailable;
    if (value == null || !Number.isFinite(value)) return headings.unavailable;
    if (value === 0) return format(metric, 0, aCurrency);
    return `${value > 0 ? "+" : "−"}${format(metric, Math.abs(value), aCurrency)}`;
  };
  return (
    <>
      {[data.a, data.b].map((side, index) => side.n_ads > 0 && !knownSourceCurrency(side.kpis) ? (
        <p key={index} className="panel-sub" role="note">
          {t(side.kpis.mixed_currency ? "sourceCurrency.mixed" : "sourceCurrency.unknown", { metric: side.label })}
        </p>
      ) : null)}
      {moneyUnavailable ? <p className="panel-sub" role="note">{t("sourceCurrency.period")}</p> : null}
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th scope="col">{headings.metric}</th>
              <th scope="col">{data.a.label} ({data.a.from}…{data.a.to}, n={data.a.n_ads})</th>
              <th scope="col">{data.b.label} ({data.b.from}…{data.b.to}, n={data.b.n_ads})</th>
              <th scope="col" className="num">{headings.delta}</th>
            </tr>
          </thead>
          <tbody>
            {PERIOD_METRICS.map((metric) => (
              <tr key={metric}>
                <th scope="row">{metricLabel(metric)}</th>
                <td>{format(metric, data.a.kpis[metric], aCurrency)}</td>
                <td>{format(metric, data.b.kpis[metric], bCurrency)}</td>
                <td className="num">{delta(metric)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
