import { describe, expect, test } from "bun:test";
import { TraceCollector, mapToolStatus } from "./collector";
import {
  createBufferedFrameSource,
  frameFromBase64,
  frameFromDataUrl,
} from "./frame-source";
import type { SessionUpdate } from "../acp/types";
import type { TraceFrame } from "./types";

/** Controllable clock so every duration assertion is exact. */
function clock(start = 1_000) {
  let value = start;
  return {
    now: () => value,
    advance: (ms: number) => {
      value += ms;
    },
  };
}

function toolCall(
  toolCallId: string,
  title: string,
  status = "in_progress",
  rawInput?: Record<string, unknown>,
): SessionUpdate {
  return { sessionUpdate: "tool_call", toolCallId, title, status, rawInput };
}

function toolCallUpdate(
  toolCallId: string,
  status: string,
  title?: string,
): SessionUpdate {
  return { sessionUpdate: "tool_call_update", toolCallId, status, title };
}

function frame(
  key: string,
  tsMs: number,
  phase: TraceFrame["phase"] = "after",
): TraceFrame {
  return {
    key,
    tsMs,
    phase,
    dataUrl: "data:image/jpeg;base64,AAAA",
    width: 1120,
    height: 780,
  };
}

describe("TraceCollector durations", () => {
  test("measures a tool call from open to terminal update", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });

    collector.addSessionUpdate(toolCall("t1", "browser_click"));
    c.advance(341);
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));

    const run = collector.snapshot();
    expect(run.steps).toHaveLength(1);
    expect(run.steps[0]!.durMs).toBe(341);
    expect(run.steps[0]!.status).toBe("complete");
    expect(run.steps[0]!.tsEndMs! - run.steps[0]!.tsStartMs).toBe(341);
  });

  test("advancing the clock does not rewrite a closed step's duration", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_read"));
    c.advance(100);
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));
    c.advance(5_000);

    expect(collector.snapshot().steps[0]!.durMs).toBe(100);
  });

  test("a call that arrives already terminal keeps durMs null", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "browser_tabs", "completed"));

    const step = collector.snapshot().steps[0]!;
    expect(step.status).toBe("complete");
    expect(step.durMs).toBeNull();
  });

  test("failed and cancelled updates map onto error and canceled", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addSessionUpdate(toolCall("t2", "b"));
    c.advance(10);
    collector.addSessionUpdate(toolCallUpdate("t1", "failed"));
    collector.addSessionUpdate(toolCallUpdate("t2", "cancelled"));

    const [a, b] = collector.snapshot().steps;
    expect(a!.status).toBe("error");
    expect(b!.status).toBe("canceled");
  });

  test("updates for an unknown tool call are ignored", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCallUpdate("nope", "completed"));
    expect(collector.snapshot().steps).toHaveLength(0);
  });

  test("non tool-call updates are ignored", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate({
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "hi" },
    } as SessionUpdate);
    collector.addSessionUpdate({
      sessionUpdate: "user_message_chunk",
      content: { type: "text", text: "go" },
    } as SessionUpdate);
    expect(collector.snapshot().steps).toHaveLength(0);
  });

  test("mapToolStatus covers unknown statuses as running", () => {
    expect(mapToolStatus("completed")).toBe("complete");
    expect(mapToolStatus("failed")).toBe("error");
    expect(mapToolStatus("cancelled")).toBe("canceled");
    expect(mapToolStatus(undefined)).toBe("running");
    expect(mapToolStatus("whatever")).toBe("running");
  });
});

describe("TraceCollector run lifecycle", () => {
  test("elapsed keeps ticking while the run is open and freezes on endRun", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    c.advance(250);
    expect(collector.snapshot().elapsedMs).toBe(250);

    collector.endRun();
    c.advance(1_000);
    const run = collector.snapshot();
    expect(run.elapsedMs).toBe(250);
    expect(run.endedAtMs).toBe(1_250);
  });

  test("endRun closes steps that never received a terminal update", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_execute"));
    c.advance(30);
    collector.endRun();

    const step = collector.snapshot().steps[0]!;
    expect(step.status).toBe("complete");
    expect(step.durMs).toBe(30);
  });

  test("beginRun discards previous steps and frames", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addFrame(frame("f1", c.now()));
    collector.beginRun({ url: "https://example.com", task: "search" });

    const run = collector.snapshot();
    expect(run.steps).toHaveLength(0);
    expect(run.frames).toHaveLength(0);
    expect(run.url).toBe("https://example.com");
    expect(run.task).toBe("search");
  });

  test("metrics split measured tool time from the unattributed gap", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    c.advance(100);
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));
    c.advance(900);
    collector.addSessionUpdate(toolCall("t2", "b"));
    c.advance(50);
    collector.addSessionUpdate(toolCallUpdate("t2", "completed"));

    const { metrics, elapsedMs } = collector.snapshot();
    expect(elapsedMs).toBe(1_050);
    expect(metrics.stepCount).toBe(2);
    expect(metrics.toolMs).toBe(150);
    expect(metrics.gapMs).toBe(900);
  });

  test("partially overlapping tool calls count their shared interval once", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    c.advance(25);
    collector.addSessionUpdate(toolCall("a", "first"));
    c.advance(50);
    collector.addSessionUpdate(toolCall("b", "second"));
    c.advance(50);
    collector.addSessionUpdate(toolCallUpdate("a", "completed"));
    c.advance(50);
    collector.addSessionUpdate(toolCallUpdate("b", "completed"));
    c.advance(25);
    const run = collector.snapshot();
    expect(run.steps.map(step => step.durMs)).toEqual([100, 100]);
    expect(run.elapsedMs).toBe(200);
    expect(run.metrics.toolMs).toBe(150);
    expect(run.metrics.gapMs).toBe(50);
  });

  test("nested calls and disjoint intervals preserve the uncovered gaps", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    c.advance(10);
    collector.addSessionUpdate(toolCall("outer", "outer"));
    c.advance(10);
    collector.addSessionUpdate(toolCall("inner", "inner"));
    c.advance(10);
    collector.addSessionUpdate(toolCallUpdate("inner", "completed"));
    c.advance(80);
    collector.addSessionUpdate(toolCallUpdate("outer", "completed"));
    c.advance(20);
    collector.addSessionUpdate(toolCall("last", "last"));
    c.advance(20);
    collector.addSessionUpdate(toolCallUpdate("last", "completed"));
    const run = collector.snapshot();
    expect(run.elapsedMs).toBe(150);
    expect(run.metrics.toolMs).toBe(120);
    expect(run.metrics.gapMs).toBe(30);
  });

  test("running tools contribute elapsed coverage and freeze when the request fails", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    c.advance(20);
    collector.addSessionUpdate(toolCall("a", "first"));
    c.advance(40);
    collector.addSessionUpdate(toolCall("b", "second"));
    c.advance(50);
    const live = collector.snapshot();
    expect(live.steps.map(step => step.durMs)).toEqual([null, null]);
    expect(live.metrics.toolMs).toBe(90);
    expect(live.metrics.gapMs).toBe(20);
    collector.endRun("error");
    c.advance(1_000);
    const ended = collector.snapshot();
    expect(ended.elapsedMs).toBe(110);
    expect(ended.metrics).toEqual(live.metrics);
    expect(ended.steps.map(step => step.status)).toEqual(["error", "error"]);
  });

  test("one-shot terminal calls do not invent an observed tool interval", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    c.advance(20);
    collector.addSessionUpdate(toolCall("instant", "finished", "completed"));
    c.advance(20);
    const run = collector.snapshot();
    expect(run.metrics.toolMs).toBe(0);
    expect(run.metrics.gapMs).toBe(40);
  });

  test("a snapshot uses a single clock reading for run and tool coverage", () => {
    let reads = 0;
    const collector = new TraceCollector({ now: () => ++reads });
    collector.addSessionUpdate(toolCall("a", "first"));
    const before = reads;
    const run = collector.snapshot();
    expect(reads - before).toBe(1);
    expect(run.elapsedMs).toBe(2);
    expect(run.metrics.toolMs).toBe(1);
    expect(run.metrics.gapMs).toBe(1);
  });

  test("notifies subscribers and stops after unsubscribe", () => {
    const collector = new TraceCollector({ now: clock().now });
    const seen: number[] = [];
    const off = collector.subscribe((run) => seen.push(run.steps.length));

    collector.addSessionUpdate(toolCall("t1", "a"));
    off();
    collector.addSessionUpdate(toolCall("t2", "b"));

    expect(seen).toEqual([1]);
  });

  test("indexes steps from 1 and keeps them in arrival order", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "first"));
    collector.addSessionUpdate(toolCall("t2", "second"));

    const steps = collector.snapshot().steps;
    expect(steps.map((s) => s.i)).toEqual([1, 2]);
    expect(steps.map((s) => s.action)).toEqual(["first", "second"]);
  });
});

describe("TraceCollector frame association", () => {
  test("a matched frame lands on the running step and reports its attachment", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_click"));
    c.advance(20);
    expect(collector.addFrame(frame("f1", c.now()), "t1")).toEqual({
      kind: "step", stepIndex: 1, phase: "after",
    });

    expect(collector.snapshot().steps[0]!.frameKey).toBe("f1");
  });

  test("an uncorrelated frame stays standalone even when a completed step exists", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));
    c.advance(5);
    expect(collector.addFrame(frame("f1", c.now()))).toEqual({
      kind: "standalone", reason: "no-correlation",
    });

    expect(collector.snapshot().steps[0]!.frameKey).toBeUndefined();
    expect(collector.snapshot().frames.map(value => value.key)).toEqual(["f1"]);
  });

  test("evicting an old frame drops the step reference to it", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now, maxFrames: 1 });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addFrame(frame("f1", c.now()), "t1");
    collector.addSessionUpdate(toolCall("t2", "b"));
    collector.addFrame(frame("f2", c.now()), "t2");

    const steps = collector.snapshot().steps;
    expect(steps[0]!.frameKey).toBeUndefined();
    expect(steps[1]!.frameKey).toBe("f2");
  });

  test("a correlation id pins the frame to its own step", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "first"));
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));
    collector.addSessionUpdate(toolCall("t2", "second"));
    collector.addFrame(frame("f1", c.now()), "t1");

    const steps = collector.snapshot().steps;
    expect(steps[0]!.frameKey).toBe("f1");
    expect(steps[1]!.frameKey).toBeUndefined();
  });

  test("an unknown correlation cannot claim the running step's before/after slots", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "first"));
    expect(collector.addFrame(frame("f1", c.now()), "gone")).toEqual({
      kind: "standalone", reason: "unmatched-correlation",
    });
    collector.addFrame(frame("b1", c.now(), "before"), "gone");
    collector.addFrame(frame("live", c.now()));

    const run = collector.snapshot();
    expect(run.steps[0]!.frameKey).toBeUndefined();
    expect(run.steps[0]!.frameKeyBefore).toBeUndefined();
    expect(run.frames.map(value => value.key)).toEqual(["f1", "b1", "live"]);
  });

  test("a before frame fills the before slot, not the after slot", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_execute"));

    collector.addFrame(frame("b1", c.now(), "before"), "t1");
    collector.addFrame(frame("a1", c.now(), "after"), "t1");

    const step = collector.snapshot().steps[0]!;
    expect(step.frameKeyBefore).toBe("b1");
    expect(step.frameKey).toBe("a1");
  });

  test("evicting old frames clears both the before and after slots", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now, maxFrames: 2 });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addFrame(frame("b1", c.now(), "before"), "t1");
    collector.addFrame(frame("a1", c.now(), "after"), "t1");
    collector.addFrame(frame("a2", c.now(), "after"), "t1");

    const step = collector.snapshot().steps[0]!;
    // b1 fell out of the frame window, so the overlay pair is gone; the after
    // slot tracks the newest picture.
    expect(step.frameKeyBefore).toBeUndefined();
    expect(step.frameKey).toBe("a2");
  });

  test("input text becomes the step target and value", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(
      toolCall("t1", "browser_execute", "in_progress", { text: "Zurich" }),
    );

    const step = collector.snapshot().steps[0]!;
    expect(step.target?.label).toBe("Zurich");
    expect(step.value).toBe("Zurich");
  });
});

describe("buffered frame source", () => {
  test("current returns the newest frame and frameFor looks up by key", () => {
    const source = createBufferedFrameSource();
    source.push(frame("f1", 1));
    source.push(frame("f2", 2));

    expect(source.current()?.key).toBe("f2");
    expect(source.frameFor("f1")?.key).toBe("f1");
    expect(source.frameFor("missing")).toBeNull();
  });

  test("history is bounded and evicted keys stop resolving", () => {
    const source = createBufferedFrameSource({ maxFrames: 2 });
    source.push(frame("f1", 1));
    source.push(frame("f2", 2));
    source.push(frame("f3", 3));

    expect(source.size()).toBe(2);
    expect(source.frameFor("f1")).toBeNull();
    expect(source.frameFor("f3")?.key).toBe("f3");
  });

  test("subscribers receive pushed frames", () => {
    const source = createBufferedFrameSource();
    const keys: string[] = [];
    const off = source.subscribe((f) => keys.push(f.key));
    source.push(frame("f1", 1));
    off();
    source.push(frame("f2", 2));

    expect(keys).toEqual(["f1"]);
  });

  test("frameFromBase64 builds a data URL and a unique key", () => {
    const a = frameFromBase64({ base64: "AAAA", width: 100, height: 50, tsMs: 7 });
    const b = frameFromBase64({ base64: "BBBB", width: 100, height: 50, tsMs: 7 });

    expect(a.dataUrl).toBe("data:image/jpeg;base64,AAAA");
    expect(a.width).toBe(100);
    expect(a.tsMs).toBe(7);
    expect(a.key).not.toBe(b.key);
  });

  test("frameFromDataUrl keeps the data URL and marks an unknown size as 0", () => {
    const frame = frameFromDataUrl({
      dataUrl: "data:image/jpeg;base64,ZZZZ",
      tsMs: 42,
      url: "https://example.com",
    });

    expect(frame.dataUrl).toBe("data:image/jpeg;base64,ZZZZ");
    expect(frame.tsMs).toBe(42);
    expect(frame.width).toBe(0);
    expect(frame.height).toBe(0);
    expect(frame.url).toBe("https://example.com");
  });
});
