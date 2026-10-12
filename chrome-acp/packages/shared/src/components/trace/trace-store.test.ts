import { describe, expect, test } from "bun:test";
import type { FrameEnvelope, TurnLifecycleEvent } from "../../acp/client";
import type { FramePayload, SessionUpdate } from "../../acp/types";
import { createTraceStore, reportedTabId, type TraceStoreOptions } from "./trace-store";

type UpdateHandler = (sessionId: string, update: SessionUpdate) => void;
type FrameHandler = (frame: FrameEnvelope) => void;
type TurnHandler = (event: TurnLifecycleEvent) => void;

/**
 * Pictures may carry the tab they were captured from and the run the relay
 * attributes them to; the viewer's own payload type predates that tagging, so
 * tests feed it in explicitly (on the envelope, as the relay sends it, and in
 * the payload for producers that embed it).
 */
type PayloadWithTab = Partial<FramePayload> & { tabId?: unknown };

/** A frame payload with the fields a test wants to vary. */
function payloadWith(fields: PayloadWithTab = {}): FramePayload {
  return {
    dataUrl: "data:image/jpeg;base64,AAAA",
    width: 1000,
    height: 600,
    ...fields,
  } as FramePayload;
}

/** Stand-in for ACPClient: the store only needs these three subscriptions. */
class FakeStreams {
  private updateHandlers = new Set<UpdateHandler>();
  private frameHandlers = new Set<FrameHandler>();
  private turnHandlers = new Set<TurnHandler>();

  addSessionUpdateListener(handler: UpdateHandler): () => void {
    this.updateHandlers.add(handler);
    return () => this.updateHandlers.delete(handler);
  }

  onFrame(handler: FrameHandler): () => void {
    this.frameHandlers.add(handler);
    return () => this.frameHandlers.delete(handler);
  }

  addTurnLifecycleListener(handler: TurnHandler): () => void {
    this.turnHandlers.add(handler);
    return () => this.turnHandlers.delete(handler);
  }

  // Test-side simulation
  toolCall(sessionId: string, toolCallId: string, title = "browser_click"): void {
    const update: SessionUpdate = {
      sessionUpdate: "tool_call",
      toolCallId,
      title,
      status: "in_progress",
    };
    for (const handler of this.updateHandlers) handler(sessionId, update);
  }

  frame(
    payload: PayloadWithTab = {},
    callId?: string,
    routing: { tabId?: number; sessionId?: string } = {},
  ): void {
    const full = payloadWith(payload);
    const envelope: FrameEnvelope = {
      ...routing,
      ...(callId === undefined ? {} : { callId }),
      payload: full,
    };
    for (const handler of this.frameHandlers) handler(envelope);
  }

  turn(event: TurnLifecycleEvent): void {
    for (const handler of this.turnHandlers) handler(event);
  }
}

function clock(start = 1_000) {
  let value = start;
  return {
    now: () => value,
    advance: (ms: number) => {
      value += ms;
    },
  };
}

/** A store following `streams`, as ACPMain wires it up on mount. */
function attachedStore(streams: FakeStreams, options: TraceStoreOptions = {}) {
  const store = createTraceStore(options);
  store.attach(streams);
  return store;
}

describe("trace store run lifecycle", () => {
  test("a fresh session is not live until a prompt goes out", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);

    // Nothing has been done yet, so the run exists but is finished.
    expect(store.collector.snapshot().endedAtMs).not.toBeNull();

    store.setSession("s1");
    expect(store.collector.snapshot().endedAtMs).not.toBeNull();

    streams.turn({ kind: "started" });
    expect(store.collector.snapshot().endedAtMs).toBeNull();
    store.detach();
  });

  test("a prompt starts a live run and prompt_complete ends it with its steps closed", () => {
    const streams = new FakeStreams();
    const c = clock();
    const store = attachedStore(streams, { now: c.now, model: () => "gpt-test" });
    store.setSession("s1");

    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");
    c.advance(120);
    expect(store.collector.snapshot().endedAtMs).toBeNull();

    streams.turn({ kind: "completed", stopReason: "end_turn" });

    const run = store.collector.snapshot();
    expect(run.endedAtMs).not.toBeNull();
    expect(run.model).toBe("gpt-test");
    expect(run.steps[0]!.status).toBe("complete");
    expect(run.steps[0]!.durMs).toBe(120);
    store.detach();
  });

  test("a cancel ends the run as canceled, even before the agent confirms", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");

    streams.turn({ kind: "cancel-requested" });

    expect(store.collector.snapshot().steps[0]!.status).toBe("canceled");

    // The agent's late confirmation cannot rewrite the verdict.
    streams.turn({ kind: "completed", stopReason: "cancelled" });
    expect(store.collector.snapshot().steps[0]!.status).toBe("canceled");
    store.detach();
  });

  test("a prompt_complete for a cancelled turn is canceled, not completed", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");

    streams.turn({ kind: "completed", stopReason: "cancelled" });

    expect(store.collector.snapshot().steps[0]!.status).toBe("canceled");
    store.detach();
  });

  test("a failed turn and a dropped connection both end the run as errors", () => {
    for (const event of [
      { kind: "failed", message: "BadGatewayError: 502" } as const,
      { kind: "disconnected" } as const,
    ]) {
      const streams = new FakeStreams();
      const store = attachedStore(streams);
      store.setSession("s1");
      streams.turn({ kind: "started" });
      streams.toolCall("s1", "t1");

      streams.turn(event);

      const run = store.collector.snapshot();
      expect(run.endedAtMs).not.toBeNull();
      expect(run.steps[0]!.status).toBe("error");
      store.detach();
    }
  });

  test("a new prompt after a finished turn starts a new run again", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");
    streams.turn({ kind: "completed", stopReason: "end_turn" });

    streams.turn({ kind: "started" });

    const run = store.collector.snapshot();
    expect(run.endedAtMs).toBeNull();
    expect(run.steps).toHaveLength(0);
    store.detach();
  });
});

describe("trace store sessions and pictures", () => {
  test("updates from a session the viewer left are dropped", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");

    streams.toolCall("s2", "other");
    streams.toolCall("s1", "mine");

    expect(store.collector.snapshot().steps.map((s) => s.correlationId)).toEqual(["mine"]);
    store.detach();
  });

  test("switching sessions discards the previous run's steps and pictures", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");
    streams.frame({}, "call-1");

    store.setSession("s2");

    const run = store.collector.snapshot();
    expect(run.steps).toHaveLength(0);
    expect(run.frames).toHaveLength(0);
    expect(store.frames.size()).toBe(0);
    // The new session has not worked yet, so its run is not live either.
    expect(run.endedAtMs).not.toBeNull();
    store.detach();
  });

  test("a picture with an unmatched call id stays standalone but is the latest picture", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");

    streams.frame({}, "mcp-call-1");

    const run = store.collector.snapshot();
    expect(run.steps[0]!.frameKey).toBeUndefined();
    // The viewport resolves `current()`, so the picture is still shown.
    expect(store.frames.current()?.key).toBe(run.frames[0]!.key);
    store.detach();
  });

  test("a picture that names its tab is dropped when it is another tab's", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    store.setTab(7);

    streams.frame({}, undefined, { tabId: 8 });
    expect(store.frames.size()).toBe(0);

    streams.frame({}, undefined, { tabId: 7 });
    expect(store.frames.size()).toBe(1);

    // A payload that carries the tab itself is honoured the same way.
    streams.frame({ tabId: 8 });
    expect(store.frames.size()).toBe(1);
    streams.frame({ tabId: 7 });
    expect(store.frames.size()).toBe(2);

    // A producer that reports no tab gives no evidence to reject.
    streams.frame();
    expect(store.frames.size()).toBe(3);
    store.detach();
  });

  test("a picture the relay attributes to another run is dropped", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");

    streams.frame({}, "t1", { sessionId: "s0" });
    expect(store.frames.size()).toBe(0);

    streams.frame({}, "t1", { sessionId: "s1" });
    expect(store.frames.size()).toBe(1);

    // Untagged pictures carry no evidence to reject.
    streams.frame({}, "t1");
    expect(store.frames.size()).toBe(2);

    // Leaving the session (web client close) accepts everything again.
    store.clearSession();
    streams.frame({}, "t1", { sessionId: "s2" });
    expect(store.frames.size()).toBe(3);
    store.detach();
  });

  test("without a known tab every picture is accepted", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    store.setTab(undefined);

    streams.frame({ tabId: 8 });

    expect(store.frames.size()).toBe(1);
    store.detach();
  });

  test("detach unsubscribes from every stream", () => {
    const streams = new FakeStreams();
    const store = attachedStore(streams);
    store.setSession("s1");
    store.detach();

    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");
    streams.frame();

    expect(store.collector.snapshot().steps).toHaveLength(0);
    expect(store.frames.size()).toBe(0);
  });

  test("React's mount/unmount/mount cycle leaves the store subscribed exactly once", () => {
    const streams = new FakeStreams();
    const store = createTraceStore();

    store.attach(streams); // mount
    store.detach(); // StrictMode unmount
    store.attach(streams); // mount again
    store.attach(streams); // a third attach must not double anything either

    store.setSession("s1");
    streams.turn({ kind: "started" });
    streams.toolCall("s1", "t1");
    streams.frame();

    // One step and one picture, not two of each.
    expect(store.collector.snapshot().steps).toHaveLength(1);
    expect(store.frames.size()).toBe(1);
    expect(store.collector.snapshot().endedAtMs).toBeNull();
    store.detach();
  });
});

describe("reportedTabId", () => {
  test("reads a tab id from the relay envelope or from the payload, never by guessing", () => {
    expect(reportedTabId({ payload: payloadWith(), tabId: 3 })).toBe(3);
    expect(reportedTabId({ payload: payloadWith({ tabId: 4 }) })).toBe(4);
    expect(reportedTabId({ payload: payloadWith() })).toBeUndefined();
    expect(reportedTabId({ payload: payloadWith({ tabId: "3" }) })).toBeUndefined();
  });
});