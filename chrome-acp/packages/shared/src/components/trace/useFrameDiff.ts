import { useEffect, useState } from "react";
import { changedRegions, type Pixels } from "../../trace/diff";
import type { TraceFrame, TraceOverlay } from "../../trace/types";

/** Decoded frames are reused across step selections; keyed by frame key. */
const pixelCache = new Map<string, Pixels | null>();
const PIXEL_CACHE_LIMIT = 8;

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

/**
 * Decode a frame into RGBA pixels. Requires a DOM canvas, which is why this
 * lives beside the component instead of in the pure diff module.
 */
async function decodeFramePixels(dataUrl: string): Promise<Pixels | null> {
  const image = await loadImage(dataUrl);
  if (!image || image.naturalWidth === 0 || image.naturalHeight === 0) {
    return null;
  }
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0);
  const { data, width, height } = context.getImageData(0, 0, canvas.width, canvas.height);
  return { data, width, height };
}

async function decodeCached(frame: TraceFrame): Promise<Pixels | null> {
  const cached = pixelCache.get(frame.key);
  if (cached !== undefined) return cached;

  const pixels = await decodeFramePixels(frame.dataUrl);
  if (pixelCache.size >= PIXEL_CACHE_LIMIT) {
    const oldest = pixelCache.keys().next().value;
    if (oldest !== undefined) pixelCache.delete(oldest);
  }
  pixelCache.set(frame.key, pixels);
  return pixels;
}

/**
 * Overlays marking the areas that changed between two frames. Returns an empty
 * list while decoding, when a frame is missing, or when the pair is unusable
 * (different sizes, failed decode).
 */
export function useFrameDiff(
  before: TraceFrame | null,
  after: TraceFrame | null,
): TraceOverlay[] {
  const [overlays, setOverlays] = useState<TraceOverlay[]>([]);

  useEffect(() => {
    if (!before || !after || before.key === after.key) {
      setOverlays([]);
      return;
    }

    let cancelled = false;
    void (async () => {
      const [beforePixels, afterPixels] = await Promise.all([
        decodeCached(before),
        decodeCached(after),
      ]);
      if (cancelled) return;
      if (!beforePixels || !afterPixels) {
        setOverlays([]);
        return;
      }
      setOverlays(
        changedRegions(beforePixels, afterPixels).map((rect) => ({
          kind: "changed" as const,
          rect,
        })),
      );
    })();

    return () => {
      cancelled = true;
    };
  }, [before, after]);

  return overlays;
}
