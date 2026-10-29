/** Daily trend values prefer canonical backend ratios when present. */

export interface DailyPointLike {
  spend: number;
  revenue: number;
  impressions: number;
  clicks: number;
  conversions: number;
  cpa?: number | null;
  cpm?: number | null;
  roas?: number | null;
}

/**
 * Canonical daily cpa/cpm/roas (including explicit null for mixed or
 * unreported days) win over client recomputation. Payloads without the
 * canonical keys fall back to the legacy same-day arithmetic. CTR is
 * dimensionless and always same-day clicks/impressions.
 */
export function dailyMetricValue(
  point: DailyPointLike, metric: string,
): number | null {
  if (metric === "roas" || metric === "cpa" || metric === "cpm") {
    const canonical = point[metric];
    if (canonical !== undefined) return canonical ?? null;
    if (metric === "roas") return point.spend ? point.revenue / point.spend : null;
    if (metric === "cpa") {
      return point.conversions ? point.spend / point.conversions : null;
    }
    return point.impressions ? (point.spend / point.impressions) * 1000 : null;
  }
  if (metric === "ctr") {
    return point.impressions ? (point.clicks / point.impressions) * 100 : null;
  }
  const raw = Number(
    (point as unknown as Record<string, unknown>)[metric] ?? 0);
  return Number.isFinite(raw) ? raw : null;
}
