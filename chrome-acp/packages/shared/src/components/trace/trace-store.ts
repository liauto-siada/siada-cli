// Wiring between an ACP client's observable streams and the viewer's data:
// which session a run belongs to, which pictures may be shown, and when a run
// starts and ends.
//
// It lives outside the component so the rules that keep the viewer honest can
// be exercised without rendering anything:
//
// - a run is one turn, started by a prompt and ended only by the protocol's
//   own terminal events (prompt_complete, cancel, error, dropped connection);
// - a frame is only ever tied to a step whose correlation id it actually
//   matches, and otherwise stays a standalone picture of the run;
// - switching sessions discards the previous run's steps and pictures.

import type { ACPClient, FrameEnvelope } from "../../acp/client";
import type { TurnLifecycleEvent } from "../../acp/client";
import type { FramePayload, SessionUpdate } from "../../acp/types";
import {
  createBufferedFrameSource,
  frameFromDataUrl,
  type BufferedFrameSource,
} from "../../trace/frame-source";
import { createSessionGate } from "../../trace/session-gate";
import { TraceCollector } from "../../trace/collector";

/** The part of ACPClient this store consumes (so tests can stand in for it). */
export interface TraceStreamClient {
  addSessionUpdateListener(
    handler: (sessionId: string, update: SessionUpdate) => void,
  ): () => void;
  onFrame(handler: (frame: FrameEnvelope) => void): () => void;
  addTurnLifecycleListener(handler: (event: TurnLifecycleEvent) => void): () => void;
}

export interface TraceStoreOptions {
  /** Current model id, read when a run starts (shown on the run summary). */
  model?: () => string | undefined;
  /** Forwarded to the collector (used by tests for deterministic timings). */
  now?: () => number;
}

export interface TraceStore {
  readonly collector: TraceCollector;
  readonly frames: BufferedFrameSource;
  /**
   * Follow a client's streams (session updates, pictures, turn lifecycle).
   * Safe to call again after detach(): React's StrictMode mount/unmount/mount
   * cycle must leave the store subscribed exactly once.
   */
  attach(client: TraceStreamClient | ACPClient): void;
  /** Stop following the client; the collected run stays on screen. */
  detach(): void;
  /** Follow a session: the previous run's steps and pictures are discarded. */
  setSession(sessionId: string): void;
  /** The tab the session is bound to; `undefined` = unknown, nothing filtered. */
  setTab(tabId: number | undefined): void;
  /** Stop following a session (the last run stays on screen). */
  clearSession(): void;
}

/**
 * The tab a picture says it came from. The relay tags the message envelope;
 * a producer that puts the tab in the payload itself is honoured too.
 */
export function reportedTabId(frame: FrameEnvelope | FramePayload): number | undefined {
  const candidate =
    (frame as { tabId?: unknown }).tabId ??
    (frame as { payload?: { tabId?: unknown } }).payload?.tabId;
  return typeof candidate === "number" ? candidate : undefined;
}

/** A TraceStore whose subscriptions are wired up by attach(). */
export function createTraceStore(options: TraceStoreOptions = {}): TraceStore {
  const collector = new TraceCollector({
    ...(options.now ? { now: options.now } : {}),
  });
  const frames = createBufferedFrameSource();
  const gate = createSessionGate();
  // null = the session's tab is not known here (e.g. the web client, which has
  // no chrome.tabs access); then a picture is accepted on its own evidence.
  let tabId: number | null = null;
  // Session the viewer is following; a picture the relay attributes to another
  // run is not this run's.
  let activeSession: string | null = null;
  let attached: TraceStreamClient | ACPClient | null = null;
  let unsubscribes: Array<() => void> = [];

  const startRun = (): void => {
    frames.clear();
    collector.beginRun({ model: options.model?.() });
  };

  // Before the first prompt there is no live turn: the run exists (so the view
  // has a shape to render) but is already finished, or its "live" badge would
  // be a claim about work that has not started.
  collector.prepareRun({ model: options.model?.() });

  const subscribe = (client: TraceStreamClient | ACPClient): Array<() => void> => [
    client.addSessionUpdateListener((sessionId, update) => {
      if (!gate.accepts(sessionId)) return;
      collector.addSessionUpdate(update);
    }),

    client.onFrame(({ callId, tabId: frameTab, sessionId, payload }) => {
      // Reject a picture of another tab, or one the relay attributes to a run
      // this viewer has left: blending it into the current timeline would show
      // a page state that belongs to a different session.
      const fromTab = frameTab ?? reportedTabId(payload);
      if (fromTab !== undefined && tabId !== null && fromTab !== tabId) return;
      if (sessionId !== undefined && activeSession !== null && sessionId !== activeSession) {
        return;
      }
      const frame = frameFromDataUrl(payload);
      frames.push(frame);
      // The capture channel and the ACP stream number their calls differently,
      // so an id that matches no step leaves the picture standalone: the
      // viewport still shows it as the latest picture, but no step claims it
      // as its own before/after (see TraceCollector.addFrame).
      if (callId !== undefined) collector.addFrame(frame, callId);
    }),

    client.addTurnLifecycleListener((event) => {
      switch (event.kind) {
        case "started":
          startRun();
          break;
        case "completed":
          // Only a cancelled turn is canceled; any other stop reason means the
          // agent finished the turn (refusal, max tokens included).
          collector.endRun(
            event.stopReason === "cancelled" ? "canceled" : "complete",
          );
          break;
        case "cancel-requested":
          // The agent's confirmation can take a while or never arrive (the
          // prompt may already have failed agent-side); endRun is idempotent,
          // so ending here cannot double-count.
          collector.endRun("canceled");
          break;
        case "failed":
        case "disconnected":
          collector.endRun("error");
          break;
      }
    }),
  ];

  const detach = (): void => {
    for (const unsubscribe of unsubscribes) unsubscribe();
    unsubscribes = [];
    attached = null;
  };

  return {
    collector,
    frames,
    attach(client: TraceStreamClient | ACPClient): void {
      // Re-attaching the same client would double every event (React remounts
      // effects in StrictMode), so drop the previous bindings first.
      if (attached === client && unsubscribes.length > 0) return;
      detach();
      unsubscribes = subscribe(client);
      attached = client;
    },
    detach,
    setSession(sessionId: string): void {
      gate.setActive(sessionId);
      activeSession = sessionId;
      // The previous session's run and pictures are gone; this one has not
      // started working, so it is not live yet.
      frames.clear();
      collector.prepareRun({ model: options.model?.() });
    },
    setTab(next: number | undefined): void {
      tabId = next ?? null;
    },
    clearSession(): void {
      gate.setActive(null);
      activeSession = null;
    },
  };
}