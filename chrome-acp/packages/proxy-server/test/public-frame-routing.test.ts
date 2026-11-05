import {afterEach, beforeAll, describe, expect, test} from "bun:test";
import {createServer} from "node:net";
import {join} from "node:path";
import {startServer} from "../src/server";

type Message = {type: string; callId?: string; tabId?: number; sessionId?: string; payload?: any};
let port = 0;
const token = "synthetic-frame-routing-token";
const clients: Client[] = [];

class Client {
  ws: WebSocket;
  queue: Message[] = [];
  ready: Promise<void>;
  constructor(path = "/ws") {
    this.ws = new WebSocket(`ws://127.0.0.1:${port}${path}?token=${token}`);
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", () => resolve());
      this.ws.addEventListener("error", () => reject(new Error("Socket failed")));
    });
    this.ws.addEventListener("message", event => this.queue.push(JSON.parse(String(event.data))));
    clients.push(this);
  }
  send(type: string, payload?: any) { this.ws.send(JSON.stringify({type, payload})); }
  frame(tabId: number | undefined, callId?: string) {
    this.ws.send(JSON.stringify({
      type: "frame", tabId, callId,
      payload: {dataUrl: "data:image/jpeg;base64,AAAA", width: 8, height: 6, tsMs: 7},
    }));
  }
  async take(type: string, timeout = 2000): Promise<Message> {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const index = this.queue.findIndex(message => message.type === type);
      if (index >= 0) return this.queue.splice(index, 1)[0]!;
      await Bun.sleep(10);
    }
    throw new Error(`No ${type} message`);
  }
  close() { this.ws.close(); }
}

async function viewer(tabId?: number) {
  const client = new Client();
  await client.ready;
  client.send("connect");
  expect((await client.take("status")).payload.connected).toBe(true);
  client.send("new_session", {cwd: import.meta.dir, tabId});
  await client.take("session_created");
  return client;
}

async function producer() {
  const client = new Client();
  await client.ready;
  client.send("register_executor");
  await client.take("executor_registered");
  return client;
}

beforeAll(async () => {
  port = await new Promise<number>(resolve => {
    const probe = createServer();
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address() as {port: number};
      probe.close(() => resolve(address.port));
    });
  });
  void startServer({
    port, host: "127.0.0.1", token, https: false,
    command: process.execPath, args: [join(import.meta.dir, "fixtures/fake-agent.mjs")],
    cwd: import.meta.dir,
  });
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    try { if ((await fetch(`http://127.0.0.1:${port}/health`)).ok) return; } catch {}
    await Bun.sleep(20);
  }
  throw new Error("Proxy startup timed out");
});

afterEach(async () => {
  for (const client of clients) {
    if (client.ws.readyState === WebSocket.OPEN) client.send("disconnect");
  }
  await Bun.sleep(50);
  for (const client of clients.splice(0)) client.close();
});

describe("public frame routing", () => {
  test("only the producer can send frames, and only to the bound tab", async () => {
    const extension = await producer();
    const first = await viewer(501);
    const second = await viewer(502);
    const impostor = new Client();
    await impostor.ready;
    impostor.frame(501, "forged");
    await expect(first.take("frame", 150)).rejects.toThrow();
    extension.frame(501, "valid");
    const frame = await first.take("frame");
    expect(frame.callId).toBe("valid");
    expect(frame.tabId).toBe(501);
    expect(frame.sessionId).toBe("fake-session");
    await expect(second.take("frame", 150)).rejects.toThrow();
    await expect(extension.take("frame", 150)).rejects.toThrow();
    extension.frame(undefined, "unowned");
    await expect(first.take("frame", 150)).rejects.toThrow();
  });

  test("session switching stops its own tab and rejects late live frames", async () => {
    const extension = await producer();
    const client = await viewer(503);
    client.send("screencast", {enabled: true});
    expect((await extension.take("screencast")).payload).toEqual({enabled: true, tabId: 503});
    client.send("new_session", {cwd: import.meta.dir, tabId: 503});
    expect((await extension.take("screencast")).payload).toEqual({enabled: false, tabId: 503});
    await client.take("session_created");
    extension.frame(503);
    await expect(client.take("frame", 150)).rejects.toThrow();
  });

  test("closing a viewer stops only its tab", async () => {
    const extension = await producer();
    const client = await viewer(504);
    client.send("screencast", {enabled: true});
    await extension.take("screencast");
    client.close();
    expect((await extension.take("screencast")).payload).toEqual({enabled: false, tabId: 504});
  });

  test("an older viewer cannot remove a newer viewer's tab binding", async () => {
    const extension = await producer();
    const older = await viewer(505);
    const newer = await viewer(505);
    older.send("new_session", {cwd: import.meta.dir, tabId: 506});
    await older.take("session_created");
    extension.frame(505, "new-owner");
    expect((await newer.take("frame")).callId).toBe("new-owner");
    await expect(older.take("frame", 150)).rejects.toThrow();
  });

  test("an unbound viewer cannot start or stop another tab's stream", async () => {
    const extension = await producer();
    const client = await viewer();
    client.send("screencast", {enabled: true});
    expect((await client.take("screencast_state")).payload.error).toContain("No browser tab");
    client.send("screencast", {enabled: false});
    await expect(extension.take("screencast", 150)).rejects.toThrow();
  });
});