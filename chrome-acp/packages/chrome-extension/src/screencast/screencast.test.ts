import { describe, expect, test } from "bun:test";
import {
  createScreencast,
  createScreenshotPolling,
  type LiveViewState,
  type ScreencastTarget,
} from "./screencast";

/** Fake CDP target recording every command the session issues. */
function fakeTarget(overrides: Partial<ScreencastTarget> = {}) {
  const commands: Array<{ method: string; params?: Record<string, unknown> }> = [];
  let attached = false;
  let listener: ((method: string, params: Record<string, unknown>) => void) | null = null;
  let unsubscribed = 0;

  const target: ScreencastTarget = {
    attach: async () => {
      attached = true;
    },
    detach: async () => {
      attached = false;
    },
    isAttached: () => attached,
    sendCommand: async (method, params) => {
      // Acked frames throw nowhere; anything else is recorded in order.
      commands.push({ method, params });
      return {};
    },
    onEvent: (l) => {
      listener = l;
      return () => {
        unsubscribed++;
        listener = null;
      };
    },
    ...overrides,
  };

  return {
    target,
    commands,
    isAttached: () => attached,
    unsubscribed: () => unsubscribed,
    emit: (method: string, params: Record<string, unknown>) => listener?.(method, params),
  };
}

function frameEvent(sessionId: number, data = "AAAA") {
  return {
    sessionId,
    data,
    metadata: { deviceWidth: 1120, deviceHeight: 780 },
  };
}

describe("createScreencast", () => {
  test("start attaches, subscribes, then enables the stream in order", async () => {
    const fake = fakeTarget();
    const session = createScreencast(fake.target, { onFrame: () => {} });

    await session.start();

    expect(fake.isAttached()).toBe(true);
    // Focus emulation comes first: without it Chrome composites nothing for a
    // tab that is not the user's focused one, and the stream would be empty.
    expect(fake.commands.map((c) => c.method)).toEqual([
      "Emulation.setFocusEmulationEnabled",
      "Page.startScreencast",
    ]);
    expect(fake.commands[1]!.params).toMatchObject({
      format: "jpeg",
      quality: 60,
      everyNthFrame: 1,
    });
    expect(session.isActive()).toBe(true);
  });

  test("start is idempotent while active", async () => {
    const fake = fakeTarget();
    const session = createScreencast(fake.target, { onFrame: () => {} });
    await session.start();
    await session.start();

    expect(fake.commands.filter((c) => c.method === "Page.startScreencast")).toHaveLength(1);
  });

  test("each frame is acked before it is emitted", async () => {
    const fake = fakeTarget();
    const seen: Array<{ width: number; dataUrl: string }> = [];
    const session = createScreencast(fake.target, {
      onFrame: (frame) => {
        // The ack must already be on the wire, or Chrome throttles the stream.
        expect(fake.commands.some((c) => c.method === "Page.screencastFrameAck")).toBe(true);
        seen.push({ width: frame.width, dataUrl: frame.dataUrl });
      },
      now: () => 42,
    });
    await session.start();
    fake.emit("Page.screencastFrame", frameEvent(7));

    expect(fake.commands).toContainEqual({
      method: "Page.screencastFrameAck",
      params: { sessionId: 7 },
    });
    expect(seen).toEqual([
      { width: 1120, dataUrl: "data:image/jpeg;base64,AAAA" },
    ]);
  });

  test("frames still flow when the consumer throws", async () => {
    const fake = fakeTarget();
    const session = createScreencast(fake.target, {
      onFrame: () => {
        throw new Error("render failed");
      },
    });
    await session.start();

    expect(() => fake.emit("Page.screencastFrame", frameEvent(1))).not.toThrow();
    expect(session.isActive()).toBe(true);
  });

  test("a frame without data is acked but not emitted", async () => {
    const fake = fakeTarget();
    let frames = 0;
    const session = createScreencast(fake.target, { onFrame: () => frames++ });
    await session.start();
    fake.emit("Page.screencastFrame", { sessionId: 3, data: "", metadata: {} });

    expect(frames).toBe(0);
    expect(fake.commands).toContainEqual({
      method: "Page.screencastFrameAck",
      params: { sessionId: 3 },
    });
  });

  test("stop disables the stream, unsubscribes and detaches", async () => {
    const fake = fakeTarget();
    const states: LiveViewState[] = [];
    const session = createScreencast(fake.target, {
      onFrame: () => {},
      onState: (s) => states.push(s),
    });
    await session.start();
    await session.stop();

    expect(fake.commands.map((c) => c.method)).toEqual([
      "Emulation.setFocusEmulationEnabled",
      "Page.startScreencast",
      "Page.stopScreencast",
      "Emulation.setFocusEmulationEnabled",
    ]);
    expect(fake.unsubscribed()).toBe(1);
    expect(fake.isAttached()).toBe(false);
    expect(session.isActive()).toBe(false);
    expect(states).toEqual([
      { active: true, mode: "screencast" },
      { active: false, mode: "screencast" },
    ]);
  });

  test("stop leaves a debugger it did not attach alone", async () => {
    const fake = fakeTarget();
    await fake.target.attach();
    const session = createScreencast(fake.target, { onFrame: () => {} });
    await session.start();
    await session.stop();

    // isAttached() was already true, so teardown must not detach someone
    // else's session.
    expect(fake.commands.some((c) => c.method === "Page.stopScreencast")).toBe(true);
  });

  test("a failing start reports the error, cleans up and stays inactive", async () => {
    const fake = fakeTarget({
      sendCommand: async (method) => {
        if (method === "Page.startScreencast") throw new Error("Another debugger is already attached");
        return {};
      },
    });
    const states: LiveViewState[] = [];
    const session = createScreencast(fake.target, {
      onFrame: () => {},
      onState: (s) => states.push(s),
    });

    await session.start();

    expect(session.isActive()).toBe(false);
    expect(states).toEqual([
      { active: false, error: "Another debugger is already attached", mode: "screencast" },
    ]);
    expect(fake.unsubscribed()).toBe(1);
    expect(fake.isAttached()).toBe(false);
  });

  test("stop tolerates a vanished target", async () => {
    const fake = fakeTarget({
      sendCommand: async (method) => {
        if (method === "Page.stopScreencast") throw new Error("No target with given id");
        return {};
      },
      detach: async () => {
        throw new Error("Debugger is not attached");
      },
    });
    const session = createScreencast(fake.target, { onFrame: () => {} });
    await session.start();

    await expect(session.stop()).resolves.toBeUndefined();
    expect(session.isActive()).toBe(false);
  });

  test("a stop that lands mid-start undoes the start instead of going live", async () => {
    let releaseAttach: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      releaseAttach = resolve;
    });
    let detaches = 0;
    const fake = fakeTarget({
      attach: async () => {
        await gate;
      },
      detach: async () => {
        detaches += 1;
      },
    });
    const states: LiveViewState[] = [];
    const session = createScreencast(fake.target, {
      onFrame: () => {},
      onState: (s) => states.push(s),
    });

    // The viewer leaves again while the debugger is still attaching. Without
    // the guard the start would go live afterwards with nobody holding a
    // handle, leaving the debugger attached to the user's tab for good.
    const start = session.start();
    const stop = session.stop();
    releaseAttach();
    await start;
    await stop;

    expect(session.isActive()).toBe(false);
    expect(fake.commands.some((c) => c.method === "Page.startScreencast")).toBe(false);
    expect(detaches).toBe(1);
    expect(states).toEqual([{ active: false, mode: "screencast" }]);
  });

  test("a second start while the first is attaching does not attach twice", async () => {
    let releaseAttach: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      releaseAttach = resolve;
    });
    let attaches = 0;
    const fake = fakeTarget({
      attach: async () => {
        attaches += 1;
        await gate;
      },
    });
    const session = createScreencast(fake.target, { onFrame: () => {} });

    const first = session.start();
    const second = session.start();
    releaseAttach();
    await first;
    await second;

    expect(attaches).toBe(1);
    expect(fake.commands.filter((c) => c.method === "Page.startScreencast")).toHaveLength(1);
    expect(session.isActive()).toBe(true);
  });
});

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("createScreenshotPolling", () => {
  test("start reads the layout metrics and reports the screenshots mode", async () => {
    const fake = fakeTarget({
      sendCommand: async (method) => {
        fake.commands.push({ method });
        if (method === "Page.getLayoutMetrics") {
          return { cssVisualViewport: { clientWidth: 1200, clientHeight: 700 } };
        }
        return { data: "AAAA" };
      },
    });
    const session = createScreenshotPolling(fake.target, {
      onFrame: () => {},
      intervalMs: 100,
    });

    await session.start();

    expect(fake.isAttached()).toBe(true);
    expect(session.isActive()).toBe(true);
    await session.stop();
  });

  test("frames carry the size from the layout metrics", async () => {
    const fake = fakeTarget({
      sendCommand: async (method) => {
        if (method === "Page.getLayoutMetrics") {
          return { cssVisualViewport: { clientWidth: 1000, clientHeight: 600 } };
        }
        return { data: "FRAME" };
      },
    });
    const frames: Array<{
      dataUrl: string;
      width: number;
      height: number;
      tsMs: number;
    }> = [];
    const session = createScreenshotPolling(fake.target, {
      onFrame: (f) => frames.push(f),
      intervalMs: 100,
      now: () => 5,
    });

    await session.start();
    await sleep(160);
    await session.stop();
    const count = frames.length;

    expect(count).toBeGreaterThanOrEqual(1);
    expect(frames[0]).toEqual({
      dataUrl: "data:image/jpeg;base64,FRAME",
      width: 1000,
      height: 600,
      tsMs: 5,
    });

    // Stopping must actually stop the polling loop.
    await sleep(250);
    expect(frames.length).toBe(count);
  });

  test("gives up after repeated capture failures and reports why", async () => {
    const fake = fakeTarget({
      sendCommand: async (method) => {
        if (method === "Page.getLayoutMetrics") {
          return { cssVisualViewport: { clientWidth: 10, clientHeight: 10 } };
        }
        throw new Error("Cannot capture screenshot of a crashed tab");
      },
    });
    const states: LiveViewState[] = [];
    const session = createScreenshotPolling(fake.target, {
      onFrame: () => {},
      intervalMs: 100,
      maxFailures: 2,
      onState: (s) => states.push(s),
    });

    await session.start();
    await sleep(400);

    expect(session.isActive()).toBe(false);
    expect(states.at(-1)).toEqual({
      active: false,
      error: "Cannot capture screenshot of a crashed tab",
      mode: "screenshots",
    });
    expect(fake.isAttached()).toBe(false);
  });

  test("an empty screenshot response counts as a failure", async () => {
    const fake = fakeTarget({
      sendCommand: async (method) => {
        if (method === "Page.getLayoutMetrics") {
          return { cssVisualViewport: { clientWidth: 10, clientHeight: 10 } };
        }
        return { data: "" };
      },
    });
    const states: LiveViewState[] = [];
    const session = createScreenshotPolling(fake.target, {
      onFrame: () => {},
      intervalMs: 100,
      maxFailures: 2,
      onState: (s) => states.push(s),
    });

    await session.start();
    await sleep(400);

    expect(states.at(-1)).toEqual({
      active: false,
      error: "empty screenshot",
      mode: "screenshots",
    });
  });

  test("a failing start reports the error and does not poll", async () => {
    const fake = fakeTarget({
      attach: async () => {
        throw new Error("Another debugger is already attached");
      },
    });
    const states: LiveViewState[] = [];
    const session = createScreenshotPolling(fake.target, {
      onFrame: () => {},
      intervalMs: 100,
      onState: (s) => states.push(s),
    });

    await session.start();

    expect(session.isActive()).toBe(false);
    expect(states).toEqual([
      { active: false, error: "Another debugger is already attached", mode: "screenshots" },
    ]);
  });

  test("stop is a no-op when nothing was started", async () => {
    const fake = fakeTarget();
    const states: LiveViewState[] = [];
    const session = createScreenshotPolling(fake.target, {
      onFrame: () => {},
      onState: (s) => states.push(s),
    });

    await session.stop();

    expect(states).toEqual([]);
    expect(fake.commands).toEqual([]);
  });

  test("a stop that lands mid-start never starts polling", async () => {
    let releaseAttach: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      releaseAttach = resolve;
    });
    let detaches = 0;
    const fake = fakeTarget({
      attach: async () => {
        await gate;
      },
      detach: async () => {
        detaches += 1;
      },
    });
    const states: LiveViewState[] = [];
    const frames: unknown[] = [];
    const session = createScreenshotPolling(fake.target, {
      onFrame: (f) => frames.push(f),
      intervalMs: 100,
      onState: (s) => states.push(s),
    });

    const start = session.start();
    const stop = session.stop();
    releaseAttach();
    await start;
    await stop;
    await sleep(200);

    expect(session.isActive()).toBe(false);
    expect(frames).toEqual([]);
    expect(fake.commands.some((c) => c.method === "Page.getLayoutMetrics")).toBe(false);
    expect(detaches).toBe(1);
    expect(states).toEqual([{ active: false, mode: "screenshots" }]);
  });
});
