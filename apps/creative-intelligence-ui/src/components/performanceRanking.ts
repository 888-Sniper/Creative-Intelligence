export type PerformanceMetric = "ctr" | "roas" | "cpa" | "cpc";

export function isMeasured(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Missing measurements cannot become a zero-valued winning benchmark. */
export function topPerformanceValue(
  values: readonly (number | null | undefined)[], metric: PerformanceMetric,
): number | null {
  const measured = values.filter(isMeasured);
  if (!measured.length) return null;
  return metric === "cpa" || metric === "cpc" ? Math.min(...measured) : Math.max(...measured);
}

interface CreativePerformance {
  creative_key: string;
  metrics?: { roas?: number | null; ctr?: number | null } | null;
}

function descendingMeasured(a: number | null | undefined, b: number | null | undefined): number {
  if (!isMeasured(a)) return isMeasured(b) ? 1 : 0;
  if (!isMeasured(b)) return -1;
  return b - a;
}

/** Known ROAS first, then CTR; key order makes equal measurements deterministic. */
export function selectTopCreatives<T extends CreativePerformance>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => (
    descendingMeasured(a.metrics?.roas, b.metrics?.roas)
    || descendingMeasured(a.metrics?.ctr, b.metrics?.ctr)
    || (a.creative_key < b.creative_key ? -1 : a.creative_key > b.creative_key ? 1 : 0)
  )).slice(0, 4);
}
