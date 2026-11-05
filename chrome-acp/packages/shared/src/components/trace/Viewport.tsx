import { useState, type CSSProperties, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import type { TraceFrame, TraceOverlay } from "../../trace/types";

/** Fallback aspect ratio before the first frame arrives (roughly 1120x780). */
const DEFAULT_ASPECT = 1120 / 780;

export interface ViewportProps {
  /** Picture channel. `null` renders the placeholder instead. */
  frame: TraceFrame | null;
  /**
   * Overlays in frame pixel coordinates. Scaling is handled here, so callers
   * never need to know the rendered size.
   */
  overlays?: TraceOverlay[];
  /** Shown in the fake location bar. */
  url?: string;
  /** Shown in the footer. */
  title?: string;
  /** Short badge in the location bar, e.g. "LIVE". */
  badge?: string;
  /** Rendered inside the stage when there is no frame yet. */
  placeholder?: ReactNode;
  /** Extra content drawn over the stage, above the frame. */
  children?: ReactNode;
  className?: string;
}

/**
 * The picture half of the viewer: a decorative browser frame around whatever
 * the frame source provides. The window chrome is drawn in CSS rather than
 * captured, so no browser UI pixels are ever needed.
 */
export function Viewport({
  frame,
  overlays = [],
  url,
  title,
  badge,
  placeholder,
  children,
  className,
}: ViewportProps) {
  const [measuredAspect, setMeasuredAspect] = useState<number | null>(null);

  // The producer may not know the content-area size; fall back to the image's
  // own aspect ratio once it loads so nothing is ever stretched.
  const reportedAspect =
    frame && frame.width > 0 && frame.height > 0
      ? frame.width / frame.height
      : null;
  const aspect = reportedAspect ?? measuredAspect ?? DEFAULT_ASPECT;
  const canPlaceOverlays =
    frame !== null && frame.width > 0 && frame.height > 0;

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col overflow-hidden rounded-lg border bg-background",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-red-400/80" />
          <span className="size-2.5 rounded-full bg-yellow-400/80" />
          <span className="size-2.5 rounded-full bg-green-400/80" />
        </div>
        <div className="min-w-0 flex-1 truncate rounded bg-background/70 px-2 py-0.5 text-[11px] text-muted-foreground">
          {url || "about:blank"}
        </div>
        {badge ? (
          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {badge}
          </span>
        ) : null}
      </div>

      <div
        className="relative w-full overflow-hidden bg-muted"
        style={{ aspectRatio: String(aspect) } as CSSProperties}
      >
        {frame ? (
          <img
            key={frame.key}
            src={frame.dataUrl}
            alt={title ?? "Captured page"}
            className="absolute inset-0 size-full"
            draggable={false}
            onLoad={(event) => {
              const image = event.currentTarget;
              if (image.naturalWidth > 0 && image.naturalHeight > 0) {
                setMeasuredAspect(image.naturalWidth / image.naturalHeight);
              }
            }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-muted-foreground">
            {placeholder ?? "No frame captured yet"}
          </div>
        )}

        {frame && canPlaceOverlays
          ? overlays.map((overlay, index) => (
              <div
                key={`${overlay.kind}-${index}`}
                className={cn(
                  "pointer-events-none absolute rounded-sm border-2",
                  overlay.kind === "target"
                    ? "border-sky-400 bg-sky-400/10"
                    : "border-amber-400 bg-amber-400/20",
                )}
                style={{
                  left: `${(overlay.rect.x / frame.width) * 100}%`,
                  top: `${(overlay.rect.y / frame.height) * 100}%`,
                  width: `${(overlay.rect.w / frame.width) * 100}%`,
                  height: `${(overlay.rect.h / frame.height) * 100}%`,
                }}
              >
                {overlay.label ? (
                  <span className="absolute -top-4 left-0 whitespace-nowrap rounded bg-sky-500 px-1 text-[10px] text-white">
                    {overlay.label}
                  </span>
                ) : null}
              </div>
            ))
          : null}

        {children}
      </div>

      {title ? (
        <div className="truncate border-t px-3 py-1.5 text-[11px] text-muted-foreground">
          {title}
        </div>
      ) : null}
    </div>
  );
}
