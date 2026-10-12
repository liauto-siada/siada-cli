import { useState, type CSSProperties, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import type { TraceFrame, TraceOverlay } from "../../trace/types";

/** Fallback aspect ratio before the first picture arrives (roughly 1120x780). */
const DEFAULT_ASPECT = 1120 / 780;

export interface ViewportProps {
  /** Picture channel. `null` renders the placeholder instead. */
  frame: TraceFrame | null;
  /**
   * Overlays in the pixel coordinates of the picture they mark. Scaling is
   * handled here, so callers never need to know the rendered size.
   */
  overlays?: TraceOverlay[];
  /** Shown in the fake location bar. */
  url?: string;
  /** Shown in the footer. */
  title?: string;
  /**
   * Short provenance line next to the title, e.g. whether the picture on
   * screen belongs to the selected step or is just the latest one.
   */
  note?: string;
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
 *
 * Geometry (the stage's aspect ratio and the overlay scale) comes from the
 * loaded picture's own pixel size, never from `frame.width/height`: those are
 * the producer's CSS viewport metadata, while the picture itself is scaled by
 * the device pixel ratio and clamped by the capture limits (a screencast is
 * capped at 1280px wide, for example). Trusting the metadata would distort the
 * picture and slide the overlays off the areas they mark, so the metadata is
 * kept as provenance only.
 */
export function Viewport({
  frame,
  overlays = [],
  url,
  title,
  note,
  badge,
  placeholder,
  children,
  className,
}: ViewportProps) {
  // The picture's own pixel size, learned once the image has decoded.
  const [picture, setPicture] = useState<{
    key: string;
    width: number;
    height: number;
  } | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);

  const size = frame && picture?.key === frame.key ? picture : null;
  const failed = frame !== null && failedKey === frame.key;
  const aspect = size ? size.width / size.height : DEFAULT_ASPECT;
  // Overlays are only meaningful once the picture's pixel space is known and
  // the picture is actually on screen.
  const canPlaceOverlays = frame !== null && size !== null && !failed;

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
        {frame && !failed ? (
          <img
            key={frame.key}
            src={frame.dataUrl}
            alt={title ?? "Captured page"}
            className="absolute inset-0 size-full object-contain"
            draggable={false}
            onLoad={(event) => {
              const image = event.currentTarget;
              if (image.naturalWidth > 0 && image.naturalHeight > 0) {
                setPicture({
                  key: frame.key,
                  width: image.naturalWidth,
                  height: image.naturalHeight,
                });
              }
            }}
            onError={() => setFailedKey(frame.key)}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-muted-foreground">
            {failed
              ? "This captured picture could not be displayed."
              : (placeholder ?? "No frame captured yet")}
          </div>
        )}

        {canPlaceOverlays
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
                  left: `${(overlay.rect.x / size.width) * 100}%`,
                  top: `${(overlay.rect.y / size.height) * 100}%`,
                  width: `${(overlay.rect.w / size.width) * 100}%`,
                  height: `${(overlay.rect.h / size.height) * 100}%`,
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

      {title || note ? (
        <div className="flex items-center gap-2 border-t px-3 py-1.5 text-[11px] text-muted-foreground">
          <span className="truncate">{title}</span>
          {note ? <span className="ml-auto shrink-0 truncate">{note}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
