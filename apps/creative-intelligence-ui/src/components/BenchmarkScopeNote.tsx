import type { BenchmarkReportingTranslator } from "../i18n/benchmarkReporting";
import type { BenchmarkResult, PooledBenchmarkMetric } from "./benchmarkPooling";

function numberFormatter(locale: string, options?: Intl.NumberFormatOptions): Intl.NumberFormat {
  try {
    return new Intl.NumberFormat(locale, options);
  } catch {
    return new Intl.NumberFormat("en", options);
  }
}

function shareLabel(share: number, locale: string, t: BenchmarkReportingTranslator): string {
  const percent = numberFormatter(locale, { style: "percent", maximumFractionDigits: 1 });
  // A rounded 0% or 100% must not imply absent or complete reporting.
  if (share > 0 && share < 0.001) return t("benchmarkReporting.lessThan", { percent: percent.format(0.001) });
  if (share < 1 && share > 0.999) return t("benchmarkReporting.moreThan", { percent: percent.format(0.999) });
  return percent.format(share);
}

export function BenchmarkScopeNote({ active, result, metric, locale, t, label, relativeComparison = false }: {
  active: boolean;
  result: BenchmarkResult;
  metric: PooledBenchmarkMetric;
  locale: string;
  t: BenchmarkReportingTranslator;
  label?: string;
  relativeComparison?: boolean;
}) {
  if (!active) return null;
  let reason: string | null = null;
  if (result.reason === "denominator") {
    const key = metric === "roas" ? "zeroSpend" : metric === "cpc" ? "zeroClicks"
      : metric === "cpa" ? "zeroConversions" : "zeroImpressions";
    reason = t(`benchmarkReporting.${key}`);
  } else if (result.reason) {
    reason = t(`benchmarkReporting.${result.reason}`);
  } else if (relativeComparison && result.value === 0) {
    reason = t("benchmarkReporting.zeroBaselineChange");
  }
  let coverage: string | null = null;
  if (result.coverage) {
    const percent = shareLabel(result.coverage.share, locale, t);
    if (result.coverage.kind === "spend") {
      coverage = t("benchmarkReporting.spend", { percent });
    } else {
      const counts = numberFormatter(locale);
      coverage = t("benchmarkReporting.rows", {
        reported: counts.format(result.coverage.reported), total: counts.format(result.coverage.total), percent,
      });
    }
  } else if (result.value != null) {
    coverage = t("benchmarkReporting.coverageUnavailable");
  }
  return (
    <div role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 12, lineHeight: 1.5 }}>
      {label && <p style={{ margin: "4px 0" }}><strong>{label}</strong></p>}
      {reason && <p style={{ margin: "4px 0" }}>{reason}</p>}
      {coverage && <p style={{ margin: "4px 0" }}>{coverage}</p>}
    </div>
  );
}
