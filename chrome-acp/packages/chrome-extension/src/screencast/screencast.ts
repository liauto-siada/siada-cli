// Live view: a CDP screencast of one tab, driven through chrome.debugger.
//
// All chrome.* coupling lives behind `ScreencastTarget`, so the protocol logic
// (start -> ack every frame -> stop, and the awkward teardown order) is unit
// testable without a browser.
//
// Why the debugger API rather than captureVisibleTab: captureVisibleTab only
// sees the *active* tab of a window, so an agent working in a background tab
// could not be shown at all, and it has no per-frame geometry. A CDP
// screencast renders regardless of visibility and reports the content size in
// each frame's metadata, which is also the coordinate space overlays need.

export interface ScreencastFrameMetadata {
  deviceWidth?: number;
  deviceHeight?: number;
}

/** The subset of chrome.debugger this module needs. */
export interface ScreencastTarget {
  attach(): Promise<void>;
  detach(): Promise<void>;
  isAttached(): boolean;
  sendCommand(method: string, params?: Record<string, unknown>): Promise<unknown>;
  /** Subscribe to CDP events for this target. Returns an unsubscribe function. */
  onEvent(
    listener: (method: string, params: Record<string, unknown>) => void,
  ): () => void;
}

export interface ScreencastFrame {
  /** `data:` URL of the encoded JPEG frame. */
  dataUrl: string;
  /** Content-area size in CSS pixels, from the frame metadata. */
  width: number;
  height: number;
  tsMs: number;
}

export interface ScreencastOptions {
  /** JPEG quality, 0-100. */
  quality?: number;
  maxWidth?: number;
  maxHeight?: number;
  /** 1 sends every frame; higher values drop frames to save bandwidth. */
  everyNthFrame?: number;
  onFrame(frame: ScreencastFrame): void;
  /** Called when the stream starts or stops, including on failure. */
  onState?(state: LiveViewState): void;
  /** Injectable clock for deterministic tests. */
  now?: () => number;
}

/**
 * `screencast` is the real stream and only works while the tab is composited,
 * i.e. while the user is actually looking at it. `screenshots` is the polling
 * fallback used for a non-visible tab, where Chrome emits a single frame and
 * then goes quiet. Both satisfy ScreencastSession so callers do not branch.
 */
export type LiveViewMode = "screencast" | "screenshots";

export interface LiveViewState {
  active: boolean;
  error?: string;
  mode?: LiveViewMode;
}

export interface ScreencastSession {
  start(): Promise<void>;
  stop(): Promise<void>;
  isActive(): boolean;
}

const FRAME_EVENT = "Page.screencastFrame";

export function createScreencast(
  target: ScreencastTarget,
  options: ScreencastOptions,
): ScreencastSession {
  const now = options.now ?? (() => Date.now());
  let active = false;
  let unsubscribe: (() => void) | null = null;
  let attachedHere = false;
  // Bringing the stream up takes two round trips (attach, then start), so a
  // stop can arrive while it is still starting: `starting` holds that in-flight
  // work and `stopping` tells it to undo itself instead of going live.
  let starting: Promise<void> | null = null;
  let stopping = false;

  const report = (state: LiveViewState): void => {
    try {
      options.onState?.(state);
    } catch {
      // A reporting failure must not take the stream down.
    }
  };

  const handleFrame = (params: Record<string, unknown>): void => {
    const sessionId = params.sessionId;
    // Acknowledge first: Chrome throttles (and eventually stops) a screencast
    // whose frames are never acked, and a decoding failure below must not
    // stall the stream.
    if (typeof sessionId === "number") {
      void target
        .sendCommand("Page.screencastFrameAck", { sessionId })
        .catch(() => {});
    }

    const data = params.data;
    if (typeof data !== "string" || data.length === 0) return;

    const metadata = (params.metadata ?? {}) as ScreencastFrameMetadata;
    try {
      options.onFrame({
        dataUrl: `data:image/jpeg;base64,${data}`,
        width: metadata.deviceWidth ?? 0,
        height: metadata.deviceHeight ?? 0,
        tsMs: now(),
      });
    } catch {
      // Consumer errors are not the stream's problem.
    }
  };

  async function start(): Promise<void> {
    if (active || starting) return;
    stopping = false;

    const run = (async () => {
      try {
        if (!target.isAttached()) {
          await target.attach();
          attachedHere = true;
        }
        if (stopping) return;
        unsubscribe = target.onEvent((method, params) => {
          if (method === FRAME_EVENT) handleFrame(params);
        });
        // Chrome only composites the frame of a tab it considers focused, so a
        // background tab emits no screencast frames at all without this. The
        // emulated focus is scoped to this target and does not steal the user's
        // actual tab or window focus.
        await target.sendCommand("Emulation.setFocusEmulationEnabled", { enabled: true });
        if (stopping) return;
        await target.sendCommand("Page.startScreencast", {
          format: "jpeg",
          quality: options.quality ?? 60,
          ...(options.maxWidth !== undefined ? { maxWidth: options.maxWidth } : {}),
          ...(options.maxHeight !== undefined ? { maxHeight: options.maxHeight } : {}),
          everyNthFrame: options.everyNthFrame ?? 1,
        });
        if (stopping) return;
        active = true;
        report({ active: true, mode: "screencast" });
      } catch (error) {
        await teardown();
        if (!stopping) {
          report({ active: false, error: (error as Error).message, mode: "screencast" });
        }
      } finally {
        // A stop that arrived mid-start undoes whatever this start built;
        // otherwise the stream would run with nobody holding a handle to it.
        if (stopping) await teardown();
        starting = null;
      }
    })();

    starting = run;
    await run;
  }

  async function teardown(): Promise<void> {
    active = false;
    unsubscribe?.();
    unsubscribe = null;
    try {
      await target.sendCommand("Page.stopScreencast");
    } catch {
      // Already stopping, or the tab navigated away.
    }
    try {
      await target.sendCommand("Emulation.setFocusEmulationEnabled", { enabled: false });
    } catch {
      // Focus emulation is gone with the target.
    }
    if (attachedHere) {
      attachedHere = false;
      try {
        await target.detach();
      } catch {
        // The target may already be gone (tab closed).
      }
    }
  }

  async function stop(): Promise<void> {
    // Wait out an in-flight start rather than racing it: the start unwinds
    // itself when it sees this stop, and the terminal state is reported here.
    const pending = starting;
    if (pending) {
      stopping = true;
      await pending;
      report({ active: false, mode: "screencast" });
      return;
    }
    stopping = false;
    if (!active && !unsubscribe && !attachedHere) return;
    await teardown();
    report({ active: false, mode: "screencast" });
  }

  return { start, stop, isActive: () => active };
}

// ---------------------------------------------------------------------------
// Screenshot polling: the fallback for a tab Chrome will not composite.
// ---------------------------------------------------------------------------

export interface ScreenshotPollingOptions extends ScreencastOptions {
  /** Milliseconds between captures (default 400). */
  intervalMs?: number;
  /** Consecutive capture failures tolerated before the stream gives up. */
  maxFailures?: number;
}

/**
 * Live view by polling `Page.captureScreenshot`.
 *
 * `Page.startScreencast` only emits frames for a tab Chrome is compositing, so a
 * tab the user is not currently looking at yields a single frame and then
 * silence. Screenshots have no such restriction, at the cost of a much lower
 * frame rate and a capture round trip per frame.
 */
export function createScreenshotPolling(
  target: ScreencastTarget,
  options: ScreenshotPollingOptions,
): ScreencastSession {
  const now = options.now ?? (() => Date.now());
  const intervalMs = Math.max(100, options.intervalMs ?? 400);
  const maxFailures = Math.max(1, options.maxFailures ?? 3);

  let active = false;
  let attachedHere = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let failures = 0;
  let size = { width: 0, height: 0 };
  // Same guard as createScreencast: a stop can arrive while the start is still
  // attaching and reading the layout metrics.
  let starting: Promise<void> | null = null;
  let stopping = false;

  const report = (state: LiveViewState): void => {
    try {
      options.onState?.(state);
    } catch {
      // A reporting failure must not take the stream down.
    }
  };

  async function captureOnce(): Promise<void> {
    const shot = (await target.sendCommand("Page.captureScreenshot", {
      format: "jpeg",
      quality: options.quality ?? 60,
      captureBeyondViewport: false,
    })) as { data?: string };
    if (typeof shot?.data !== "string" || shot.data.length === 0) {
      throw new Error("empty screenshot");
    }
    failures = 0;
    try {
      options.onFrame({
        dataUrl: `data:image/jpeg;base64,${shot.data}`,
        width: size.width,
        height: size.height,
        tsMs: now(),
      });
    } catch {
      // Consumer errors are not the stream's problem.
    }
  }

  async function tick(): Promise<void> {
    if (!active) return;
    try {
      await captureOnce();
    } catch (error) {
      failures++;
      if (failures >= maxFailures) {
        await teardown();
        report({
          active: false,
          error: (error as Error).message,
          mode: "screenshots",
        });
        return;
      }
    }
    if (!active) return;
    timer = setTimeout(() => void tick(), intervalMs);
  }

  async function teardown(): Promise<void> {
    active = false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (attachedHere) {
      attachedHere = false;
      try {
        await target.detach();
      } catch {
        // The target may already be gone (tab closed).
      }
    }
  }

  async function start(): Promise<void> {
    if (active || starting) return;
    stopping = false;

    const run = (async () => {
      try {
        if (!target.isAttached()) {
          await target.attach();
          attachedHere = true;
        }
        if (stopping) return;
        const metrics = (await target.sendCommand("Page.getLayoutMetrics")) as {
          cssVisualViewport?: { clientWidth?: number; clientHeight?: number };
          visualViewport?: { clientWidth?: number; clientHeight?: number };
        };
        const viewport = metrics?.cssVisualViewport ?? metrics?.visualViewport;
        size = {
          width: Math.round(viewport?.clientWidth ?? 0),
          height: Math.round(viewport?.clientHeight ?? 0),
        };
        failures = 0;
        if (stopping) return;
        active = true;
        report({ active: true, mode: "screenshots" });
        void tick();
      } catch (error) {
        await teardown();
        if (!stopping) {
          report({ active: false, error: (error as Error).message, mode: "screenshots" });
        }
      } finally {
        if (stopping) await teardown();
        starting = null;
      }
    })();

    starting = run;
    await run;
  }

  async function stop(): Promise<void> {
    // See createScreencast: wait out a pending start instead of racing it.
    const pending = starting;
    if (pending) {
      stopping = true;
      await pending;
      report({ active: false, mode: "screenshots" });
      return;
    }
    stopping = false;
    if (!active && !timer && !attachedHere) return;
    await teardown();
    report({ active: false, mode: "screenshots" });
  }

  return { start, stop, isActive: () => active };
}
