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

for (const [mode, createSession, startupCommand] of [
  ["screencast", createScreencast, "Page.startScreencast"],
  ["screenshots", createScreenshotPolling, "Page.getLayoutMetrics"],
] as const) {
  describe(`${mode} startup lifecycle`, () => {
    for (const phase of ["attach", "command"] as const) {
      test(`stop during ${phase} waits for startup and releases the debugger`, async () => {
        const gate = Promise.withResolvers<void>();
        const entered = Promise.withResolvers<void>();
        let attached = false;
        let detachCount = 0;
        let frameCount = 0;
        const states: LiveViewState[] = [];
        const fake = fakeTarget({
          isAttached: () => attached,
          attach: async () => {
            if (phase === "attach") {
              entered.resolve();
              await gate.promise;
            }
            attached = true;
          },
          detach: async () => { attached = false; detachCount++; },
          sendCommand: async (method) => {
            if (phase === "command" && method === startupCommand) {
              entered.resolve();
              await gate.promise;
            }
            return {};
          },
        });
        const session = createSession(fake.target, {
          onFrame: () => { frameCount++; },
          onState: state => states.push(state),
        });
        const starting = session.start();
        await entered.promise;
        let stopped = false;
        const stopping = session.stop().then(() => { stopped = true; });
        try {
          await Promise.resolve();
          expect(stopped).toBe(false);
          gate.resolve();
          await Promise.all([starting, stopping]);
          expect(session.isActive()).toBe(false);
          expect(attached).toBe(false);
          expect(detachCount).toBe(1);
          expect(frameCount).toBe(0);
          expect(states).toEqual([{ active: false, mode }]);
        } finally {
          gate.resolve();
          await Promise.all([starting, stopping]);
          await session.stop();
        }
      });
    }

    test("concurrent starts do not attach the same debugger twice", async () => {
      const gate = Promise.withResolvers<void>();
      let attachCount = 0;
      let attached = false;
      const fake = fakeTarget({
        isAttached: () => attached,
        attach: async () => {
          attachCount++;
          await gate.promise;
          attached = true;
        },
        detach: async () => { attached = false; },
      });
      const session = createSession(fake.target, { onFrame: () => {} });
      const first = session.start();
      const second = session.start();
      try {
        expect(attachCount).toBe(1);
      } finally {
        gate.resolve();
        await Promise.all([first, second]);
        await session.stop();
      }
      expect(attached).toBe(false);
    });
  });
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
});
