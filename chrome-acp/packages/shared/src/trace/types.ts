// Trace schema for the browser-activity viewer.
//
// A trace is the data channel; a frame is the picture channel. They are kept
// separate on purpose: every number the viewer shows (durations, actions,
// targets) is derived from the trace, never read back out of the pixels. That
// is what makes the frame source pluggable — a static screenshot, a recorded
// clip and a live screencast all satisfy the same interface.

/** Version tag so persisted traces stay readable after schema changes. */
export const TRACE_SCHEMA = "browser-trace/1";

/** Where a step's time was spent. */
export type TracePhaseName = "tool" | "gap";

export interface TracePhase {
  name: TracePhaseName;
  ms: number;
}

/**
 * What produced the step. `tool` is an agent tool call observed over ACP;
 * `user` is a browser action observed by the recorder content script.
 */
export type TraceStepKind = "tool" | "user";

export type TraceStepStatus = "running" | "complete" | "error" | "canceled";

export interface TraceStepTarget {
  /** Human-readable element/tool label, e.g. "browser_click" or "Where from?". */
  label: string;
  /** Element role when the source knows it (button, combobox, ...). */
  role?: string;
  text?: string;
}

export interface TraceStep {
  /** 1-based position in the run, used as the display index. */
  i: number;
  /** Absolute epoch ms when the step started. */
  tsStartMs: number;
  /** Absolute epoch ms when the step finished; null while still running. */
  tsEndMs: number | null;
  /** Measured duration; null when the start time was never observed. */
  durMs: number | null;
  kind: TraceStepKind;
  /** What was done: the tool title, or the recorded action kind. */
  action: string;
  status: TraceStepStatus;
  target?: TraceStepTarget;
  /** Typed value, when the source reports one. */
  value?: string;
  /** Whether the page visibly changed; null = not observed. */
  pageChanged: boolean | null;
  /** Key into the frame table for the frame captured after this step. */
  frameKey?: string;
  /** Key into the frame table for the frame captured before this step. */
  frameKeyBefore?: string;
  /** Correlation id (ACP toolCallId) so late updates can find the step. */
  correlationId?: string;
}

export interface TraceFrame {
  key: string;
  /** Absolute epoch ms the frame was captured at. */
  tsMs: number;
  /**
   * Whether this is the picture taken just before the step or just after it.
   * A before/after pair is what the change-region overlay diffs.
   */
  phase: "before" | "after";
  /** `data:` URL. Kept as a string so frames survive structured cloning. */
  dataUrl: string;
  /** Pixel size of the captured content area, the coordinate space for overlays. */
  width: number;
  height: number;
  url?: string;
  title?: string;
}

export interface TraceOverlayRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Overlay drawn on top of a frame. Coordinates are in frame pixels, so the
 * renderer can scale them by (displayed width / frame width).
 */
export interface TraceOverlay {
  kind: "target" | "changed";
  rect: TraceOverlayRect;
  label?: string;
}

export interface TraceMetrics {
  stepCount: number;
  /** Time covered by observed tool intervals, counting concurrent overlaps once. */
  toolMs: number;
  /** Run time not attributed to any step (model turns, orchestration). */
  gapMs: number;
  /** Steps whose own picture pair was compared and showed a change. */
  changedSteps: number;
  /** Compared picture pairs with no change above the diff threshold. */
  wastedSteps: number;
}

export interface TraceRun {
  schema: typeof TRACE_SCHEMA;
  /** Unique even when two requests start in the same millisecond. */
  runId?: string;
  startedAtMs: number;
  /** null while the run is still open. */
  endedAtMs: number | null;
  elapsedMs: number;
  url?: string;
  task?: string;
  model?: string;
  steps: TraceStep[];
  frames: TraceFrame[];
  metrics: TraceMetrics;
}

/**
 * Pluggable picture channel. Step C wires a buffered source fed by the
 * extension; step A swaps in a live screencast without touching the viewer.
 */
export interface FrameSource {
  readonly id: string;
  subscribe(listener: (frame: TraceFrame) => void): () => void;
  /** Most recent frame, or null before the first one arrives. */
  current(): TraceFrame | null;
  /** Frame captured after a given step, when the source keeps history. */
  frameFor(key: string): TraceFrame | null;
}
