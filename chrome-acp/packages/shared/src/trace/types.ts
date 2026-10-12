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
  /**
   * Chrome tab the picture came from, when the producer knows it. Pictures are
   * routed per tab, so a consumer can reject a frame that belongs to a tab
   * other than the one its run is bound to.
   */
  tabId?: number;
  /**
   * Agent session whose run the picture belongs to, when known. Live-view
   * frames are attributed server-side; a consumer drops frames stamped with a
   * session other than the one currently shown.
   */
  sessionId?: string;
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
  /**
   * Measured tool time: the union of the intervals observed for the run's
   * steps, so concurrent calls that overlap are counted once. A call whose
   * start-to-end stretch was never observed contributes nothing.
   */
  toolMs: number;
  /** Run time not covered by any observed step interval (model turns, orchestration). */
  gapMs: number;
  /** Completed steps that reported a page change. */
  changedSteps: number;
  /** Steps that finished without any page change. */
  wastedSteps: number;
}

export interface TraceRun {
  schema: typeof TRACE_SCHEMA;
  /**
   * Identity of this run, unique per beginRun() even when two runs start in the
   * same millisecond. Optional so traces persisted before it stay readable;
   * a view that does not get one falls back to `startedAtMs` as identity.
   */
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
