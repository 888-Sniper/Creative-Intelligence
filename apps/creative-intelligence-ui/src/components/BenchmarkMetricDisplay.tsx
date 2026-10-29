import type { SourceCurrencyTranslator } from "../i18n/sourceCurrency";
import { benchmarkMetricValue, type BenchmarkRow } from "./benchmarkMetrics";
import { SourceCurrencyNote } from "./SourceCurrencyNote";
import { formatNativeMoney, knownSourceCurrency } from "./sourceCurrency";

export function BenchmarkMoneyCell({ row, metric, metricLabel, locale, unavailable, t }: {
  row: BenchmarkRow;
  metric: "cpm" | "cpa";
  metricLabel: string;
  locale: string;
  unavailable: string;
  t: SourceCurrencyTranslator;
}) {
  return <>
    {formatNativeMoney(benchmarkMetricValue(row, metric), knownSourceCurrency(row), locale, unavailable)}
    <SourceCurrencyNote source={row} preferred="" metric={metricLabel} t={t} />
  </>;
}

/** Keep unavailable slots and colours aligned with the visible group legend. */
export function BenchmarkMiniBars({ groups, format, unavailable, emptyLabel }: {
  groups: readonly { label: string; value: number | null | undefined }[];
  format: (value: number) => string;
  unavailable: string;
  emptyLabel: string;
}) {
  const values = groups.map((group) => typeof group.value === "number" && Number.isFinite(group.value)
    ? group.value : null);
  const measured = values.filter((value): value is number => value !== null);
  const max = Math.max(1, ...measured);
  const colors = ["#2F6FBE", "#0E9F6E", "#7C6BD6"];
  return <>
    {!measured.length ? <p className="panel-sub" role="note">{emptyLabel}</p> : null}
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 96, paddingTop: 14 }}>
      {groups.map((group, index) => {
        const value = values[index];
        return <div key={index} role="group" aria-label={group.label}
          style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--shell-navy)" }}>
            {value === null ? unavailable : format(value)}
          </span>
          {value === null ? null : <div aria-hidden="true" style={{ width: "70%",
            height: `${value === 0 ? 0 : Math.max(4, (value / max) * 72)}px`, borderRadius: "5px 5px 0 0",
            background: colors[index % colors.length] }} />}
        </div>;
      })}
    </div>
  </>;
}
