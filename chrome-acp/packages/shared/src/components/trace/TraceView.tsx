import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Ban, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { cn } from "../../lib/utils";
import { ScrollArea } from "../ui/scroll-area";
import { Viewport } from "./Viewport";
import { useFrameDiff, type FrameDiff } from "./useFrameDiff";
import { formatDuration, formatElapsed, shareOfTotal } from "../../trace/format";
import type {
  FrameSource,
  TraceRun,
  TraceStep,
  TraceStepStatus,
} from "../../trace/types";

export interface TraceViewProps {
  run: TraceRun;
  frameSource: FrameSource;
  className?: string;
  /**
   * `auto` stacks in a narrow panel (the extension sidepanel) and splits
   * side-by-side when the viewport is wide enough (web client, full tab).
   */
  density?: "auto" | "compact" | "full";
  /** Shown inside the stage before the first frame arrives. */
  placeholder?: ReactNode;
  /**
   * Called with the verdict of an actual picture comparison for a step (its
   * own before/after pair, once decoded). The host records it on the step as
   * the one page-change observation the viewer is allowed to show.
   */
  onPageChange?: (correlationId: string, changed: boolean) => void;
}

const statusIcon: Record<TraceStepStatus, ReactNode> = {
  running: <Loader2 className="size-3.5 animate-spin text-yellow-600" />,
  complete: <CheckCircle2 className="size-3.5 text-green-600" />,
  error: <XCircle className="size-3.5 text-red-600" />,
  canceled: <Ban className="size-3.5 text-orange-500" />,
};

/**
 * The data half plus layout: summary, step timeline, and the viewport that the
 * selected step drives. Everything numeric here comes from the trace; the frame
 * is only ever a background picture.
 */
export function TraceView({
  run,
  frameSource,
  className,
  density = "auto",
  placeholder,
  onPageChange,
}: TraceViewProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [, setFrameTick] = useState(0);

  // Frames arrive independently of trace updates; re-render when one lands.
  useEffect(
    () => frameSource.subscribe(() => setFrameTick((tick) => tick + 1)),
    [frameSource],
  );

  // Identity of the run on screen. `runId` is minted per beginRun(), so two
  // runs that start in the same millisecond are still told apart; traces
  // without one (persisted before the field existed) fall back to their start
  // time, which was the only identity available then.
  const runIdentity = run.runId ?? `started-${run.startedAtMs}`;

  // A new run replaces the timeline wholesale, so a step selected in the
  // previous one must not survive: it would leave the detail panel pointing at
  // an index the current run does not have.
  useEffect(() => {
    setSelected(null);
  }, [runIdentity]);

  const activeIndex = selected ?? run.steps.at(-1)?.i ?? null;
  const activeStep = useMemo(
    () => run.steps.find((step) => step.i === activeIndex) ?? null,
    [run.steps, activeIndex],
  );

  const afterFrame = activeStep?.frameKey
    ? frameSource.frameFor(activeStep.frameKey)
    : null;
  const beforeFrame = activeStep?.frameKeyBefore
    ? frameSource.frameFor(activeStep.frameKeyBefore)
    : null;

  // Prefer the selected step's own frame; fall back to the newest one so the
  // stage is never blank while frames trail the trace slightly.
  const frame = afterFrame ?? frameSource.current();
  // Say which picture is on screen: a step's own after-frame, or the newest
  // picture of the run — which is a picture, not an attribution.
  const frameNote = frame
    ? afterFrame
      ? "picture linked to this step"
      : "latest picture, not linked to a step"
    : undefined;

  const [showChanges, setShowChanges] = useState(true);
  // Diffing a step's own before/after pair is the only page-change evidence
  // this viewer has; the verdict is reported back so the host can record it.
  const diff = useFrameDiff(beforeFrame, afterFrame);
  const overlays = showChanges ? diff.overlays : [];

  const correlationId = activeStep?.correlationId;
  const pairKey =
    beforeFrame && afterFrame && beforeFrame.key !== afterFrame.key
      ? `${beforeFrame.key}>${afterFrame.key}`
      : null;
  const reportedPair = useRef<string | null>(null);
  useEffect(() => {
    if (!onPageChange || !correlationId || !pairKey || diff.changed === null) return;
    // The run is part of the identity: a new run may reuse the same
    // correlation id and frame keys, and its pictures are new evidence that
    // must be reported rather than suppressed as "already reported".
    const key = `${runIdentity}::${correlationId}::${pairKey}`;
    if (reportedPair.current === key) return;
    reportedPair.current = key;
    onPageChange(correlationId, diff.changed);
  }, [onPageChange, runIdentity, correlationId, pairKey, diff.changed]);

  const maxDur = run.steps.reduce((max, step) => Math.max(max, step.durMs ?? 0), 0);

  return (
    <div className={cn("flex min-h-0 flex-col gap-3 p-3", className)}>
      <Summary run={run} />

      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col gap-3",
          density === "auto" && "lg:flex-row",
          density === "full" && "lg:flex-row",
        )}
      >
        <div className="flex min-w-0 flex-col gap-2 lg:flex-1">
          <Viewport
            frame={frame}
            overlays={overlays}
            url={frame?.url ?? run.url}
            title={frame?.title ?? run.task}
            note={frameNote}
            badge={run.endedAtMs === null ? "live" : undefined}
            placeholder={placeholder}
          />
          <StepDetail
            step={activeStep}
            diff={diff}
            overlaysVisible={showChanges}
            onToggleOverlays={() => setShowChanges((visible) => !visible)}
          />
        </div>

        <div className="flex min-h-0 flex-col lg:w-80 lg:shrink-0">
          <div className="flex items-center justify-between px-1 pb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Steps
            </span>
            <span className="text-[11px] text-muted-foreground">
              {run.metrics.stepCount} actions
            </span>
          </div>
          <ScrollArea className="min-h-0 flex-1 rounded-md border">
            {run.steps.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                Steps appear here as the agent acts on the page.
              </p>
            ) : (
              <ul className="divide-y">
                {run.steps.map((step) => (
                  <StepRow
                    key={step.i}
                    step={step}
                    maxDur={maxDur}
                    active={step.i === activeIndex}
                    onSelect={() => setSelected(step.i)}
                  />
                ))}
              </ul>
            )}
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}

function Summary({ run }: { run: TraceRun }) {
  const { metrics } = run;
  const attributed = shareOfTotal(metrics.toolMs, run.elapsedMs);
  // "no change" is a count of comparisons that actually happened: a step whose
  // before/after pictures were never compared is neither changed nor unchanged,
  // so with nothing compared the metric reads "—" instead of a made-up 0.
  const comparedSteps = metrics.changedSteps + metrics.wastedSteps;

  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-2xl tabular-nums">
          {formatElapsed(run.elapsedMs)}
        </span>
        <span className="text-xs text-muted-foreground">elapsed</span>
        {run.model ? (
          <span className="ml-auto truncate text-[11px] text-muted-foreground">
            {run.model}
          </span>
        ) : null}
      </div>

      <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-muted">
        <div className="bg-sky-500" style={{ width: `${attributed}%` }} />
        <div className="bg-muted-foreground/30" style={{ width: `${100 - attributed}%` }} />
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] sm:grid-cols-4">
        <Metric label="steps" value={String(metrics.stepCount)} />
        <Metric
          label="tool"
          value={formatDuration(metrics.toolMs)}
          hint="run time covered by observed tool calls; calls that run concurrently overlap and are counted once"
        />
        <Metric
          label="outside tools"
          value={formatDuration(metrics.gapMs)}
          hint="run time not covered by observed tool calls: model thinking, browser work between steps, anything else the trace cannot see"
        />
        <Metric
          label="no change"
          value={comparedSteps > 0 ? String(metrics.wastedSteps) : "—"}
          warn={metrics.wastedSteps > 0}
          hint={
            comparedSteps > 0
              ? `of the ${comparedSteps} step(s) whose own before/after pictures were compared, this many showed no change above the diff threshold — a pixel verdict, not a claim that the action did nothing`
              : "no step has a compared before/after picture pair yet"
          }
        />
      </dl>
    </div>
  );
}

function Metric({
  label,
  value,
  warn,
  hint,
}: {
  label: string;
  value: string;
  warn?: boolean;
  hint?: string;
}) {
  return (
    <div className="flex min-w-0 items-baseline gap-1" title={hint}>
      <dt className="truncate text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "ml-auto font-mono tabular-nums",
          warn && "text-amber-600",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function StepRow({
  step,
  maxDur,
  active,
  onSelect,
}: {
  step: TraceStep;
  maxDur: number;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "step" : undefined}
        className={cn(
          "flex w-full flex-col gap-1 px-2.5 py-2 text-left transition-colors hover:bg-muted/60",
          active && "bg-muted",
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          <span className="font-mono text-[10px] text-muted-foreground">
            {String(step.i).padStart(2, "0")}
          </span>
          {statusIcon[step.status]}
          <span className="min-w-0 flex-1 truncate text-xs">{step.action}</span>
          <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
            {formatDuration(step.durMs)}
          </span>
        </div>

        {step.target || step.value ? (
          <div className="truncate pl-6 text-[10px] text-muted-foreground">
            {step.target?.label}
            {step.value && step.value !== step.target?.label ? ` · “${step.value}”` : ""}
          </div>
        ) : null}

        <div className="ml-6 h-1 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full",
              step.status === "error" ? "bg-red-500" : "bg-sky-500",
            )}
            style={{ width: `${shareOfTotal(step.durMs ?? 0, maxDur)}%` }}
          />
        </div>
      </button>
    </li>
  );
}

function StepDetail({
  step,
  diff,
  overlaysVisible,
  onToggleOverlays,
}: {
  step: TraceStep | null;
  diff: FrameDiff;
  overlaysVisible: boolean;
  onToggleOverlays: () => void;
}) {
  if (!step) {
    return (
      <div className="rounded-lg border bg-card p-3 text-xs text-muted-foreground">
        Select a step to inspect what the agent did.
      </div>
    );
  }

  const changedAreas = diff.overlays.length;
  const diffNote =
    diff.status === "pending"
      ? "change overlay: comparing this step's before/after pictures…"
      : diff.status === "unavailable"
        ? `change overlay unavailable: ${diff.reason}`
        : diff.status === "idle"
          ? "change overlay: no before/after picture pair is linked to this step"
          : null;

  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center gap-2">
        {statusIcon[step.status]}
        <span className="truncate text-sm font-medium">{step.action}</span>
        <span className="ml-auto font-mono text-sm tabular-nums">
          {formatDuration(step.durMs)}
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span>step {step.i}</span>
        <span>kind: {step.kind}</span>
        {step.target?.label ? <span>target: {step.target.label}</span> : null}
        {step.value ? <span>value: {step.value}</span> : null}
        {step.pageChanged !== null ? (
          <span className={step.pageChanged ? "" : "text-amber-600"}>
            {step.pageChanged
              ? "page changed"
              : "page diff: no change above threshold"}
          </span>
        ) : null}
        {diff.status === "ready" && changedAreas > 0 ? (
          <button
            type="button"
            onClick={onToggleOverlays}
            className="rounded border px-1.5 py-0.5 hover:bg-muted"
          >
            {overlaysVisible ? "hide" : "show"} {changedAreas} changed{" "}
            {changedAreas === 1 ? "area" : "areas"}
          </button>
        ) : null}
        {diff.status === "ready" && changedAreas === 0 ? (
          <span>page change: none found above the diff threshold</span>
        ) : null}
      </div>
      {diffNote ? <p className="mt-1 text-[11px] text-muted-foreground">{diffNote}</p> : null}
    </div>
  );
}
