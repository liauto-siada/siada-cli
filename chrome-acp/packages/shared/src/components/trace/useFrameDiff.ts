import { useEffect, useState } from "react";
import { changedRegions, type Pixels } from "../../trace/diff";
import type { TraceFrame, TraceOverlay } from "../../trace/types";

// Only successful decodes are cached, and a reused key must match its bytes.
const pixelCache = new Map<string, { dataUrl: string; pixels: Pixels }>();
const PIXEL_CACHE_LIMIT = 8;

export interface FrameDiff {
  overlays: TraceOverlay[];
  changed: boolean | null;
  status: "idle" | "pending" | "ready" | "unavailable";
  reason?: string;
}
const IDLE: FrameDiff = { overlays: [], changed: null, status: "idle" };
const PENDING: FrameDiff = { overlays: [], changed: null, status: "pending" };

function sameFrame(a: TraceFrame, b: TraceFrame): boolean {
  return a.key === b.key && a.dataUrl === b.dataUrl;
}

async function decodeCached(frame: TraceFrame): Promise<Pixels> {
  const cached = pixelCache.get(frame.key);
  if (cached?.dataUrl === frame.dataUrl) return cached.pixels;
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("this view cannot compare pictures (no 2D canvas)");
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const value = new Image();
    value.onload = () => resolve(value);
    value.onerror = () => reject(new Error("the captured picture could not be decoded"));
    value.src = frame.dataUrl;
  });
  if (!image.naturalWidth || !image.naturalHeight) {
    throw new Error("the captured picture has no pixel size");
  }
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  context.drawImage(image, 0, 0);
  const { data } = await context.getImageData(0, 0, canvas.width, canvas.height);
  const pixels = { data, width: canvas.width, height: canvas.height };
  pixelCache.delete(frame.key);
  if (pixelCache.size >= PIXEL_CACHE_LIMIT) {
    const oldest = pixelCache.keys().next().value;
    if (oldest !== undefined) pixelCache.delete(oldest);
  }
  pixelCache.set(frame.key, { dataUrl: frame.dataUrl, pixels });
  return pixels;
}

/** A verdict exists only after successfully comparing this exact picture pair. */
export function useFrameDiff(before: TraceFrame | null, after: TraceFrame | null): FrameDiff {
  const [result, setResult] = useState<{
    before: TraceFrame; after: TraceFrame; diff: FrameDiff;
  } | null>(null);
  const usable = before !== null && after !== null && !sameFrame(before, after);

  useEffect(() => {
    if (!before || !after || sameFrame(before, after)) {
      setResult(null);
      return;
    }
    let cancelled = false;
    const pair = { before, after };
    setResult({ ...pair, diff: PENDING });
    void (async () => {
      try {
        const [a, b] = await Promise.all([decodeCached(before), decodeCached(after)]);
        if (cancelled) return;
        if (a.width !== b.width || a.height !== b.height) {
          throw new Error("the two pictures have different sizes");
        }
        const rects = changedRegions(a, b);
        setResult({ ...pair, diff: {
          overlays: rects.map(rect => ({ kind: "changed", rect })),
          changed: rects.length > 0, status: "ready",
        } });
      } catch (error) {
        if (!cancelled) setResult({ ...pair, diff: {
          overlays: [], changed: null, status: "unavailable",
          reason: error instanceof Error ? error.message : String(error),
        } });
      }
    })();
    return () => { cancelled = true; };
  }, [before?.key, before?.dataUrl, after?.key, after?.dataUrl]);

  if (!usable) return IDLE;
  if (!result || !sameFrame(result.before, before!) || !sameFrame(result.after, after!)) return PENDING;
  return result.diff;
}
