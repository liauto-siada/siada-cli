// Frame sources for the viewport.
//
// The viewer never talks to Chrome directly: it reads from a FrameSource. Step
// C ships the buffered source below (fed by whatever production channel exists
// — the extension today); step A adds a live screencast source without the
// viewer noticing.

import type { FrameSource, TraceFrame } from "./types";

let keyCounter = 0;

/** Unique, stable frame key derived from the capture time. */
export function createFrameKey(tsMs: number): string {
  keyCounter += 1;
  return `f${tsMs}-${keyCounter}`;
}

/** Build a TraceFrame from a raw base64 payload (as browser_screenshot returns). */
export function frameFromBase64(input: {
  base64: string;
  mimeType?: string;
  width: number;
  height: number;
  tsMs?: number;
  url?: string;
  title?: string;
  phase?: TraceFrame["phase"];
}): TraceFrame {
  const tsMs = input.tsMs ?? Date.now();
  const mimeType = input.mimeType ?? "image/jpeg";
  return {
    key: createFrameKey(tsMs),
    tsMs,
    phase: input.phase ?? "after",
    dataUrl: `data:${mimeType};base64,${input.base64}`,
    width: input.width,
    height: input.height,
    url: input.url,
    title: input.title,
  };
}

export interface BufferedFrameSource extends FrameSource {
  push(frame: TraceFrame): void;
  clear(): void;
  /** Number of frames currently retained. */
  size(): number;
}

/**
 * Build a TraceFrame from an already-encoded `data:` URL, as the extension
 * sends it. A size of 0 means "unknown"; the viewer then falls back to the
 * image's own aspect ratio.
 */
export function frameFromDataUrl(input: {
  dataUrl: string;
  width?: number;
  height?: number;
  tsMs?: number;
  url?: string;
  title?: string;
  phase?: TraceFrame["phase"];
}): TraceFrame {
  const tsMs = input.tsMs ?? Date.now();
  return {
    key: createFrameKey(tsMs),
    tsMs,
    phase: input.phase ?? "after",
    dataUrl: input.dataUrl,
    width: input.width ?? 0,
    height: input.height ?? 0,
    url: input.url,
    title: input.title,
  };
}

export interface BufferedFrameSourceOptions {
  maxFrames?: number;
}

/**
 * Bounded in-memory frame history. `current()` is the newest frame, so a view
 * that ignores history still works when frames arrive faster than the UI draws.
 */
export function createBufferedFrameSource(
  options: BufferedFrameSourceOptions = {},
): BufferedFrameSource {
  const maxFrames = options.maxFrames ?? 200;
  let frames: TraceFrame[] = [];
  const byKey = new Map<string, TraceFrame>();
  const listeners = new Set<(frame: TraceFrame) => void>();

  const push = (frame: TraceFrame): void => {
    frames.push(frame);
    byKey.set(frame.key, frame);
    if (frames.length > maxFrames) {
      const dropped = frames.splice(0, frames.length - maxFrames);
      for (const frame of dropped) byKey.delete(frame.key);
    }
    for (const listener of listeners) listener(frame);
  };

  return {
    id: "buffered",
    push,
    size: () => frames.length,
    clear: () => {
      frames = [];
      byKey.clear();
    },
    current: () => frames.at(-1) ?? null,
    frameFor: (key: string) => byKey.get(key) ?? null,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
