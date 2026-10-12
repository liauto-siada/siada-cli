import { describe, expect, test, beforeAll } from "bun:test";
import { createServer as createNetServer } from "node:net";
import { join } from "node:path";
import { startServer } from "../src/server.ts";

// Prompt failures used to reach the sidepanel and the proxy log as the ACP
// error's generic name — every agent-side failure read "Prompt failed:
// Internal error". These tests drive the real server against a fake agent
// that fails every prompt, and assert the client is told what actually broke.

const fakeAgentPath = join(import.meta.dir, "fixtures", "fake-agent.mjs");
const TOKEN = "prompt-error-display-test-token";
const CAUSE = "BadGatewayError: Error code: 502 LiteLLM Retried: 3 times";

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

interface ProxyMessage {
  type: string;
  payload: Record<string, any>;
}

function openClient(url: string) {
  const ws = new WebSocket(url);
  const queue: ProxyMessage[] = [];
  const waiters: Array<{ type: string; resolve: (payload: Record<string, any>) => void }> = [];

  ws.addEventListener("message", (event: MessageEvent) => {
    const message = JSON.parse(String(event.data)) as ProxyMessage;
    const waiter = waiters.findIndex((candidate) => candidate.type === message.type);
    if (waiter >= 0) {
      waiters.splice(waiter, 1)[0].resolve(message.payload);
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
    waitFor(type: string, timeoutMs = 8000): Promise<Record<string, any>> {
      const queued = queue.findIndex((message) => message.type === type);
      if (queued >= 0) return Promise.resolve(queue.splice(queued, 1)[0].payload);
      return new Promise((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error(`timed out waiting for "${type}"`)),
          timeoutMs,
        );
        waiters.push({
          type,
          resolve: (payload) => {
            clearTimeout(timer);
            resolve(payload);
          },
        });
      });
    },
  };
}

let client: ReturnType<typeof openClient>;

beforeAll(async () => {
  const port = await freePort();
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
    await new Promise((resolve) => setTimeout(resolve, 200));
  }

  client = openClient(`ws://127.0.0.1:${port}/ws?token=${TOKEN}`);
  await client.ready;
  client.send("connect");
  const status = await client.waitFor("status");
  expect(status.connected).toBe(true);
  client.send("new_session", { cwd: import.meta.dir });
  await client.waitFor("session_created");
}, 30_000);

describe("prompt failure reporting", () => {
  test("the agent's specific message is shown", async () => {
    client.send("prompt", { content: [{ type: "text", text: "hello" }] });

    const error = await client.waitFor("error");
    expect(error.message).toBe(`Prompt failed: ${CAUSE}`);
  });

  test("a generic message is replaced by error.data.details", async () => {
    client.send("prompt", {
      content: [{ type: "text", text: "hello (generic-shape)" }],
    });

    const error = await client.waitFor("error");
    expect(error.message).toBe(`Prompt failed: ${CAUSE}`);
  });
});
