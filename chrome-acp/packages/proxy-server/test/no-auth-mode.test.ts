import { describe, expect, test, beforeAll, afterAll } from "bun:test";
import { createServer as createNetServer } from "node:net";
import { join } from "node:path";
import { startServer } from "../src/server.ts";

// `--no-auth` is the explicit, user-chosen localhost mode: the token gate is
// off on every endpoint, /ws/trajectory included. This file pins that the
// trajectory gate did not turn that mode into "token required" — the default
// (auth enabled) behaviour is covered by trajectory-auth.test.ts. Both modes
// share module state, so each test file runs its own server.

const fakeAgentPath = join(import.meta.dir, "fixtures", "fake-agent.mjs");
const TAB_ID = 3001;

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
const opened: ReturnType<typeof openClient>[] = [];

function track<T extends ReturnType<typeof openClient>>(client: T): T {
  opened.push(client);
  return client;
}

beforeAll(async () => {
  port = await freePort();
  // No token: the explicit --no-auth mode.
  void startServer({
    port,
    host: "127.0.0.1",
    command: process.execPath,
    args: [fakeAgentPath],
    cwd: import.meta.dir,
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

afterAll(() => {
  for (const client of opened.splice(0)) client.close();
});

describe("--no-auth mode", () => {
  test("both channels accept a client without a token", async () => {
    const wsClient = track(openClient(`ws://127.0.0.1:${port}/ws`));
    await wsClient.ready;

    const trajectory = track(openClient(`ws://127.0.0.1:${port}/ws/trajectory`));
    await trajectory.ready;
  });

  test("an untokened trajectory producer's batch still reaches the handler", async () => {
    const viewer = track(openClient(`ws://127.0.0.1:${port}/ws`));
    await viewer.ready;
    viewer.sendRaw({ type: "connect" });
    await viewer.waitFor("status");
    viewer.sendRaw({ type: "new_session", payload: { cwd: import.meta.dir, tabId: TAB_ID } });
    await viewer.waitFor("session_created");

    const producer = track(openClient(`ws://127.0.0.1:${port}/ws/trajectory`));
    await producer.ready;
    const marker = `no-auth-${Date.now()}`;
    producer.sendRaw({
      type: "trajectory_events",
      payload: [{ ts: 1, type: "navigation", tabId: TAB_ID, marker }],
    });

    const update = await viewer.waitFor("session_update");
    expect(JSON.stringify(update.payload)).toContain(marker);
  }, 15_000);
});