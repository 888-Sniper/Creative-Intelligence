/** Inclusive UTC calendar bounds; invalid requests leave the current filters alone. */
export function presetDateRange(days: number, now = new Date()): {
  date_from: string;
  date_to: string;
} | null {
  if (!Number.isSafeInteger(days) || days <= 0 || !Number.isFinite(now.getTime())) {
    return null;
  }
  const from = new Date(now.getTime() - (days - 1) * 86400000);
  if (!Number.isFinite(from.getTime())) return null;
  return {
    date_from: from.toISOString().slice(0, 10),
    date_to: now.toISOString().slice(0, 10),
  };
}
