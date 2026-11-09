import type { ACPClient, TurnLifecycleEvent } from "../../acp/client";
import { TraceCollector, type RunEndReason } from "../../trace/collector";
import { createBufferedFrameSource, frameFromDataUrl } from "../../trace/frame-source";

type TraceStreamClient = Pick<ACPClient,
  "getSessionId" | "addSessionUpdateListener" | "onFrame" | "addTurnLifecycleListener"
>;

/** Connect Trace to request boundaries without taking over the chat callbacks. */
export function createTraceStore(options: { model?: () => string | undefined; now?: () => number } = {}) {
  const collector = new TraceCollector({ now: options.now });
  const frames = createBufferedFrameSource();
  let sessionId: string | null = null;
  let tabId: number | undefined;
  let requestId: string | undefined;
  let running = false;
  let attached: TraceStreamClient | null = null;
  let unsubscribes: Array<() => void> = [];
  collector.prepareRun({ model: options.model?.() });

  const detach = () => {
    for (const unsubscribe of unsubscribes) unsubscribe();
    unsubscribes = [];
    attached = null;
  };
  const finish = (reason: RunEndReason) => {
    if (!running) return;
    running = false;
    collector.endRun(reason);
  };
  const lifecycle = (event: TurnLifecycleEvent) => {
    if (event.sessionId !== undefined && event.sessionId !== sessionId) return;
    if (event.kind === "started") {
      if (sessionId === null) return;
      frames.clear();
      requestId = event.requestId;
      running = true;
      collector.beginRun({ model: options.model?.() });
      return;
    }
    if (event.requestId !== undefined && event.requestId !== requestId) return;
    switch (event.kind) {
      case "completed":
        finish(event.stopReason === "cancelled" || event.stopReason === "canceled" ? "canceled" : "complete");
        break;
      case "cancel-requested":
        finish("canceled");
        break;
      case "failed":
      case "disconnected":
        finish("error");
        break;
    }
  };

  return {
    collector,
    frames,
    attach(client: TraceStreamClient) {
      if (attached === client) return;
      detach();
      attached = client;
      unsubscribes = [
        client.addSessionUpdateListener((id, update) => {
          // Session replay and late updates must not enter a different request.
          if (running && id === sessionId && id === client.getSessionId()) {
            collector.addSessionUpdate(update);
          }
        }),
        client.onFrame(({ callId, tabId: fromTab, payload }) => {
          // ACPClient also filters unowned and pending-session frames.
          if (sessionId === null || client.getSessionId() !== sessionId) return;
          if (tabId !== undefined && fromTab !== undefined && fromTab !== tabId) return;
          const frame = frameFromDataUrl(payload);
          frames.push(frame);
          // The collector retains unknown correlations as standalone pictures.
          collector.addFrame(frame, callId);
        }),
        client.addTurnLifecycleListener(lifecycle),
      ];
    },
    detach,
    setSession(id: string) {
      sessionId = id;
      tabId = undefined;
      requestId = undefined;
      running = false;
      frames.clear();
      collector.prepareRun({ model: options.model?.() });
    },
    setTab(id: number | undefined, expectedSession: string) {
      if (sessionId === expectedSession) tabId = id;
    },
    reportPageChange(correlationId: string, changed: boolean, runId?: string) {
      if (runId !== collector.snapshot().runId) return;
      collector.reportPageChange(correlationId, changed);
    },
  };
}