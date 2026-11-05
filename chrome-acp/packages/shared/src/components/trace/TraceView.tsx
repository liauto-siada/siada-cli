import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Ban, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { cn } from "../../lib/utils";
import { ScrollArea } from "../ui/scroll-area";
import { Viewport } from "./Viewport";
import { useFrameDiff } from "./useFrameDiff";
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
}: TraceViewProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [, setFrameTick] = useState(0);

  // Frames arrive independently of trace updates; re-render when one lands.
  useEffect(
    () => frameSource.subscribe(() => setFrameTick((tick) => tick + 1)),
    [frameSource],
  );

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

  const [showChanges, setShowChanges] = useState(true);
  const changeOverlays = useFrameDiff(beforeFrame, afterFrame);
  const overlays = showChanges ? changeOverlays : [];

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
            badge={run.endedAtMs === null ? "live" : undefined}
            placeholder={placeholder}
          />
          <StepDetail
            step={activeStep}
            changedRegions={changeOverlays.length}
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
        <Metric label="tool" value={formatDuration(metrics.toolMs)} />
        <Metric label="model / wait" value={formatDuration(metrics.gapMs)} />
        <Metric
          label="no change"
          value={String(metrics.wastedSteps)}
          warn={metrics.wastedSteps > 0}
        />
      </dl>
    </div>
  );
}

function Metric({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-baseline gap-1">
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
  changedRegions,
  overlaysVisible,
  onToggleOverlays,
}: {
  step: TraceStep | null;
  changedRegions: number;
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
            page {step.pageChanged ? "changed" : "unchanged"}
          </span>
        ) : null}
        {changedRegions > 0 ? (
          <button
            type="button"
            onClick={onToggleOverlays}
            className="rounded border px-1.5 py-0.5 hover:bg-muted"
          >
            {overlaysVisible ? "hide" : "show"} {changedRegions} changed{" "}
            {changedRegions === 1 ? "area" : "areas"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
