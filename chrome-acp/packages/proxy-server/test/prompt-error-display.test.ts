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
    args: [fakeAgentPath, "--steering"],
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
  await client.waitFor("dir_listing");
}, 30_000);

describe("prompt failure reporting", () => {
  test("the agent's specific message is shown", async () => {
    client.send("prompt", { content: [{ type: "text", text: "hello" }] });

    const error = await client.waitFor("error");
    expect(error.message).toBe(`Prompt failed: ${CAUSE}`);
    expect((await client.waitFor("prompt_complete")).stopReason).toBe("error");
  });

  test("a generic message is replaced by error.data.details", async () => {
    client.send("prompt", {
      content: [{ type: "text", text: "hello (generic-shape)" }],
    });

    const error = await client.waitFor("error");
    expect(error.message).toBe(`Prompt failed: ${CAUSE}`);
    expect((await client.waitFor("prompt_complete")).stopReason).toBe("error");
  });
});

describe("steering protocol", () => {
  test("steering rejection does not complete the prompt, acceptance is independently correlated", async () => {
    client.send("prompt", {
      content: [{ type: "text", text: "steering-hold" }], requestId: "main-steering-test",
    });
    client.send("steer", {
      content: [{ type: "image", mimeType: "image/png", data: "" }], requestId: "rejected-steer",
    });
    const rejected = await client.waitFor("steer_result");
    expect(rejected.requestId).toBe("rejected-steer");
    expect(rejected.accepted).toBe(false);
    client.send("steer", {
      content: [{ type: "text", text: "correction" }], requestId: "accepted-steer",
    });
    const accepted = await client.waitFor("steer_result");
    expect(accepted).toEqual({ requestId: "accepted-steer", accepted: true });
    const completed = await client.waitFor("prompt_complete");
    expect(completed).toMatchObject({
      stopReason: "end_turn", requestId: "main-steering-test", sessionId: "fake-session",
    });
  });
});

describe("file operation response correlation", () => {
  test("missing directories produce a scoped error with the request ID", async () => {
    client.send("list_dir", { path: "removed/target/classes/db", requestId: 101 });
    expect(await client.waitFor("error")).toEqual({
      message: "list_dir failed: removed/target/classes/db",
      operation: "list_dir",
      path: "removed/target/classes/db",
      requestId: 101,
    });
  });

  test("file reads outside the workspace produce a scoped error", async () => {
    client.send("read_file", { path: "../outside.txt", requestId: 102 });
    expect(await client.waitFor("error")).toEqual({
      message: "Access denied or file not found",
      operation: "read_file",
      path: "../outside.txt",
      requestId: 102,
    });
  });

  test("successful file operations echo their request IDs", async () => {
    client.send("list_dir", { path: "fixtures", requestId: 103 });
    const listing = await client.waitFor("dir_listing");
    expect(listing.path).toBe("fixtures");
    expect(listing.requestId).toBe(103);
    expect(listing.items.some((item: { name: string }) => item.name === "fake-agent.mjs")).toBe(true);
    client.send("read_file", { path: "fixtures/fake-agent.mjs", requestId: 104 });
    const file = await client.waitFor("file_content");
    expect(file.path).toBe("fixtures/fake-agent.mjs");
    expect(file.requestId).toBe(104);
    expect(file.content).toContain("jsonrpc");
  });
});
