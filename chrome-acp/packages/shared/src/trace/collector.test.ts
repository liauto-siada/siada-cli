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

  test("a canceled turn closes its open steps as canceled, not complete", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_execute"));
    c.advance(30);
    collector.endRun("canceled");

    const step = collector.snapshot().steps[0]!;
    expect(step.status).toBe("canceled");
    expect(step.durMs).toBe(30);
  });

  test("a failed turn closes its open steps as errors", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_execute"));
    c.advance(12);
    collector.endRun("error");

    const run = collector.snapshot();
    expect(run.steps[0]!.status).toBe("error");
    expect(run.endedAtMs).not.toBeNull();
  });

  test("the first end wins: a later reason cannot rewrite the run", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_execute"));
    c.advance(5);
    collector.endRun("canceled");
    c.advance(500);
    collector.endRun("complete");

    const run = collector.snapshot();
    expect(run.steps[0]!.status).toBe("canceled");
    expect(run.elapsedMs).toBe(5);
    expect(run.endedAtMs).toBe(1_005);
  });

  test("endRun closes only what is still running, never rewriting a measured outcome", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    // A call the agent reported already finished in one shot.
    collector.addSessionUpdate(toolCall("t1", "browser_tabs", "completed"));
    collector.addSessionUpdate(toolCall("t2", "browser_click"));
    c.advance(40);
    collector.addSessionUpdate(toolCallUpdate("t2", "failed"));
    collector.addSessionUpdate(toolCall("t3", "browser_read"));
    c.advance(10);
    collector.addSessionUpdate(toolCallUpdate("t3", "cancelled"));
    collector.addSessionUpdate(toolCall("t4", "browser_execute"));
    c.advance(25);
    collector.endRun("complete");

    const [oneShot, failed, canceled, open] = collector.snapshot().steps;
    // The run-end reason applies only to the call the stream left open: the
    // step that already reported a failure is not rewritten as a success, and
    // the one that was canceled keeps its own verdict.
    expect(oneShot!.status).toBe("complete");
    expect(oneShot!.durMs).toBeNull();
    expect(failed!.status).toBe("error");
    expect(failed!.durMs).toBe(40);
    expect(failed!.tsEndMs).toBe(1_040);
    expect(canceled!.status).toBe("canceled");
    expect(canceled!.durMs).toBe(10);
    expect(open!.status).toBe("complete");
    expect(open!.durMs).toBe(25);
  });

  test("a run keeps its identity across updates and gets a new one on beginRun", () => {
    // Frozen clock: the second run starts in the same millisecond as the first,
    // which is exactly what a timestamp alone cannot tell apart.
    const collector = new TraceCollector({ now: () => 5_000 });
    const first = collector.snapshot();
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.endRun();
    expect(collector.snapshot().runId).toBe(first.runId);

    collector.beginRun();
    const second = collector.snapshot();
    expect(second.startedAtMs).toBe(first.startedAtMs);
    expect(second.runId).toBeDefined();
    expect(second.runId).not.toBe(first.runId);
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

describe("TraceCollector metrics", () => {
  test("parallel calls that overlap are counted once, not summed", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addSessionUpdate(toolCall("t2", "b"));
    collector.addSessionUpdate(toolCall("t3", "c"));
    c.advance(100);
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));
    collector.addSessionUpdate(toolCallUpdate("t2", "completed"));
    collector.addSessionUpdate(toolCallUpdate("t3", "completed"));

    const run = collector.snapshot();
    expect(run.elapsedMs).toBe(100);
    // Summing the three 100 ms calls would claim 300 ms of a 100 ms run and
    // report no time outside tools at all.
    expect(run.metrics.toolMs).toBe(100);
    expect(run.metrics.gapMs).toBe(0);
  });

  test("an overlapping pair merges into its union and untouched time stays outside it", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    c.advance(50);
    collector.addSessionUpdate(toolCall("t2", "b"));
    c.advance(50);
    collector.addSessionUpdate(toolCallUpdate("t1", "completed")); // t1: 0-100
    c.advance(50);
    collector.addSessionUpdate(toolCallUpdate("t2", "completed")); // t2: 50-150
    c.advance(150);
    collector.addSessionUpdate(toolCall("t3", "c"));
    c.advance(100);
    collector.addSessionUpdate(toolCallUpdate("t3", "completed")); // t3: 300-400

    const run = collector.snapshot();
    expect(run.elapsedMs).toBe(400);
    // [0,150] ∪ [300,400]: the three measured calls sum to 300 ms, but 50 ms of
    // that sum is the same wall-clock moment seen twice, and the 150 ms gap is
    // not tool time at all.
    expect(run.metrics.toolMs).toBe(250);
    expect(run.metrics.gapMs).toBe(150);
  });

  test("an open call is measured to now, while an unobserved one-shot adds no duration", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    // The agent reported this call already finished: no start-to-end stretch
    // was observed, so it contributes no duration rather than a guessed one.
    collector.addSessionUpdate(toolCall("t0", "browser_tabs", "completed"));
    c.advance(400);
    collector.addSessionUpdate(toolCall("t1", "browser_execute"));
    c.advance(25);

    const run = collector.snapshot();
    expect(run.elapsedMs).toBe(425);
    expect(run.steps[0]!.durMs).toBeNull();
    // The open call is still running: its observed interval reaches now.
    expect(run.steps[1]!.status).toBe("running");
    expect(run.metrics.toolMs).toBe(25);
    expect(run.metrics.gapMs).toBe(400);
  });
});

describe("TraceCollector frame association", () => {
  test("a frame with no correlation id is standalone even while a step is running", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "browser_click"));
    c.advance(20);

    // Nothing about the timing says this picture is the click's own, so the
    // collector does not pretend it is.
    expect(collector.addFrame(frame("f1", c.now()))).toEqual({
      kind: "standalone",
      reason: "no-correlation",
    });
    const run = collector.snapshot();
    expect(run.steps[0]!.frameKey).toBeUndefined();
    expect(run.frames.map((f) => f.key)).toEqual(["f1"]);
  });

  test("a frame with no correlation id does not attach to the newest step either", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "a"));
    collector.addSessionUpdate(toolCallUpdate("t1", "completed"));
    c.advance(5);
    collector.addFrame(frame("f1", c.now()));

    expect(collector.snapshot().steps[0]!.frameKey).toBeUndefined();
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

  test("an unmatched correlation id leaves the picture standalone", () => {
    const c = clock();
    const collector = new TraceCollector({ now: c.now });
    collector.addSessionUpdate(toolCall("t1", "first"));

    const attachment = collector.addFrame(frame("f1", c.now()), "some-mcp-call-id");

    // The id belongs to something the collector never saw (the capture channel
    // and the ACP stream number their calls differently), so hanging the frame
    // on the running step would invent a before/after pair.
    expect(attachment).toEqual({
      kind: "standalone",
      reason: "unmatched-correlation",
    });
    const run = collector.snapshot();
    expect(run.steps[0]!.frameKey).toBeUndefined();
    expect(run.steps[0]!.frameKeyBefore).toBeUndefined();
    expect(run.frames.map((f) => f.key)).toEqual(["f1"]);
  });

  test("a frame reported on a matched correlation id attaches and says so", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "first"));

    expect(collector.addFrame(frame("f1", 1, "before"), "t1")).toEqual({
      kind: "step",
      stepIndex: 1,
      phase: "before",
    });
    expect(collector.addFrame(frame("f2", 2), "t1")).toEqual({
      kind: "step",
      stepIndex: 1,
      phase: "after",
    });
    expect(collector.addFrame(frame("f3", 3), "other")).toEqual({
      kind: "standalone",
      reason: "unmatched-correlation",
    });
  });

  test("a frame with no correlation id at all is standalone too", () => {
    const collector = new TraceCollector({ now: clock().now });

    expect(collector.addFrame(frame("f1", 1))).toEqual({
      kind: "standalone",
      reason: "no-correlation",
    });
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

describe("TraceCollector page-change observation", () => {
  test("pageChanged starts unobserved and is counted in neither bucket", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "browser_click"));

    const run = collector.snapshot();
    expect(run.steps[0]!.pageChanged).toBeNull();
    // No comparison happened, so the viewer has no "no change" claim to make
    // and the metric must not read as a verified zero.
    expect(run.metrics.changedSteps).toBe(0);
    expect(run.metrics.wastedSteps).toBe(0);
  });

  test("a reported comparison verdict lands on the step and the metrics", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "browser_click"));
    collector.addSessionUpdate(toolCall("t2", "browser_read"));

    expect(collector.reportPageChange("t1", true)).toBe(true);
    expect(collector.reportPageChange("t2", false)).toBe(true);

    const run = collector.snapshot();
    expect(run.steps[0]!.pageChanged).toBe(true);
    expect(run.steps[1]!.pageChanged).toBe(false);
    expect(run.metrics.changedSteps).toBe(1);
    expect(run.metrics.wastedSteps).toBe(1);
  });

  test("a verdict for an unknown step is refused, not attached", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "browser_click"));

    expect(collector.reportPageChange("nope", true)).toBe(false);
    expect(collector.snapshot().steps[0]!.pageChanged).toBeNull();
  });

  test("reporting notifies subscribers so the view can re-render", () => {
    const collector = new TraceCollector({ now: clock().now });
    collector.addSessionUpdate(toolCall("t1", "browser_click"));
    const seen: Array<boolean | null> = [];
    collector.subscribe((run) => seen.push(run.steps[0]!.pageChanged));

    collector.reportPageChange("t1", false);
    // Repeating the same verdict changes nothing, so it stays quiet.
    collector.reportPageChange("t1", false);

    expect(seen).toEqual([false]);
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
