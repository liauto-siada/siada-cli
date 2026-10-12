// Display formatting for trace numbers. Kept next to the schema so the viewer
// and any exported report render durations identically.

/** Short duration, e.g. 341 -> "341 ms", 1240 -> "1.24 s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Run elapsed time in seconds, e.g. "0.03 s" / "7.09 s". */
export function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Percentage of a total, clamped to 0..100. */
export function shareOfTotal(part: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(100, (part / total) * 100));
}
