// Trace collection: turns ACP session updates into timed steps.
//
// Timing is measured client-side (wall clock at the moment an update arrives),
// so no backend change is needed to obtain per-action durations. The cost is
// that the numbers include transport latency — acceptable for a viewer whose
// job is showing where time went, and documented here rather than hidden.

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

export class TraceCollector {
  private readonly now: () => number;
  private readonly maxFrames: number;
  private listeners = new Set<(run: TraceRun) => void>();

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
    this.startedAtMs = this.now();
    if (options.onChange) this.listeners.add(options.onChange);
  }

  /** Start (or restart) a run. Any previous steps and frames are discarded. */
  beginRun(meta: { url?: string; task?: string; model?: string } = {}): void {
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

  /** Freeze the elapsed clock; the viewer keeps rendering the captured run. */
  endRun(): void {
    if (this.endedAtMs !== null) return;
    this.endedAtMs = this.now();
    for (const step of this.steps) this.closeStep(step, "complete");
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
   * Attach a frame to the run. When a correlation id is given the frame lands
   * on that specific step; otherwise it prefers the step that is currently
   * running, falling back to the most recent one. A `before` frame fills the
   * step's before slot, which is what the change overlay diffs against.
   */
  addFrame(frame: TraceFrame, correlationId?: string): void {
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
      (correlationId
        ? this.steps.find((s) => s.correlationId === correlationId)
        : undefined) ??
      [...this.steps].reverse().find((s) => s.status === "running") ??
      this.steps.at(-1);
    if (target) {
      if (frame.phase === "before") {
        target.frameKeyBefore = frame.key;
      } else {
        target.frameKey = frame.key;
      }
    }

    this.emit();
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
    const elapsedMs = Math.max(0, (endedAtMs ?? this.now()) - this.startedAtMs);
    return {
      schema: TRACE_SCHEMA,
      startedAtMs: this.startedAtMs,
      endedAtMs,
      elapsedMs,
      url: this.url,
      task: this.task,
      model: this.model,
      steps: this.steps.map((step) => ({ ...step })),
      frames: [...this.frames],
      metrics: this.metrics(elapsedMs),
    };
  }

  private metrics(elapsedMs: number): TraceMetrics {
    let toolMs = 0;
    let changedSteps = 0;
    let wastedSteps = 0;
    for (const step of this.steps) {
      toolMs += step.durMs ?? 0;
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
