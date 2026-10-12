import { describe, expect, test, beforeAll, beforeEach, afterEach } from "bun:test";
import { createServer as createNetServer } from "node:net";
import { join } from "node:path";
import { startServer } from "../src/server.ts";

// The live-view channel: the extension's background worker pushes pictures and
// stream state, viewers ask for the live view of the tab their session is bound
// to, and the proxy — not the UI — decides who may receive what. A picture is
// page content, so it is delivered to the client bound to the tab it came from
// and only when the registered extension produced it; everything else is
// dropped rather than broadcast. These tests drive the real server over
// WebSocket with a fake extension standing in for the Chrome background worker.

const fakeAgentPath = join(import.meta.dir, "fixtures", "fake-agent.mjs");
const TOKEN = "live-view-channel-test-token";

// Distinct tab ids per test: the server's tab -> client map is shared by the
// whole process, so reusing one id would let a previous test's close race the
// next test's binding.
const TAB_A = 1001;
const TAB_B = 1002;

interface ProxyMessage {
  type: string;
  callId?: string;
  tabId?: number;
  sessionId?: string | null;
  payload?: Record<string, any>;
}

// Pick a free TCP port so a locally running proxy (default port) can't clash.
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createNetServer();
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address() as { port: number };
      probe.close(() => resolve(port));
    });
    probe.on("error", reject);
  });
}

function openClient(url: string) {
  const ws = new WebSocket(url);
  const queue: ProxyMessage[] = [];
  const waiters: Array<{ type: string; resolve: (message: ProxyMessage) => void }> = [];

  ws.addEventListener("message", (event: MessageEvent) => {
    const message = JSON.parse(String(event.data)) as ProxyMessage;
    const index = waiters.findIndex((candidate) => candidate.type === message.type);
    if (index >= 0) {
      waiters.splice(index, 1)[0]!.resolve(message);
      return;
    }
    queue.push(message);
  });

  const ready = new Promise<void>((resolve, reject) => {
    ws.addEventListener("open", () => resolve());
    ws.addEventListener("error", () => reject(new Error(`ws error (${url})`)));
  });

  return {
    ready,
    close: () => ws.close(),
    send(type: string, payload?: unknown) {
      ws.send(JSON.stringify({ type, payload }));
    },
    /** Messages whose fields sit at the top level (frame, screencast_state). */
    sendRaw(message: object) {
      ws.send(JSON.stringify(message));
    },
    waitFor(type: string, timeoutMs = 8000): Promise<ProxyMessage> {
      const queued = queue.findIndex((message) => message.type === type);
      if (queued >= 0) return Promise.resolve(queue.splice(queued, 1)[0]!);
      return new Promise((resolve, reject) => {
        const waiter = {
          type,
          resolve: (message: ProxyMessage) => {
            clearTimeout(timer);
            resolve(message);
          },
        };
        const timer = setTimeout(() => {
          // Drop the waiter on timeout: a stale entry would otherwise swallow
          // the next message of that type instead of letting a later
          // waitFor() see it.
          const index = waiters.indexOf(waiter);
          if (index >= 0) waiters.splice(index, 1);
          reject(new Error(`timed out waiting for "${type}"`));
        }, timeoutMs);
        waiters.push(waiter);
      });
    },
  };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

let port = 0;
/** Every client a test opened, closed automatically afterwards. */
const opened: ReturnType<typeof openClient>[] = [];

async function openViewer(): Promise<ReturnType<typeof openClient>> {
  const client = openClient(`ws://127.0.0.1:${port}/ws?token=${TOKEN}`);
  opened.push(client);
  await client.ready;
  return client;
}

/** A sidepanel-shaped viewer: connected agent plus the tab it lives in. */
async function openBoundViewer(tabId: number): Promise<ReturnType<typeof openClient>> {
  const client = await openViewer();
  client.send("connect");
  const status = await client.waitFor("status");
  expect(status.payload?.connected).toBe(true);
  client.send("new_session", { cwd: import.meta.dir, tabId });
  await client.waitFor("session_created");
  return client;
}

/** The extension's dedicated tool channel: the only legal frame producer. */
async function registerExtension(): Promise<ReturnType<typeof openClient>> {
  const client = await openViewer();
  client.send("register_executor");
  await client.waitFor("executor_registered");
  return client;
}

function jpeg(tag: string) {
  return { dataUrl: `data:image/jpeg;base64,${tag}`, width: 8, height: 6, tsMs: 7 };
}

let extension: ReturnType<typeof openClient>;

beforeAll(async () => {
  port = await freePort();
  // Never awaited: startServer keeps running (heartbeat, open listener) for
  // the lifetime of the test process.
  void startServer({
    port,
    host: "127.0.0.1",
    command: process.execPath,
    args: [fakeAgentPath],
    cwd: import.meta.dir,
    token: TOKEN,
    https: false,
  });

  const deadline = Date.now() + 10_000;
  for (;;) {
    try {
      const health = await fetch(`http://127.0.0.1:${port}/health`);
      if (health.ok) break;
    } catch {
      // Not listening yet.
    }
    if (Date.now() > deadline) throw new Error("proxy did not become healthy");
    await sleep(200);
  }
}, 30_000);

// A fresh producer per test: one test takes the extension away on purpose, and
// a stale registration must never leak into the next one.
beforeEach(async () => {
  extension = await registerExtension();
});

afterEach(() => {
  for (const client of opened.splice(0)) client.close();
});

describe("live view channel", () => {
  test("a frame reaches only the viewer bound to its tab, and is not echoed back", async () => {
    const viewer = await openBoundViewer(TAB_A);
    const otherTab = await openBoundViewer(TAB_B);
    const payload = jpeg("AAAA");

    extension.sendRaw({ type: "frame", callId: "call-1", tabId: TAB_A, payload });

    const frame = await viewer.waitFor("frame");
    expect(frame.callId).toBe("call-1");
    expect(frame.tabId).toBe(TAB_A);
    expect(frame.payload).toEqual(payload);
    // The picture is attributed to the run it was delivered into, so a viewer
    // can reject one that belongs to a session it has already left.
    expect(frame.sessionId).toBe("fake-session");

    // Another tab's viewer, and the producer itself, must not see it.
    await expect(otherTab.waitFor("frame", 250)).rejects.toThrow();
    await expect(extension.waitFor("frame", 250)).rejects.toThrow();
  });

  test("an untagged frame or state is dropped instead of broadcast", async () => {
    const viewer = await openBoundViewer(TAB_A);

    extension.sendRaw({ type: "frame", callId: "no-tab", payload: jpeg("AA") });
    extension.sendRaw({ type: "screencast_state", payload: { active: true } });

    await expect(viewer.waitFor("frame", 300)).rejects.toThrow();
    await expect(viewer.waitFor("screencast_state", 300)).rejects.toThrow();
  });

  test("a viewer with no bound tab is told why the live view cannot start", async () => {
    const viewer = await openViewer();

    viewer.send("screencast", { enabled: true });

    const state = await viewer.waitFor("screencast_state");
    expect(state.payload).toEqual({
      active: false,
      error: "No browser tab is bound to this session yet.",
    });
    // The request never reaches the extension: there is no tab to attach to.
    await expect(extension.waitFor("screencast", 250)).rejects.toThrow();
  });

  test("going live forwards the viewer's own tab and disconnect stops that tab's stream", async () => {
    const viewer = await openBoundViewer(TAB_A);

    viewer.send("screencast", { enabled: true });
    const forwarded = await extension.waitFor("screencast");
    expect(forwarded.payload).toEqual({ enabled: true, tabId: TAB_A });

    // The extension reports the stream state; it is routed back to the same
    // tab's viewer, tagged with the tab it describes.
    extension.sendRaw({
      type: "screencast_state",
      tabId: TAB_A,
      payload: { active: true, mode: "screencast" },
    });
    const state = await viewer.waitFor("screencast_state");
    expect(state.payload).toMatchObject({ active: true, mode: "screencast", tabId: TAB_A });

    // Live frames flow to the watching viewer.
    extension.sendRaw({ type: "frame", tabId: TAB_A, payload: jpeg("BB") });
    await viewer.waitFor("frame");

    // Leaving the stream running would strand the extension's debugger on the
    // user's tab with nothing watching, so the disconnect path has to stop it —
    // and name the tab so a different tab's stream is untouched.
    viewer.close();
    const stopped = await extension.waitFor("screencast");
    expect(stopped.payload).toEqual({ enabled: false, tabId: TAB_A });
  });

  test("two viewers watching different tabs never see each other's stream", async () => {
    const forA = await openBoundViewer(TAB_A);
    const forB = await openBoundViewer(TAB_B);

    forA.send("screencast", { enabled: true });
    expect((await extension.waitFor("screencast")).payload).toEqual({
      enabled: true,
      tabId: TAB_A,
    });
    forB.send("screencast", { enabled: true });
    expect((await extension.waitFor("screencast")).payload).toEqual({
      enabled: true,
      tabId: TAB_B,
    });

    extension.sendRaw({ type: "frame", tabId: TAB_A, payload: jpeg("AA") });
    expect((await forA.waitFor("frame")).payload?.dataUrl).toBe(
      "data:image/jpeg;base64,AA",
    );
    await expect(forB.waitFor("frame", 300)).rejects.toThrow();

    extension.sendRaw({ type: "frame", tabId: TAB_B, payload: jpeg("BB") });
    expect((await forB.waitFor("frame")).payload?.dataUrl).toBe(
      "data:image/jpeg;base64,BB",
    );
    await expect(forA.waitFor("frame", 300)).rejects.toThrow();
  });

  test("an ordinary viewer cannot forge a frame or a screencast state", async () => {
    const viewer = await openBoundViewer(TAB_A);
    // Connected like any viewer, but never announced as the frame producer.
    const impostor = await openViewer();

    impostor.sendRaw({ type: "frame", callId: "forged", tabId: TAB_A, payload: jpeg("EVIL") });
    impostor.sendRaw({ type: "screencast_state", tabId: TAB_A, payload: { active: true } });

    await expect(viewer.waitFor("frame", 300)).rejects.toThrow();
    await expect(viewer.waitFor("screencast_state", 300)).rejects.toThrow();

    // The real producer still gets through, so the rejections above are the
    // producer check working, not a broken channel.
    extension.sendRaw({ type: "frame", callId: "real", tabId: TAB_A, payload: jpeg("REAL") });
    expect((await viewer.waitFor("frame")).callId).toBe("real");
  });

  test("a late frame for a tab that lost its viewer does not leak to the next viewer", async () => {
    const first = await openBoundViewer(TAB_A);
    first.close();
    // Let the proxy drop the dead tab binding before the next viewer appears.
    await sleep(200);

    const second = await openBoundViewer(TAB_B);

    // A picture the extension had already produced for the closed tab must not
    // surface in the new viewer's timeline...
    extension.sendRaw({ type: "frame", callId: "late", tabId: TAB_A, payload: jpeg("OLD") });
    await expect(second.waitFor("frame", 300)).rejects.toThrow();

    // ...while the live channel still delivers to the right tab afterwards.
    extension.sendRaw({ type: "frame", callId: "now", tabId: TAB_B, payload: jpeg("NEW") });
    expect((await second.waitFor("frame")).callId).toBe("now");
  });

  test("switching sessions stops the stream and drops late frames from the old run", async () => {
    const viewer = await openBoundViewer(TAB_A);
    viewer.send("screencast", { enabled: true });
    await extension.waitFor("screencast");

    // A new session is a new run: the previous run's stream is stopped and
    // named, so the UI learns it is off and the extension frees the tab.
    viewer.send("new_session", { cwd: import.meta.dir, tabId: TAB_A });
    const stop = await extension.waitFor("screencast");
    expect(stop.payload).toEqual({ enabled: false, tabId: TAB_A });
    await viewer.waitFor("session_created");

    // A frame produced before the switch (still in flight) belongs to the old
    // run and must not land in the new one.
    extension.sendRaw({ type: "frame", tabId: TAB_A, payload: jpeg("STALE") });
    await expect(viewer.waitFor("frame", 300)).rejects.toThrow();
  });

  test("with no extension connected the viewer is told, not left hanging", async () => {
    extension.close();
    await sleep(300);

    const viewer = await openBoundViewer(TAB_A);
    viewer.send("screencast", { enabled: true });

    // Every /ws client is registered as a fallback executor, so a request that
    // fell through to it would look "forwarded" and never be answered.
    await expect(viewer.waitFor("screencast", 250)).rejects.toThrow();

    const state = await viewer.waitFor("screencast_state");
    expect(state.payload).toEqual({
      active: false,
      error: "No browser extension connected.",
    });
  });

  test("the channel is behind the auth token", async () => {
    const viewer = await openBoundViewer(TAB_A);
    const evilFrame = JSON.stringify({
      type: "frame",
      callId: "evil",
      tabId: TAB_A,
      payload: { dataUrl: "data:image/jpeg;base64,AA", width: 1, height: 1 },
    });

    // A wrong token is refused with the proxy's unauthorized close code.
    const refused = new WebSocket(`ws://127.0.0.1:${port}/ws?token=wrong-token`);
    const code = await new Promise<number>((resolve, reject) => {
      refused.addEventListener("close", (event) => resolve((event as CloseEvent).code));
      setTimeout(() => reject(new Error("the bad-token connection was not refused")), 8000);
    });
    expect(code).toBe(4001);
    try {
      refused.send(evilFrame);
    } catch {
      // The socket may already be past the point of accepting frames.
    }
    await expect(viewer.waitFor("frame", 250)).rejects.toThrow();

    // A connection that simply has no token is refused as well; only the fact
    // that it never becomes usable is asserted, because the close frame can
    // lose the race with the handshake and surface as an abnormal closure.
    const anonymous = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    await new Promise<void>((resolve) => {
      anonymous.addEventListener("close", () => resolve());
      anonymous.addEventListener("error", () => resolve());
    });
    try {
      anonymous.send(evilFrame);
    } catch {
      // Same as above.
    }
    await expect(viewer.waitFor("frame", 250)).rejects.toThrow();
  });
});