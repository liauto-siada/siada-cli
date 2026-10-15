import { describe, expect, test, beforeAll, afterAll, afterEach } from "bun:test";
import { ACPClient } from "./client";
import type { ACPSettings, ConnectionState, SessionUpdate } from "./types";

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

describe("ACPClient session update listeners", () => {
  const update = {
    sessionUpdate: "tool_call",
    toolCallId: "t1",
    title: "browser_click",
    status: "completed",
  };

  /** Only tool-call variants carry an id; narrow before reading it. */
  function correlationOf(u: SessionUpdate): string {
    return "toolCallId" in u ? u.toolCallId : "?";
  }

  async function connected() {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: { connected: true } });
    await promise;
    return { client, ws };
  }

  test("extra listeners observe updates in addition to the primary handler", async () => {
    const { client, ws } = await connected();
    const primary: string[] = [];
    const extra: string[] = [];
    client.setSessionUpdateHandler((_sessionId, u) => primary.push(correlationOf(u)));
    client.addSessionUpdateListener((_sessionId, u) => extra.push(correlationOf(u)));

    ws.message({ type: "session_update", payload: { sessionId: "s1", update } });

    expect(primary).toEqual(["t1"]);
    expect(extra).toEqual(["t1"]);
    client.disconnect();
  });

  test("unsubscribing stops delivery without affecting the primary handler", async () => {
    const { client, ws } = await connected();
    const primary: string[] = [];
    const extra: string[] = [];
    client.setSessionUpdateHandler((_sessionId, u) => primary.push(correlationOf(u)));
    const off = client.addSessionUpdateListener((_sessionId, u) => extra.push(correlationOf(u)));

    off();
    ws.message({ type: "session_update", payload: { sessionId: "s1", update } });

    expect(extra).toEqual([]);
    expect(primary).toEqual(["t1"]);
    client.disconnect();
  });
});

describe("ACPClient turn lifecycle listeners", () => {
  async function connected() {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: { connected: true } });
    await promise;
    ws.message({ type: "session_created", payload: { sessionId: "s1" } });
    return { client, ws };
  }

  test("sending a prompt reports the turn as started", async () => {
    const { client, ws } = await connected();
    const events: Array<{ kind: string }> = [];
    client.addTurnLifecycleListener((event) => events.push(event));

    await client.sendPrompt("go");

    expect(events).toEqual([{ kind: "started" }]);
    expect(ws.sent.at(-1)).toEqual({
      type: "prompt",
      payload: { content: [{ type: "text", text: "go" }] },
    });
    client.disconnect();
  });

  test("prompt_complete reports how the turn ended, cancel included", async () => {
    const { client, ws } = await connected();
    const events: Array<{ kind: string }> = [];
    client.addTurnLifecycleListener((event) => events.push(event));

    ws.message({ type: "prompt_complete", payload: { stopReason: "end_turn" } });
    ws.message({ type: "prompt_complete", payload: { stopReason: "cancelled" } });

    expect(events).toEqual([
      { kind: "completed", stopReason: "end_turn" },
      { kind: "completed", stopReason: "cancelled" },
    ]);
    client.disconnect();
  });

  test("a cancel request is reported without waiting for the agent", async () => {
    const { client, ws } = await connected();
    const events: Array<{ kind: string }> = [];
    client.addTurnLifecycleListener((event) => events.push(event));

    client.cancel();

    expect(events).toEqual([{ kind: "cancel-requested" }]);
    expect(ws.sent.at(-1)).toEqual({ type: "cancel" });
    client.disconnect();
  });

  test("a proxy error reports the turn as failed with its message", async () => {
    const { client, ws } = await connected();
    const events: Array<{ kind: string }> = [];
    client.addTurnLifecycleListener((event) => events.push(event));

    ws.message({ type: "error", payload: { message: "BadGatewayError: 502" } });

    expect(events).toEqual([{ kind: "failed", message: "BadGatewayError: 502" }]);
    client.disconnect();
  });

  test("a dropped connection after a turn ends the stream", async () => {
    const { client, ws } = await connected();
    const events: Array<{ kind: string }> = [];
    client.addTurnLifecycleListener((event) => events.push(event));

    client.disconnect();
    expect(events).toEqual([{ kind: "disconnected", error: undefined }]);

    // A socket that dies on its own reports the same thing once (the state is
    // no longer "connected", so the second transition stays quiet).
    const second = await connected();
    const secondEvents: Array<{ kind: string }> = [];
    second.client.addTurnLifecycleListener((event) => secondEvents.push(event));
    second.ws.closeWith(1006, "");
    second.client.disconnect();

    expect(secondEvents).toEqual([{ kind: "disconnected", error: undefined }]);
  });

  test("unsubscribing stops lifecycle delivery without affecting the primary handler", async () => {
    const { client, ws } = await connected();
    const primary: string[] = [];
    const extra: string[] = [];
    client.setPromptCompleteHandler((stopReason) => primary.push(stopReason));
    const off = client.addTurnLifecycleListener((event) => extra.push(event.kind));

    off();
    ws.message({ type: "prompt_complete", payload: { stopReason: "end_turn" } });

    expect(extra).toEqual([]);
    expect(primary).toEqual(["end_turn"]);
    client.disconnect();
  });

  test("a listener that throws does not break the connection's own handling", async () => {
    const { client, ws } = await connected();
    const seen: string[] = [];
    const originalError = console.error;
    console.error = () => {};
    try {
      client.addTurnLifecycleListener(() => {
        throw new Error("listener bug");
      });
      client.addTurnLifecycleListener((event) => seen.push(event.kind));

      await client.sendPrompt("go");
      ws.message({ type: "prompt_complete", payload: { stopReason: "end_turn" } });
    } finally {
      console.error = originalError;
    }

    // The other listeners and the primary handlers still ran in order.
    expect(seen).toEqual(["started", "completed"]);
    client.disconnect();
  });
});

describe("ACPClient file operation errors", () => {
  async function connected() {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: { connected: true, capabilities: { sessionCapabilities: { list: {} } } } });
    await promise;
    return { client, ws };
  }

  test("directory failure rejects immediately without reaching chat or session operations", async () => {
    const { client, ws } = await connected();
    const errors: string[] = [];
    client.setErrorHandler(message => errors.push(message));
    const sessions = client.listSessions();
    const listing = client.listDir("target/classes/db");
    const requestId = (ws.sent.at(-1)?.payload as { requestId: number }).requestId;
    ws.message({
      type: "error",
      payload: { operation: "list_dir", path: "target/classes/db", requestId, message: "list_dir failed: target/classes/db" },
    });
    await expect(listing).rejects.toThrow("list_dir failed");
    ws.message({ type: "session_list", payload: { sessions: [], hasMore: false } });
    expect((await sessions).sessions).toEqual([]);
    expect(errors).toEqual([]);
    expect(client.getState()).toBe("connected");
    client.disconnect();
  });

  test("file read failure only rejects its corresponding request", async () => {
    const { client, ws } = await connected();
    const errors: string[] = [];
    client.setErrorHandler(message => errors.push(message));
    const read = client.readFile("missing.txt");
    const requestId = (ws.sent.at(-1)?.payload as { requestId: number }).requestId;
    const listing = client.listDir("");
    ws.message({
      type: "error",
      payload: { operation: "read_file", path: "missing.txt", requestId, message: "Access denied or file not found" },
    });
    await expect(read).rejects.toThrow("Access denied");
    ws.message({ type: "dir_listing", payload: { path: "", items: [] } });
    expect(await listing).toEqual([]);
    expect(errors).toEqual([]);
    client.disconnect();
  });

  test("concurrent listings of the same path match out-of-order responses", async () => {
    const { client, ws } = await connected();
    const first = client.listDir("src");
    const firstId = (ws.sent.at(-1)?.payload as { requestId: number }).requestId;
    const second = client.listDir("src");
    const secondId = (ws.sent.at(-1)?.payload as { requestId: number }).requestId;
    const items = [{ path: "src/a.ts", name: "a.ts", type: "file" }];
    ws.message({ type: "dir_listing", payload: { path: "src", requestId: secondId, items } });
    expect(await second).toEqual(items);
    ws.message({ type: "error", payload: { operation: "list_dir", path: "src", requestId: firstId, message: "Directory removed" } });
    await expect(first).rejects.toThrow("Directory removed");
    client.disconnect();
  });

  test("legacy path-only listings settle every caller for the path", async () => {
    const { client, ws } = await connected();
    const first = client.listDir("src");
    const second = client.listDir("src");
    ws.message({ type: "dir_listing", payload: { path: "src", items: [] } });
    expect(await Promise.all([first, second])).toEqual([[], []]);
    client.disconnect();
  });

  test("concurrent reads of the same file match their request IDs", async () => {
    const { client, ws } = await connected();
    const first = client.readFile("src/a.ts");
    const firstId = (ws.sent.at(-1)?.payload as { requestId: number }).requestId;
    const second = client.readFile("src/a.ts");
    const secondId = (ws.sent.at(-1)?.payload as { requestId: number }).requestId;
    const payload = { path: "src/a.ts", size: 3, truncated: false, binary: false };
    ws.message({ type: "file_content", payload: { ...payload, requestId: secondId, content: "new" } });
    ws.message({ type: "file_content", payload: { ...payload, requestId: firstId, content: "old" } });
    expect((await first).content).toBe("old");
    expect((await second).content).toBe("new");
    client.disconnect();
  });

  test("disconnect rejects pending file operations", async () => {
    const { client } = await connected();
    const listing = client.listDir("src");
    const reading = client.readFile("src/a.ts");
    const settled = Promise.allSettled([listing, reading]);
    client.disconnect();
    const results = await settled;
    expect(results.map(result => result.status)).toEqual(["rejected", "rejected"]);
    for (const result of results) {
      if (result.status === "rejected") expect(result.reason.message).toBe("Disconnected");
    }
  });

  test("legacy list errors and late file errors never enter chat", async () => {
    const { client, ws } = await connected();
    const errors: string[] = [];
    client.setErrorHandler(message => errors.push(message));
    const listing = client.listDir("");
    ws.message({ type: "error", payload: { message: "list_dir failed: (root)" } });
    await expect(listing).rejects.toThrow("list_dir failed");
    ws.message({ type: "error", payload: { operation: "list_dir", path: "gone", requestId: 999, message: "Directory removed" } });
    expect(errors).toEqual([]);
    ws.message({ type: "error", payload: { message: "Prompt failed: model unavailable" } });
    expect(errors).toEqual(["Prompt failed: model unavailable"]);
    client.disconnect();
  });

  test("late correlated listings are not treated as server pushes", async () => {
    const { client, ws } = await connected();
    const pushes: string[] = [];
    client.setDirListingPushHandler(path => pushes.push(path));
    ws.message({ type: "dir_listing", payload: { path: "old", requestId: 999, items: [] } });
    ws.message({ type: "dir_listing", payload: { path: "", items: [] } });
    expect(pushes).toEqual([""]);
    client.disconnect();
  });
});

describe("ACPClient frame listeners", () => {
  async function connected() {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: { connected: true } });
    await promise;
    return { client, ws };
  }

  const payload = {
    dataUrl: "data:image/jpeg;base64,AAAA",
    width: 1120,
    height: 780,
    tsMs: 5,
  };

  test("frames reach every listener with their call id", async () => {
    const { client, ws } = await connected();
    const first: Array<string | undefined> = [];
    const second: Array<string | undefined> = [];
    client.onFrame((f) => first.push(f.callId));
    client.onFrame((f) => second.push(f.callId));

    ws.message({ type: "frame", callId: "call-1", payload });

    expect(first).toEqual(["call-1"]);
    expect(second).toEqual(["call-1"]);
    client.disconnect();
  });

  test("unsubscribing stops frame delivery", async () => {
    const { client, ws } = await connected();
    const seen: number[] = [];
    const off = client.onFrame((f) => seen.push(f.payload.width));

    off();
    ws.message({ type: "frame", callId: "call-1", payload });

    expect(seen).toEqual([]);
    client.disconnect();
  });

  test("the relay's tab and run tags reach frame listeners", async () => {
    const { client, ws } = await connected();
    const seen: Array<{ tabId?: number; sessionId?: string }> = [];
    client.onFrame((f) => seen.push({ tabId: f.tabId, sessionId: f.sessionId }));

    // The relay adds both; a picture from a producer that does not is passed on
    // with them undefined rather than invented.
    ws.message({ type: "frame", callId: "call-1", tabId: 7, sessionId: "s1", payload });
    ws.message({ type: "frame", payload });

    expect(seen).toEqual([
      { tabId: 7, sessionId: "s1" },
      { tabId: undefined, sessionId: undefined },
    ]);
    client.disconnect();
  });

  test("setScreencast asks the proxy to start and stop the live view", async () => {
    const { client, ws } = await connected();

    client.setScreencast(true);
    client.setScreencast(false);

    expect(ws.sent).toEqual([
      { type: "connect" },
      { type: "screencast", payload: { enabled: true } },
      { type: "screencast", payload: { enabled: false } },
    ]);
    client.disconnect();
  });

  test("stopping live view after manual disconnect is safe for UI cleanup", async () => {
    const { client, ws } = await connected();
    client.setScreencast(true);
    client.disconnect();
    const sent = [...ws.sent];

    expect(() => client.setScreencast(false)).not.toThrow();
    expect(() => client.setScreencast(false)).not.toThrow();
    expect(ws.sent).toEqual(sent);
    expect(() => client.setScreencast(true)).toThrow("WebSocket not connected");
  });

  test("stopping live view after a transport close is safe for UI cleanup", async () => {
    const { client, ws } = await connected();
    ws.closeWith(1006, "");
    const sent = [...ws.sent];

    expect(() => client.setScreencast(false)).not.toThrow();
    expect(ws.sent).toEqual(sent);
    client.disconnect();
  });

  test("screencast state reaches listeners, including failures", async () => {
    const { client, ws } = await connected();
    const states: Array<{ active: boolean; error?: string }> = [];
    const off = client.onScreencastState((state) => states.push(state));

    ws.message({ type: "screencast_state", payload: { active: true } });
    ws.message({
      type: "screencast_state",
      payload: { active: false, error: "No browser extension connected." },
    });
    off();
    ws.message({ type: "screencast_state", payload: { active: true } });

    expect(states).toEqual([
      { active: true },
      { active: false, error: "No browser extension connected." },
    ]);
    client.disconnect();
  });
});
