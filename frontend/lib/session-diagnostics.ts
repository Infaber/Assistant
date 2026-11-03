/** Keep the chart and statistics on the same bounded, chronological measurements. */
export function responseStatistics(raw: unknown) {
  const values: number[] = Array.isArray(raw) ? raw.filter((value): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0).slice(-100) : [];
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return {values, median: sorted.length ? sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2 : null, p95: sorted.length ? sorted[Math.ceil(sorted.length * .95) - 1] : null};
}
