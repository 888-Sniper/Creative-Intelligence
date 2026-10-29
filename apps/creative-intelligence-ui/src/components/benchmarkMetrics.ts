import { sharedSourceCurrency, type SourceCurrency } from "./sourceCurrency";

export interface BenchmarkRow extends SourceCurrency {
  spend: number; impressions: number; clicks: number; conversions: number;
  revenue: number; ctr: number | null; cpc: number | null; cpa: number | null;
  roas: number | null; n_ads: number;
  /** Older payloads without canonical CPM remain unavailable. */
  cpm?: number | null;
}

export type BenchmarkMetric = "cpm" | "ctr" | "cpa" | "roas";

/** Preserve canonical availability; raw monetary totals are not ratio inputs. */
export function benchmarkMetricValue(row: BenchmarkRow, metric: BenchmarkMetric): number | null {
  const raw = row[metric];
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  const value = metric === "ctr" ? raw * 100 : raw;
  return Number.isFinite(value) ? value : null;
}

/** Missing groups keep their positions; available costs require common units. */
export function benchmarkChartData(rows: readonly BenchmarkRow[], metric: BenchmarkMetric) {
  const values = rows.map((row) => benchmarkMetricValue(row, metric));
  if (metric !== "cpm" && metric !== "cpa") {
    return { values, currency: null, currencyUnavailable: false };
  }
  const valuedRows = rows.filter((_, index) => values[index] !== null);
  const currency = sharedSourceCurrency(valuedRows);
  const currencyUnavailable = valuedRows.length > 0 && currency === null;
  return { values: currencyUnavailable ? values.map(() => null) : values, currency, currencyUnavailable };
}
