import { describe, expect, test, beforeAll, afterAll, afterEach } from "bun:test";
import { ACPClient } from "./client";
import type { ACPSettings, ConnectionState } from "./types";

// ACPClient talks to a real WebSocket; swap in a controllable fake so server
// responses can be simulated deterministically.
const RealWebSocket = globalThis.WebSocket;

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  url: string;
  sent: { type: string; [key: string]: unknown }[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.readyState = 3;
  }

  // Test-side simulation helpers
  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  message(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }

  fail(): void {
    this.onerror?.();
    this.onclose?.({ code: 1006, reason: "" });
  }

  closeWith(code: number, reason: string): void {
    this.readyState = 3;
    this.onclose?.({ code, reason });
  }

  static get last(): FakeWebSocket {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  }
}

const settings: ACPSettings = {
  proxyUrl: "ws://localhost:9315/ws",
  token: undefined,
  cwd: undefined,
};

function newClient(): { client: ACPClient; states: Array<[ConnectionState, string?]> } {
  const client = new ACPClient(settings);
  const states: Array<[ConnectionState, string?]> = [];
  client.setConnectionStateHandler((state, error) => states.push([state, error]));
  return { client, states };
}

beforeAll(() => {
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeWebSocket;
});

afterAll(() => {
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = RealWebSocket;
});

afterEach(() => {
  FakeWebSocket.instances = [];
});

describe("ACPClient connect error reporting", () => {
  test("proxy error message during connect rejects and stays in error state", async () => {
    const { client, states } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    expect(ws.sent).toEqual([{ type: "connect" }]);

    ws.message({
      type: "error",
      payload: { message: "Failed to connect: agent exited before initialization completed (exit code 3)" },
    });

    await expect(promise).rejects.toThrow("Failed to connect: agent exited");
    expect(client.getState()).toBe("error");
    expect(states.at(-1)).toEqual(["error", "Failed to connect: agent exited before initialization completed (exit code 3)"]);
  });

  test("error message stays visible when a disconnected status follows", async () => {
    const { client, states } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();

    // Server reports the failure, then the agent connection teardown sends
    // status connected:false (and the socket may close too).
    ws.message({ type: "error", payload: { message: "Failed to connect: boom" } });
    ws.message({ type: "status", payload: { connected: false } });
    ws.closeWith(1000, "");

    await expect(promise).rejects.toThrow("Failed to connect: boom");
    expect(client.getState()).toBe("error");
    expect(states.at(-1)).toEqual(["error", "Failed to connect: boom"]);
  });

  test("status connected:false during connect rejects instead of hanging", async () => {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();

    ws.message({ type: "status", payload: { connected: false } });

    await expect(promise).rejects.toThrow("Agent connection failed");
    expect(client.getState()).toBe("error");
  });

  test("transport failure (onerror then onclose) keeps the error state", async () => {
    const { client, states } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();

    // Proxy unreachable: browser fires onerror, then onclose(1006).
    ws.fail();
    // ws://loopback retries once over wss:// — fail that attempt too.
    await new Promise((r) => setTimeout(r, 0));
    FakeWebSocket.last.fail();

    await expect(promise).rejects.toThrow("WebSocket connection error");
    expect(client.getState()).toBe("error");
    // Regression: onclose used to downgrade the state to "disconnected",
    // wiping the error message from the UI.
    expect(states.at(-1)?.[0]).toBe("error");
  });

  test("ws:// to loopback falls back to wss:// on transport failure", async () => {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    expect(ws.url).toBe("ws://localhost:9315/ws");

    ws.fail();
    await new Promise((r) => setTimeout(r, 0));

    const retry = FakeWebSocket.last;
    expect(retry).not.toBe(ws);
    expect(retry.url).toBe("wss://localhost:9315/ws");
    retry.open();
    retry.message({
      type: "status",
      payload: { connected: true, agentInfo: { name: "fake-agent", version: "1" } },
    });

    await promise;
    expect(client.getState()).toBe("connected");
    client.disconnect();
  });

  test("wss:// to loopback falls back to ws:// on transport failure", async () => {
    // Covers setups that stored wss://localhost (e.g. from the old
    // TLS-only proxy) against the untrusted self-signed certificate: the
    // transport fails, the client retries over plaintext ws.
    const client = new ACPClient({ ...settings, proxyUrl: "wss://localhost:9315/ws" });
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    expect(ws.url).toBe("wss://localhost:9315/ws");

    ws.fail();
    await new Promise((r) => setTimeout(r, 0));

    const retry = FakeWebSocket.last;
    expect(retry).not.toBe(ws);
    expect(retry.url).toBe("ws://localhost:9315/ws");
    retry.open();
    retry.message({
      type: "status",
      payload: { connected: true, agentInfo: { name: "fake-agent", version: "1" } },
    });

    await promise;
    expect(client.getState()).toBe("connected");
    client.disconnect();
  });

  test("double transport failure restores the original scheme", async () => {
    const { client } = newClient();
    const first = client.connect();
    FakeWebSocket.last.fail();
    // ws://loopback retries once over wss:// — fail that attempt too.
    await new Promise((r) => setTimeout(r, 0));
    FakeWebSocket.last.fail();
    await expect(first).rejects.toThrow("WebSocket connection error");
    await new Promise((r) => setTimeout(r, 0));

    // The next connect() must start from the ORIGINAL ws:// URL instead of
    // oscillating on the flipped one.
    const second = client.connect();
    expect(FakeWebSocket.last.url).toBe("ws://localhost:9315/ws");
    FakeWebSocket.last.fail();
    await new Promise((r) => setTimeout(r, 0));
    // Fail the wss:// retry of the second connect too.
    FakeWebSocket.last.fail();
    await expect(second).rejects.toThrow("WebSocket connection error");
    client.disconnect();
  });

  test("no scheme fallback when the server rejects with a reason (auth)", async () => {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();

    ws.closeWith(4001, "Unauthorized: Invalid token");

    await expect(promise).rejects.toThrow("Unauthorized: Invalid token");
    await new Promise((r) => setTimeout(r, 0));
    expect(FakeWebSocket.instances.length).toBe(1);
  });

  test("no scheme fallback for non-loopback hosts", async () => {
    const client = new ACPClient({ ...settings, proxyUrl: "ws://10.0.0.5:9315/ws" });
    const promise = client.connect();
    FakeWebSocket.last.fail();

    await expect(promise).rejects.toThrow("WebSocket connection error (ws://10.0.0.5:9315/ws)");
    await new Promise((r) => setTimeout(r, 0));
    expect(FakeWebSocket.instances.length).toBe(1);
    client.disconnect();
  });

  test("close with reason during connect (auth failure) rejects with the reason", async () => {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();

    ws.closeWith(4001, "Unauthorized: Invalid token");

    await expect(promise).rejects.toThrow("Unauthorized: Invalid token");
    expect(client.getState()).toBe("error");
  });

  test("successful connect still resolves and later disconnect shows disconnected", async () => {
    const { client, states } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();

    ws.message({
      type: "status",
      payload: { connected: true, agentInfo: { name: "fake-agent", version: "1" } },
    });
    await promise;
    expect(client.getState()).toBe("connected");

    // Agent dying after a successful connect is a normal disconnect, not an
    // error.
    ws.closeWith(1000, "");
    expect(client.getState()).toBe("disconnected");
    expect(states.at(-1)).toEqual(["disconnected", undefined]);
    client.disconnect();
  });
});
