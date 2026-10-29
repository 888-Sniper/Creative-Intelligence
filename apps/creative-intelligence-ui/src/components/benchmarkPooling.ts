/** Canonical reporting populations supplied with each backend aggregate. */
export type PooledBenchmarkMetric = "ctr" | "cpc" | "cpm" | "cpa" | "roas";

export interface MetricComponent {
  numerator: number;
  denominator: number;
  reporting_rows: number;
  total_rows: number;
  total_spend?: number;
}

export interface BenchmarkMetadata {
  n_ads?: number;
  currency?: string | null;
  currencies?: string[];
  currency_known?: boolean;
  mixed_currency?: boolean;
  unknown_currency_contribution?: boolean;
  metric_components?: Partial<Record<PooledBenchmarkMetric, MetricComponent | null>>;
}

export type BenchmarkUnavailableReason = "empty" | "currency" | "metadata" | "unreported" | "denominator" | "invalid";

export interface BenchmarkCoverage {
  kind: "rows" | "spend";
  reported: number;
  total: number;
  share: number;
}

export interface BenchmarkResult {
  value: number | null;
  reason: BenchmarkUnavailableReason | null;
  coverage: BenchmarkCoverage | null;
}

function unavailable(reason: BenchmarkUnavailableReason, coverage: BenchmarkCoverage | null = null): BenchmarkResult {
  return { value: null, reason, coverage };
}

/** No FX conversion or currency inference is performed by the UI. */
export function hasComparableBenchmarkCurrency(groups: readonly BenchmarkMetadata[]): boolean {
  const populated = groups.filter((group) => group.n_ads !== 0);
  if (!populated.length) return false;
  let currency: string | undefined;
  for (const group of populated) {
    const code = group.currency?.trim().toUpperCase();
    if (!code || group.currency_known !== true || group.mixed_currency || group.unknown_currency_contribution) {
      return false;
    }
    if (group.currencies?.some((item) => item.trim().toUpperCase() !== code)) return false;
    if (currency !== undefined && code !== currency) return false;
    currency = code;
  }
  return true;
}

/** Pool actual reporting components, never rounded ratios or all-scope spend.
 * Missing component/currency metadata means unavailable until the corresponding
 * backend contract is present. CTR is a fraction; callers choose display units.
 */
export function pooledBenchmark(
  groups: readonly BenchmarkMetadata[], metric: PooledBenchmarkMetric,
): BenchmarkResult {
  const populated = groups.filter((group) => group.n_ads !== 0);
  if (!populated.length) return unavailable("empty");
  if (metric !== "ctr" && !hasComparableBenchmarkCurrency(populated)) return unavailable("currency");
  let numerator = 0;
  let denominator = 0;
  let reportingRows = 0;
  let totalRows = 0;
  let totalSpend = 0;
  let spendCoverageKnown = true;
  for (const group of populated) {
    const component = group.metric_components?.[metric];
    if (!component) return unavailable("metadata");
    if (!Number.isFinite(component.numerator) || !Number.isFinite(component.denominator)) {
      return unavailable("invalid");
    }
    if (!Number.isSafeInteger(component.reporting_rows) || !Number.isSafeInteger(component.total_rows)
      || component.reporting_rows < 0 || component.total_rows < component.reporting_rows) return unavailable("invalid");
    if (component.reporting_rows === 0 && (component.numerator !== 0 || component.denominator !== 0)) {
      return unavailable("invalid");
    }
    numerator += component.numerator;
    denominator += component.denominator;
    reportingRows += component.reporting_rows;
    totalRows += component.total_rows;
    if (typeof component.total_spend === "number" && Number.isFinite(component.total_spend)) {
      totalSpend += component.total_spend;
    } else {
      spendCoverageKnown = false;
    }
  }
  let coverage: BenchmarkCoverage | null = null;
  if (metric === "roas") {
    if (spendCoverageKnown && Number.isFinite(totalSpend) && totalSpend > 0
      && Number.isFinite(denominator) && denominator >= 0 && denominator <= totalSpend) {
      coverage = { kind: "spend", reported: denominator, total: totalSpend, share: denominator / totalSpend };
    }
  } else if (Number.isSafeInteger(reportingRows) && Number.isSafeInteger(totalRows) && totalRows > 0) {
    coverage = { kind: "rows", reported: reportingRows, total: totalRows, share: reportingRows / totalRows };
  }
  if (!reportingRows) return unavailable("unreported", coverage);
  if (denominator === 0) return unavailable("denominator", coverage);
  if (metric === "roas" && denominator < 0) return unavailable("invalid", coverage);
  const value = numerator / denominator * (metric === "cpm" ? 1000 : 1);
  return Number.isFinite(value) && Number.isFinite(denominator)
    ? { value, reason: null, coverage } : unavailable("invalid", coverage);
}

/** Compatibility wrapper for consumers that only need the numeric baseline. */
export function pooledBenchmarkValue(
  groups: readonly BenchmarkMetadata[], metric: PooledBenchmarkMetric,
): number | null {
  return pooledBenchmark(groups, metric).value;
}
