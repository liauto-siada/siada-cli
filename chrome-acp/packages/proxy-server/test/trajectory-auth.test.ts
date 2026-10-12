import { describe, expect, test, beforeAll, beforeEach, afterEach } from "bun:test";
import { createServer as createNetServer } from "node:net";
import { join } from "node:path";
import { startServer } from "../src/server.ts";

// The trajectory channel is the machine that writes recorded browser events to
// the user's on-disk history and feeds them into the agent bound to the tab
// they name. It therefore shares /ws's token gate, and these tests pin that
// boundary: a producer without the token (or with a wrong one) never reaches
// the handler, an authorized producer's batch does — observed through the
// agent, which echoes what it receives — and a malformed batch is dropped.
//
// The fake extension's batch is forwarded to the agent only when a client is
// bound to the tab; the viewer opened in beforeEach provides that binding, and
// the echo comes back to it as a session update.

const fakeAgentPath = join(import.meta.dir, "fixtures", "fake-agent.mjs");
const TOKEN = "trajectory-auth-test-token";
const TAB_ID = 2001;

interface ProxyMessage {
  type: string;
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

/**
 * Open a trajectory socket and report how it died: 4001 when the server
 * refused it, 1006 when the close frame lost the race with the handshake.
 * Never resolves while the socket is still usable — a live socket means the
 * gate let an unauthorized producer through.
 */
function refusalCode(url: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(
      () => reject(new Error(`connection was not refused (${url})`)),
      8000,
    );
    ws.addEventListener("close", (event) => {
      clearTimeout(timer);
      resolve((event as CloseEvent).code || 1006);
    });
    ws.addEventListener("error", () => {
      // The close event always follows; the code is resolved there.
    });
  });
}

let port = 0;
/** Every client a test opened, closed automatically afterwards. */
const opened: ReturnType<typeof openClient>[] = [];

async function openViewer(): Promise<ReturnType<typeof openClient>> {
  const client = openClient(`ws://127.0.0.1:${port}/ws?token=${TOKEN}`);
  opened.push(client);
  await client.ready;
  return client;
}

/** A sidepanel-shaped client: connected agent, session bound to one tab. */
async function openBoundViewer(tabId: number): Promise<ReturnType<typeof openClient>> {
  const client = await openViewer();
  client.sendRaw({ type: "connect" });
  await client.waitFor("status");
  client.sendRaw({ type: "new_session", payload: { cwd: import.meta.dir, tabId } });
  await client.waitFor("session_created");
  return client;
}

/** The extension's trajectory producer channel, behind the token gate. */
async function openTrajectoryProducer(): Promise<ReturnType<typeof openClient>> {
  const client = openClient(`ws://127.0.0.1:${port}/ws/trajectory?token=${TOKEN}`);
  opened.push(client);
  await client.ready;
  return client;
}

const TRAJECTORY_URL = () => `ws://127.0.0.1:${port}/ws/trajectory`;

let viewer: ReturnType<typeof openClient>;

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

// A fresh viewer per test: the echo that proves the handler ran is delivered to
// the client bound to the tab, and no assertion may consume another test's
// message.
beforeEach(async () => {
  viewer = await openBoundViewer(TAB_ID);
});

afterEach(() => {
  for (const client of opened.splice(0)) client.close();
});

describe("trajectory channel auth", () => {
  test("a producer without a token never reaches the handler", async () => {
    const code = await refusalCode(TRAJECTORY_URL());
    expect(code).toBe(4001);

    // Even if the refused socket still manages to flush bytes, nothing may be
    // persisted or forwarded: the bound client's agent sees no batch.
    const anonymous = new WebSocket(TRAJECTORY_URL());
    await new Promise<void>((resolve) => {
      anonymous.addEventListener("close", () => resolve());
      anonymous.addEventListener("error", () => resolve());
    });
    try {
      anonymous.send(
        JSON.stringify({
          type: "trajectory_events",
          payload: [{ ts: 1, type: "navigation", tabId: TAB_ID, marker: "no-token" }],
        }),
      );
    } catch {
      // The socket was already closed for writing.
    }

    await expect(viewer.waitFor("session_update", 600)).rejects.toThrow();
  });

  test("a producer with a wrong token is refused", async () => {
    const code = await refusalCode(`${TRAJECTORY_URL()}?token=wrong-token`);
    expect(code).toBe(4001);
    await expect(viewer.waitFor("session_update", 600)).rejects.toThrow();
  });

  test("an authorized producer's batch reaches the handler and the bound agent", async () => {
    const producer = await openTrajectoryProducer();
    const marker = `authorized-${Date.now()}`;

    producer.sendRaw({
      type: "trajectory_events",
      payload: [
        {
          ts: 1,
          type: "navigation",
          url: "https://example.com",
          title: "Example",
          tabId: TAB_ID,
          marker,
        },
      ],
    });

    // The agent subprocess echoed the notification it received, which is only
    // possible if the batch made it through the handler.
    const update = await viewer.waitFor("session_update");
    expect(JSON.stringify(update.payload)).toContain(marker);
  });

  test("a malformed batch from an authorized producer is dropped whole", async () => {
    const producer = await openTrajectoryProducer();

    producer.sendRaw({ type: "trajectory_events", payload: [42, "not-an-event"] });

    await expect(viewer.waitFor("session_update", 600)).rejects.toThrow();
  });
});