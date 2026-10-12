// Trace collection: turns ACP session updates into timed steps.
//
// Timing is measured client-side (wall clock at the moment an update arrives),
// so no backend change is needed to obtain per-action durations. The cost is
// that the numbers include transport latency — acceptable for a viewer whose
// job is showing where time went, and documented here rather than hidden.
//
// A run is one turn of one session: the caller begins it when a prompt goes
// out and ends it on the protocol's terminal events (prompt_complete, error,
// cancel, dropped connection). Nothing else may invent an end, or the viewer's
// "live" badge would be a claim nobody can check.

import type { SessionUpdate } from "../acp/types";
import {
  TRACE_SCHEMA,
  type TraceFrame,
  type TraceMetrics,
  type TraceRun,
  type TraceStep,
  type TraceStepStatus,
} from "./types";

export interface TraceCollectorOptions {
  /** Injectable clock, so tests get deterministic timings. */
  now?: () => number;
  /** Upper bound on retained frames; oldest are dropped. */
  maxFrames?: number;
  /** Called whenever the run changes, so views can re-render. */
  onChange?: (run: TraceRun) => void;
}

/** Metadata for a fresh run. */
export interface RunMeta {
  url?: string;
  task?: string;
  model?: string;
}

/** Why a run stopped. Determines the status of steps left open. */
export type RunEndReason = "complete" | "canceled" | "error";

/**
 * What happened to a frame the collector was handed.
 *
 * `step` means the frame was tied to a specific step by its correlation id;
 * `standalone` means it was kept as a picture of the run (the viewport's
 * "latest picture") without being attributed to any step. Nothing in the
 * collector guesses an attribution: a frame can only land on a step when its
 * correlation id is one the collector has actually seen, so "this step's own
 * picture" is a claim with an observation behind it.
 */
export type FrameAttachment =
  | { kind: "step"; stepIndex: number; phase: TraceFrame["phase"] }
  | { kind: "standalone"; reason: "unmatched-correlation" | "no-correlation" };

/** Map an ACP tool-call status onto our closed set. */
export function mapToolStatus(status: string | undefined): TraceStepStatus {
  switch (status) {
    case "completed":
      return "complete";
    case "failed":
      return "error";
    case "cancelled":
    case "canceled":
      return "canceled";
    default:
      return "running";
  }
}

function isTerminal(status: TraceStepStatus): boolean {
  return status !== "running";
}

/**
 * Id source for runs. A wall-clock timestamp cannot tell two runs apart — a new
 * prompt can begin in the same millisecond the previous run did — so every
 * beginRun() takes the next value, and views can use it as run identity.
 */
let runIdCounter = 0;

function nextRunId(): string {
  runIdCounter += 1;
  return `run-${runIdCounter}`;
}

/** Total length of a set of half-open intervals; overlaps are counted once. */
function mergedIntervalMs(intervals: Array<readonly [number, number]>): number {
  if (intervals.length === 0) return 0;
  const sorted = [...intervals].sort((a, b) => a[0] - b[0]);
  let [start, end] = sorted[0]!;
  let total = 0;
  for (const [nextStart, nextEnd] of sorted.slice(1)) {
    if (nextStart > end) {
      total += end - start;
      start = nextStart;
      end = nextEnd;
    } else if (nextEnd > end) {
      end = nextEnd;
    }
  }
  return total + (end - start);
}

export class TraceCollector {
  private readonly now: () => number;
  private readonly maxFrames: number;
  private listeners = new Set<(run: TraceRun) => void>();

  /** Identity of the current run; changes on every beginRun(). */
  private runId: string;
  private startedAtMs: number;
  private endedAtMs: number | null = null;
  private url: string | undefined;
  private task: string | undefined;
  private model: string | undefined;

  private steps: TraceStep[] = [];
  private frames: TraceFrame[] = [];
  private openByCorrelation = new Map<string, TraceStep>();

  constructor(options: TraceCollectorOptions = {}) {
    this.now = options.now ?? (() => Date.now());
    this.maxFrames = options.maxFrames ?? 200;
    this.runId = nextRunId();
    this.startedAtMs = this.now();
    if (options.onChange) this.listeners.add(options.onChange);
  }

  /** Start (or restart) a run. Any previous steps and frames are discarded. */
  beginRun(meta: RunMeta = {}): void {
    // A fresh identity even when the clock has not moved on: a view must be
    // able to tell this run from the previous one, milliseconds or not.
    this.runId = nextRunId();
    this.startedAtMs = this.now();
    this.endedAtMs = null;
    this.url = meta.url;
    this.task = meta.task;
    this.model = meta.model;
    this.steps = [];
    this.frames = [];
    this.openByCorrelation.clear();
    this.emit();
  }

  /**
   * Set up an empty run for a session where no turn has started yet. The run
   * has no steps and is already finished, so the viewer does not badge a
   * session "live" before there is anything to be live about; the first prompt
   * then calls beginRun().
   */
  prepareRun(meta: RunMeta = {}): void {
    this.beginRun(meta);
    this.endRun("complete");
  }

  /**
   * Freeze the elapsed clock; the viewer keeps rendering the captured run.
   * Only steps the stream left open are closed with `reason`: a step that
   * already reported its own terminal update keeps that status and duration,
   * so a canceled or failed turn cannot rewrite evidence the stream gave us,
   * nor can it make a failed call look successful.
   */
  endRun(reason: RunEndReason = "complete"): void {
    if (this.endedAtMs !== null) return;
    this.endedAtMs = this.now();
    for (const step of this.steps) {
      if (step.status === "running") this.closeStep(step, reason);
    }
    this.emit();
  }

  addSessionUpdate(update: SessionUpdate): void {
    if (update.sessionUpdate === "tool_call") {
      this.openStep(
        update.toolCallId,
        update.title,
        update.status,
        update.rawInput,
      );
      return;
    }
    if (update.sessionUpdate === "tool_call_update") {
      const step = this.openByCorrelation.get(update.toolCallId);
      if (!step) return;
      if (update.title) step.action = update.title;
      const status = update.status ? mapToolStatus(update.status) : step.status;
      if (isTerminal(status)) {
        this.closeStep(step, status);
      } else {
        step.status = status;
      }
      this.emit();
    }
  }

  /**
   * Attach a frame to the run.
   *
   * A frame only lands on a step when its `correlationId` is that step's own id
   * — the observable link the producer reports. An id that matches no step is
   * evidence that the frame belongs to something the collector has not seen
   * (frame producers and ACP tool calls number their work differently), and
   * hanging it on whichever step happens to be running would invent a
   * before/after pair. Such a frame stays a standalone picture of the run: the
   * viewport still shows it as the latest picture, and the viewer says no step
   * owns it.
   *
   * A `before` frame fills the step's before slot, which is what the change
   * overlay diffs against.
   */
  addFrame(frame: TraceFrame, correlationId?: string): FrameAttachment {
    this.frames.push(frame);
    if (this.frames.length > this.maxFrames) {
      const dropped = this.frames.splice(0, this.frames.length - this.maxFrames);
      const droppedKeys = new Set(dropped.map((f) => f.key));
      for (const step of this.steps) {
        if (step.frameKey && droppedKeys.has(step.frameKey)) delete step.frameKey;
        if (step.frameKeyBefore && droppedKeys.has(step.frameKeyBefore)) {
          delete step.frameKeyBefore;
        }
      }
    }

    const target =
      correlationId === undefined
        ? undefined
        : this.steps.find((s) => s.correlationId === correlationId);

    if (!target) {
      this.emit();
      return {
        kind: "standalone",
        reason: correlationId === undefined ? "no-correlation" : "unmatched-correlation",
      };
    }

    if (frame.phase === "before") {
      target.frameKeyBefore = frame.key;
    } else {
      target.frameKey = frame.key;
    }

    this.emit();
    return { kind: "step", stepIndex: target.i, phase: frame.phase };
  }

  /**
   * Record the verdict of an actual picture comparison for a step: `changed` is
   * true when the pixel diff of the step's own before/after pair found changed
   * areas. Until this is called the step's `pageChanged` stays null ("not
   * observed"), which is what the viewer shows — no diff, no claim.
   *
   * @returns whether a step with that correlation id exists.
   */
  reportPageChange(correlationId: string, changed: boolean): boolean {
    const step = this.steps.find((s) => s.correlationId === correlationId);
    if (!step) return false;
    if (step.pageChanged === changed) return true;
    step.pageChanged = changed;
    this.emit();
    return true;
  }

  /** Correlation id shared by concurrent tool calls; used to match frames. */
  private openStep(
    toolCallId: string,
    title: string,
    status: string | undefined,
    rawInput: Record<string, unknown> | undefined,
  ): void {
    const existing = this.openByCorrelation.get(toolCallId);
    if (existing) {
      this.closeStep(existing, mapToolStatus(status));
      return;
    }

    const mapped = mapToolStatus(status);
    const step: TraceStep = {
      i: this.steps.length + 1,
      tsStartMs: this.now(),
      tsEndMs: null,
      durMs: null,
      kind: "tool",
      action: title || toolCallId,
      status: mapped,
      pageChanged: null,
      correlationId: toolCallId,
      ...describeToolInput(rawInput),
    };

    if (isTerminal(mapped)) {
      // The agent reported the finished call in one shot, so there is no
      // observed start; leave durMs null rather than inventing a duration.
      step.tsEndMs = step.tsStartMs;
      step.status = mapped;
    } else {
      this.openByCorrelation.set(toolCallId, step);
    }

    this.steps.push(step);
    this.emit();
  }

  private closeStep(step: TraceStep, status: TraceStepStatus): void {
    // A terminal status is final. Whatever a caller wants to record — a
    // run-end reason, a contradictory late event — the step already carries
    // the outcome the stream reported, with the duration measured then, and
    // rewriting it would replace an observation with a guess.
    if (isTerminal(step.status)) return;
    if (step.correlationId) this.openByCorrelation.delete(step.correlationId);
    const endedAt = this.now();
    if (step.tsEndMs === null) step.tsEndMs = endedAt;
    if (step.durMs === null && step.status === "running") {
      step.durMs = Math.max(0, step.tsEndMs - step.tsStartMs);
    }
    step.status = status;
    this.openByCorrelation.delete(step.correlationId ?? "");
  }

  snapshot(): TraceRun {
    const endedAtMs = this.endedAtMs;
    // One clock read defines both the elapsed time and the end of a still-open
    // step's interval, so the two can never disagree within one snapshot.
    const runEndMs = endedAtMs ?? this.now();
    const elapsedMs = Math.max(0, runEndMs - this.startedAtMs);
    return {
      schema: TRACE_SCHEMA,
      runId: this.runId,
      startedAtMs: this.startedAtMs,
      endedAtMs,
      elapsedMs,
      url: this.url,
      task: this.task,
      model: this.model,
      steps: this.steps.map((step) => ({ ...step })),
      frames: [...this.frames],
      metrics: this.metrics(elapsedMs, runEndMs),
    };
  }

  /**
   * Time ledger for the run. `toolMs` is the union of the intervals the stream
   * actually observed, not the sum of step durations: concurrent tool calls
   * overlap, so adding their durations up would claim more time than the run
   * has and hide the time spent outside any tool.
   *
   * An interval is only counted when its start and end were observed: a step
   * still running is measured to the run's end (`now` while the run is open),
   * while a call the agent reported already finished in one shot has no
   * observed start-to-end stretch and contributes nothing rather than a
   * guessed duration.
   */
  private metrics(elapsedMs: number, runEndMs: number): TraceMetrics {
    const intervals: Array<readonly [number, number]> = [];
    for (const step of this.steps) {
      if (step.durMs === null && step.status !== "running") continue;
      const start = Math.max(this.startedAtMs, step.tsStartMs);
      const end = Math.min(runEndMs, step.tsEndMs ?? runEndMs);
      if (end > start) intervals.push([start, end]);
    }
    const toolMs = mergedIntervalMs(intervals);

    let changedSteps = 0;
    let wastedSteps = 0;
    for (const step of this.steps) {
      // Only steps whose own before/after pair was actually compared have a
      // verdict; the rest stay at null and are counted in neither bucket.
      if (step.pageChanged === true) changedSteps++;
      if (step.pageChanged === false) wastedSteps++;
    }
    return {
      stepCount: this.steps.length,
      toolMs,
      gapMs: Math.max(0, elapsedMs - toolMs),
      changedSteps,
      wastedSteps,
    };
  }

  subscribe(listener: (run: TraceRun) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private emit(): void {
    if (this.listeners.size === 0) return;
    const run = this.snapshot();
    for (const listener of this.listeners) listener(run);
  }
}

/**
 * Best-effort extraction of a display target/value from a tool call's raw
 * input. The agent decides what it sends, so every field is optional.
 */
function describeToolInput(
  rawInput: Record<string, unknown> | undefined,
): Pick<TraceStep, "target" | "value"> {
  if (!rawInput) return {};
  const text = typeof rawInput.text === "string" ? rawInput.text : undefined;
  const selector =
    typeof rawInput.selector === "string" ? rawInput.selector : undefined;
  const label =
    text ??
    selector ??
    (typeof rawInput.url === "string" ? rawInput.url : undefined);
  if (!label) {
    return text === undefined ? {} : { value: text };
  }
  return {
    target: { label },
    ...(text !== undefined ? { value: text } : {}),
  };
}
