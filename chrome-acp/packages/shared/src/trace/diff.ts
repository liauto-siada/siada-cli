// Change-region detection: given the pictures before and after a step, work
// out which areas of the page actually changed.
//
// The core is a pure function over pixel buffers so it can be tested without a
// browser. Decoding a `data:` URL into pixels needs a canvas, so that lives in
// a thin, separate helper.
//
// Why pixel diffing rather than the recorder's mutation summary: the agent's
// own actions are not recorded by the content script, and a summary says what
// changed but not where. Two frames cover both agents and users, and give the
// viewer the "where" directly.

import type { TraceOverlayRect } from "./types";

export interface Pixels {
  /** RGBA bytes, row-major. */
  data: Uint8ClampedArray | Uint8Array;
  width: number;
  height: number;
}

export interface ChangedRegionsOptions {
  /** Cell edge in px. Bigger cells mean fewer, blockier regions. */
  cellSize?: number;
  /** Mean per-channel delta (0-255) at which a cell counts as changed. */
  threshold?: number;
  /** Upper bound on returned regions, largest first. */
  maxRegions?: number;
}

const DEFAULTS = {
  cellSize: 32,
  threshold: 24,
  maxRegions: 12,
} as const;

interface Run {
  row: number;
  startCol: number;
  endCol: number;
}

/**
 * Bounding rectangles of the changed areas, in frame pixels.
 *
 * Comparison is grid based: each cell's mean channel delta is compared against
 * `threshold`. That is deliberately coarse — it ignores antialiasing and
 * compression noise, which is exactly the kind of churn a viewer should not be
 * shown.
 *
 * An empty result is ambiguous on purpose, so callers must not read `[]` as
 * "nothing changed": it is also what an unusable pair (different or zero
 * dimensions) returns. The viewer therefore checks the picture sizes itself and
 * reports "unavailable" rather than "no change" when the two do not match.
 */
export function changedRegions(
  before: Pixels,
  after: Pixels,
  options: ChangedRegionsOptions = {},
): TraceOverlayRect[] {
  const cellSize = Math.max(1, options.cellSize ?? DEFAULTS.cellSize);
  const threshold = options.threshold ?? DEFAULTS.threshold;
  const maxRegions = Math.max(1, options.maxRegions ?? DEFAULTS.maxRegions);

  if (
    before.width !== after.width ||
    before.height !== after.height ||
    before.width === 0 ||
    before.height === 0
  ) {
    return [];
  }

  const { width, height } = before;
  const cols = Math.ceil(width / cellSize);
  const rows = Math.ceil(height / cellSize);

  const runs: Run[] = [];
  for (let row = 0; row < rows; row++) {
    let startCol = -1;
    for (let col = 0; col <= cols; col++) {
      const changed = col < cols && cellChanged(before, after, { row, col, cellSize, width, height, threshold });
      if (changed && startCol === -1) startCol = col;
      if (!changed && startCol !== -1) {
        runs.push({ row, startCol, endCol: col - 1 });
        startCol = -1;
      }
    }
  }

  return mergeRuns(runs, { cellSize, width, height, maxRegions });
}

interface CellArgs {
  row: number;
  col: number;
  cellSize: number;
  width: number;
  height: number;
  threshold: number;
}

function cellChanged(before: Pixels, after: Pixels, args: CellArgs): boolean {
  const { row, col, cellSize, width, height, threshold } = args;
  const x0 = col * cellSize;
  const y0 = row * cellSize;
  const x1 = Math.min(x0 + cellSize, width);
  const y1 = Math.min(y0 + cellSize, height);

  let delta = 0;
  let count = 0;
  for (let y = y0; y < y1; y++) {
    const rowOffset = y * width;
    for (let x = x0; x < x1; x++) {
      const i = (rowOffset + x) * 4;
      delta +=
        Math.abs((before.data[i] ?? 0) - (after.data[i] ?? 0)) +
        Math.abs((before.data[i + 1] ?? 0) - (after.data[i + 1] ?? 0)) +
        Math.abs((before.data[i + 2] ?? 0) - (after.data[i + 2] ?? 0));
      count += 3;
    }
  }
  if (count === 0) return false;
  return delta / count > threshold;
}

/**
 * Fold runs of changed cells into rectangles. Runs in consecutive rows that
 * cover the same columns are joined vertically, which turns a changed text
 * block or panel into one box instead of a stack of strips.
 */
function mergeRuns(
  runs: Run[],
  args: { cellSize: number; width: number; height: number; maxRegions: number },
): TraceOverlayRect[] {
  const { cellSize, width, height, maxRegions } = args;
  const open = new Map<string, { startRow: number; endRow: number; startCol: number; endCol: number }>();
  const rects: TraceOverlayRect[] = [];

  for (const run of runs) {
    const key = `${run.startCol}:${run.endCol}`;
    const previous = open.get(key);
    if (previous && previous.endRow === run.row - 1) {
      previous.endRow = run.row;
      continue;
    }
    if (previous) rects.push(toRect(previous, cellSize, width, height));
    open.set(key, {
      startRow: run.row,
      endRow: run.row,
      startCol: run.startCol,
      endCol: run.endCol,
    });
  }
  for (const rect of open.values()) rects.push(toRect(rect, cellSize, width, height));

  rects.sort((a, b) => b.w * b.h - a.w * a.h);
  return rects.slice(0, maxRegions);
}

function toRect(
  span: { startRow: number; endRow: number; startCol: number; endCol: number },
  cellSize: number,
  width: number,
  height: number,
): TraceOverlayRect {
  const x = span.startCol * cellSize;
  const y = span.startRow * cellSize;
  return {
    x,
    y,
    w: Math.min(width, (span.endCol + 1) * cellSize) - x,
    h: Math.min(height, (span.endRow + 1) * cellSize) - y,
  };
}
