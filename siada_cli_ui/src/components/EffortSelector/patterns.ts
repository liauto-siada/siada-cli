/**
 * Effort particle pattern — a single diamond that grows with the level.
 *
 * All levels share one shape; higher effort renders a larger diamond, so the
 * particle cloud scales up as the selection moves right on the ruler.
 */

/** Max diamond radius (rows) that fits the canvas height. */
const MAX_RADIUS = 3;

/**
 * Build a filled diamond bitmap of the given radius. X is stretched ×2 to
 * compensate for terminal cells being taller than wide.
 */
function diamond(radius: number): string[] {
  const rows: string[] = [];
  for (let dy = -radius; dy <= radius; dy++) {
    const half = (radius - Math.abs(dy)) * 2;
    rows.push(' '.repeat(radius * 2 - half) + '█'.repeat(half * 2 + 1));
  }
  return rows;
}

/** Pattern for a level: diamond radius grows from 1 to MAX_RADIUS. */
export function patternForLevel(level: string, index: number, count: number): string[] {
  const t = count > 1 ? index / (count - 1) : 1;
  return diamond(1 + Math.round(t * (MAX_RADIUS - 1)));
}
