import { useEffect, useState } from "react";
import { changedRegions, type Pixels } from "../../trace/diff";
import type { TraceFrame, TraceOverlay } from "../../trace/types";

/**
 * Decoded frames are reused across step selections. An entry is keyed by frame
 * key but remembers the data URL it was decoded from: keys are only unique
 * within one capture source (a later run can reuse them for other pictures),
 * so the key alone does not prove the pixels belong to the frame in hand.
 */
const pixelCache = new Map<string, { dataUrl: string; pixels: Pixels }>();
const PIXEL_CACHE_LIMIT = 8;

const NO_CANVAS = "this view cannot compare pictures (no 2D canvas)";

export type FrameDiffStatus =
  /** No pair to compare (missing picture, or the same picture twice). */
  | "idle"
  /** Decoding the pair. */
  | "pending"
  /** The pair was compared; `changed` is the verdict. */
  | "ready"
  /** The pair cannot be compared here; `reason` says why. */
  | "unavailable";

export interface FrameDiff {
  /** Changed areas in the compared pixels; empty unless status is "ready". */
  overlays: TraceOverlay[];
  /**
   * Whether the comparison found changed areas: `false` means "none above the
   * diff's noise threshold", not "the page is provably identical"; `null`
   * means no comparison happened, so no claim is made.
   */
  changed: boolean | null;
  status: FrameDiffStatus;
  /** Why the comparison could not be made, when status is "unavailable". */
  reason?: string;
}

const IDLE: FrameDiff = { overlays: [], changed: null, status: "idle" };
const PENDING: FrameDiff = { overlays: [], changed: null, status: "pending" };

/**
 * Identity of a picture for the purpose of "is this the pair already
 * compared?": frame key plus content. Frame keys are reused across runs and
 * capture sources, so the same key with different bytes is a different
 * picture. The registry is bounded; a frame that falls out of it simply gets
 * a fresh identity and is compared again (the pixel cache still remembers the
 * bytes), never mistaken for the picture that held that key before.
 */
const identityByKey = new Map<string, { dataUrl: string; id: string }>();
const IDENTITY_LIMIT = 32;
let identityCounter = 0;

function frameIdentity(frame: TraceFrame): string {
  const known = identityByKey.get(frame.key);
  if (known && known.dataUrl === frame.dataUrl) {
    // Refresh recency: the frames in use stay resident.
    identityByKey.delete(frame.key);
    identityByKey.set(frame.key, known);
    return known.id;
  }
  identityCounter += 1;
  const entry = { dataUrl: frame.dataUrl, id: `picture-${identityCounter}` };
  identityByKey.set(frame.key, entry);
  if (identityByKey.size > IDENTITY_LIMIT) {
    const oldest = identityByKey.keys().next().value;
    if (oldest !== undefined) identityByKey.delete(oldest);
  }
  return entry.id;
}

/**
 * Identity of the pair under comparison, or null when there is nothing to
 * compare (a missing picture, or the very same picture twice).
 */
function pairIdentityOf(before: TraceFrame | null, after: TraceFrame | null): string | null {
  if (!before || !after) return null;
  if (before.key === after.key && before.dataUrl === after.dataUrl) return null;
  return `${frameIdentity(before)}>${frameIdentity(after)}`;
}

/** Whether this view can turn a picture into pixels at all. */
function canDecodePixels(): boolean {
  if (typeof document === "undefined" || typeof Image === "undefined") return false;
  try {
    return document.createElement("canvas").getContext("2d") !== null;
  } catch {
    return false;
  }
}

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
 *
 * Every failure mode — no image, no canvas, a canvas whose draw/getImageData
 * throws or rejects — is raised as an Error for the caller to report, never
 * left as an unhandled rejection that would silently keep stale overlays on
 * screen.
 */
async function decodeFramePixels(dataUrl: string): Promise<Pixels> {
  if (!canDecodePixels()) throw new Error(NO_CANVAS);

  const image = await loadImage(dataUrl);
  if (!image) throw new Error("the captured picture could not be decoded");
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  if (width === 0 || height === 0) throw new Error("the captured picture has no pixel size");

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error(NO_CANVAS);
  context.drawImage(image, 0, 0);
  // `await` so a canvas implementation that rejects (instead of throwing) is
  // handled by the caller's try/catch.
  const { data } = await context.getImageData(0, 0, width, height);
  return { data, width, height };
}

/** Decode with a small cache; only successful decodes are remembered. */
async function decodeCached(frame: TraceFrame): Promise<Pixels> {
  const cached = pixelCache.get(frame.key);
  if (cached && cached.dataUrl === frame.dataUrl) {
    // Refresh recency, then hand back the pixels decoded from these bytes.
    pixelCache.delete(frame.key);
    pixelCache.set(frame.key, cached);
    return cached.pixels;
  }

  const pixels = await decodeFramePixels(frame.dataUrl);
  // The key now maps to the picture actually decoded; an entry left over from
  // different bytes is dropped rather than read for the new picture.
  pixelCache.delete(frame.key);
  if (pixelCache.size >= PIXEL_CACHE_LIMIT) {
    const oldest = pixelCache.keys().next().value;
    if (oldest !== undefined) pixelCache.delete(oldest);
  }
  pixelCache.set(frame.key, { dataUrl: frame.dataUrl, pixels });
  return pixels;
}

/**
 * Overlays marking the areas that changed between a step's own before/after
 * pair, plus the honest state of that comparison: while the pair is missing or
 * still decoding, or when this view cannot decode it, there is no verdict.
 *
 * The result is bound to the identity of the pair it was computed from. A
 * selection change re-renders before the effect has run, and during that
 * render the previous pair's verdict is not handed out as if it described the
 * new pictures — neither as overlays drawn on the new frame, nor as a
 * `changed` value a host might record against the new step.
 */
export function useFrameDiff(
  before: TraceFrame | null,
  after: TraceFrame | null,
): FrameDiff {
  const pairId = pairIdentityOf(before, after);
  const [result, setResult] = useState<{ pairId: string | null; diff: FrameDiff }>({
    pairId: null,
    diff: IDLE,
  });

  useEffect(() => {
    // `pairId` names the content of the pair, so the frames captured here are
    // the ones it was computed from; a re-render for a new object with the
    // same bytes would only repeat the same comparison.
    const pairBefore = before;
    const pairAfter = after;
    if (pairId === null || !pairBefore || !pairAfter) {
      setResult({ pairId: null, diff: IDLE });
      return;
    }

    let cancelled = false;
    setResult({ pairId, diff: PENDING });

    void (async () => {
      try {
        const [beforePixels, afterPixels] = await Promise.all([
          decodeCached(pairBefore),
          decodeCached(pairAfter),
        ]);
        if (cancelled) return;
        if (
          beforePixels.width !== afterPixels.width ||
          beforePixels.height !== afterPixels.height
        ) {
          setResult({
            pairId,
            diff: {
              overlays: [],
              changed: null,
              status: "unavailable",
              reason: "the two pictures have different sizes",
            },
          });
          return;
        }
        const rects = changedRegions(beforePixels, afterPixels);
        setResult({
          pairId,
          diff: {
            overlays: rects.map((rect) => ({ kind: "changed" as const, rect })),
            changed: rects.length > 0,
            status: "ready",
          },
        });
      } catch (error) {
        if (cancelled) return;
        setResult({
          pairId,
          diff: {
            overlays: [],
            changed: null,
            status: "unavailable",
            reason: error instanceof Error ? error.message : String(error),
          },
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pairId]);

  if (result.pairId !== pairId) return pairId === null ? IDLE : PENDING;
  return result.diff;
}
