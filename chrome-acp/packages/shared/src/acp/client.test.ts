import { describe, expect, test, beforeAll, afterAll, afterEach } from "bun:test";
import { ACPClient, type TurnLifecycleEvent } from "./client";
import type { ACPSettings, ConnectionState, SessionUpdate } from "./types";
import { createTraceStore } from "../components/trace/trace-store";

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

describe("ACPClient sidepanel retention", () => {
  test("unmount detaches while explicit disconnect still destroys the session", async () => {
    const id = "11111111-1111-4111-8111-111111111111";
    const client = new ACPClient(settings, id);
    const connected = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    expect(ws.sent[0]).toEqual({ type: "connect", payload: { retentionId: id } });
    ws.message({ type: "status", payload: { connected: true, retainedSessionId: "previous-session" } });
    await connected;
    expect(client.retainedSessionId).toBe("previous-session");
    client.disconnect({ retainSession: true });
    expect(ws.sent.some(message => message.type === "disconnect")).toBe(false);
    expect(ws.readyState).toBe(3);

    const reconnected = client.connect();
    const next = FakeWebSocket.last;
    next.open();
    next.message({ type: "status", payload: { connected: true } });
    await reconnected;
    expect(client.retainedSessionId).toBeNull();
    client.disconnect();
    expect(next.sent.at(-1)).toEqual({ type: "disconnect" });
  });

  test("clients without a stable identity preserve immediate disconnect behavior", async () => {
    const client = new ACPClient(settings);
    const connected = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: { connected: true } });
    await connected;
    client.disconnect({ retainSession: true });
    expect(ws.sent.at(-1)).toEqual({ type: "disconnect" });
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

  test("throwing primary and additional listeners do not block other consumers", async () => {
    const { client, ws } = await connected();
    const seen: string[] = [];
    client.setSessionUpdateHandler(() => { throw new Error("Synthetic UI error"); });
    client.addSessionUpdateListener(() => { throw new Error("Synthetic observer error"); });
    client.addSessionUpdateListener((_id, value) => seen.push(correlationOf(value)));
    ws.message({ type: "session_update", payload: { sessionId: "s1", update } });
    expect(seen).toEqual(["t1"]);
    client.disconnect();
  });
});

describe("ACPClient Trace lifecycle integration", () => {
  async function connected() {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: { connected: true } });
    await promise;
    ws.message({ type: "session_created", payload: { sessionId: "trace-session" } });
    let now = 1000;
    const store = createTraceStore({ now: () => now });
    store.attach(client);
    store.setSession("trace-session");
    return { client, ws, store, advance: (ms: number) => { now += ms; } };
  }
  function tool(ws: FakeWebSocket, id: string, status = "in_progress", sessionId = "trace-session") {
    ws.message({ type: "session_update", payload: {
      sessionId, update: { sessionUpdate: "tool_call", toolCallId: id, title: "browser_read", status },
    } });
  }

  test("idle sessions do not run a clock; prompts start and completion freezes it", async () => {
    const { client, ws, store, advance } = await connected();
    try {
      advance(500);
      expect(store.collector.snapshot().elapsedMs).toBe(0);
      tool(ws, "replayed");
      expect(store.collector.snapshot().steps).toHaveLength(0);
      await client.sendPrompt("First task", "first");
      tool(ws, "failed-tool", "failed");
      tool(ws, "running-tool");
      tool(ws, "foreign", "in_progress", "another-session");
      advance(30);
      ws.message({ type: "prompt_complete", payload: {
        stopReason: "end_turn", sessionId: "trace-session", requestId: "first",
      } });
      advance(1000);
      expect(store.collector.snapshot().elapsedMs).toBe(30);
      expect(store.collector.snapshot().steps.map(step => step.status)).toEqual(["error", "complete"]);
    } finally { store.detach(); client.disconnect(); }
  });

  test("cancel closes unfinished steps and a delayed completion cannot finish the next prompt", async () => {
    const { client, ws, store, advance } = await connected();
    try {
      await client.sendPrompt("First", "first");
      tool(ws, "first-tool");
      advance(20);
      client.cancel();
      expect(store.collector.snapshot().steps[0]!.status).toBe("canceled");
      await client.sendPrompt("Next", "next");
      tool(ws, "next-tool");
      ws.message({ type: "prompt_complete", payload: {
        stopReason: "cancelled", sessionId: "trace-session", requestId: "first",
      } });
      expect(store.collector.snapshot().endedAtMs).toBeNull();
      advance(40);
      ws.message({ type: "prompt_complete", payload: {
        stopReason: "end_turn", sessionId: "trace-session", requestId: "next",
      } });
      expect(store.collector.snapshot().elapsedMs).toBe(40);
      expect(store.collector.snapshot().steps.map(step => step.action)).toEqual(["browser_read"]);
    } finally { store.detach(); client.disconnect(); }
  });

  for (const ending of ["error", "close", "cancelled"] as const) {
    test(`${ending} ends the trace with the correct unfinished-step status`, async () => {
      const { client, ws, store, advance } = await connected();
      try {
        await client.sendPrompt("Task", "task");
        tool(ws, "tool");
        advance(50);
        if (ending === "error") ws.message({ type: "error", payload: { message: "Synthetic failure" } });
        else if (ending === "close") ws.closeWith(1006, "");
        else ws.message({ type: "prompt_complete", payload: { stopReason: "cancelled", requestId: "task" } });
        advance(1000);
        expect(store.collector.snapshot().elapsedMs).toBe(50);
        expect(store.collector.snapshot().steps[0]!.status).toBe(ending === "cancelled" ? "canceled" : "error");
      } finally { store.detach(); client.disconnect(); }
    });
  }

  test("completion notifications precede a queued prompt dispatched by the primary callback", async () => {
    const { client, ws, store } = await connected();
    try {
      await client.sendPrompt("First", "first");
      client.setPromptCompleteHandler(() => { void client.sendPrompt("Second", "second"); });
      ws.message({ type: "prompt_complete", payload: { stopReason: "end_turn", requestId: "first" } });
      expect(store.collector.snapshot().endedAtMs).toBeNull();
      tool(ws, "second-tool");
      expect(store.collector.snapshot().steps).toHaveLength(1);
    } finally {
      client.setPromptCompleteHandler(() => {});
      store.detach(); client.disconnect();
    }
  });

  test("session switches discard pictures and reject previous-session updates and completions", async () => {
    const { client, ws, store } = await connected();
    try {
      await client.sendPrompt("First", "first");
      tool(ws, "first-tool");
      const payload = { dataUrl: "data:image/jpeg;base64,AAAA", width: 8, height: 6, tsMs: 1 };
      ws.message({ type: "frame", sessionId: "trace-session", callId: "first-tool", payload });
      expect(store.frames.size()).toBe(1);
      ws.message({ type: "session_created", payload: { sessionId: "next-session" } });
      store.setSession("next-session");
      expect(store.frames.size()).toBe(0);
      await client.sendPrompt("Second", "second");
      tool(ws, "stale-tool");
      ws.message({ type: "frame", sessionId: "trace-session", payload });
      ws.message({ type: "prompt_complete", payload: {
        sessionId: "trace-session", requestId: "first", stopReason: "end_turn",
      } });
      expect(store.collector.snapshot().steps).toHaveLength(0);
      expect(store.frames.size()).toBe(0);
      expect(store.collector.snapshot().endedAtMs).toBeNull();
    } finally { store.detach(); client.disconnect(); }
  });

  test("lifecycle listeners isolate exceptions and unsubscribe without replacing chat handlers", async () => {
    const { client, ws, store } = await connected();
    const seen: TurnLifecycleEvent[] = [];
    const primary: string[] = [];
    client.addTurnLifecycleListener(() => { throw new Error("Synthetic lifecycle error"); });
    const off = client.addTurnLifecycleListener(event => seen.push(event));
    client.setPromptCompleteHandler(reason => primary.push(reason));
    try {
      await client.sendPrompt("Task", "task");
      off();
      ws.message({ type: "prompt_complete", payload: { stopReason: "end_turn", requestId: "task" } });
      expect(seen.map(event => event.kind)).toEqual(["started"]);
      expect(primary).toEqual(["end_turn"]);
      expect(store.collector.snapshot().endedAtMs).not.toBeNull();
    } finally { store.detach(); client.disconnect(); }
  });

  test("reattaching does not duplicate delivery, and detach stops delivery", async () => {
    const { client, ws, store } = await connected();
    try {
      store.attach(client);
      await client.sendPrompt("Task", "task");
      tool(ws, "tool");
      expect(store.collector.snapshot().steps).toHaveLength(1);
      store.detach();
      tool(ws, "detached");
      expect(store.collector.snapshot().steps).toHaveLength(1);
    } finally { store.detach(); client.disconnect(); }
  });

  test("tab evidence is preserved and wrong-tab pictures are rejected", async () => {
    const { client, ws, store } = await connected();
    try {
      store.setTab(501, "trace-session");
      const payload = { dataUrl: "data:image/jpeg;base64,AAAA", width: 8, height: 6, tsMs: 1 };
      ws.message({ type: "frame", sessionId: "trace-session", tabId: 502, payload });
      expect(store.frames.size()).toBe(0);
      ws.message({ type: "frame", sessionId: "trace-session", tabId: 501, payload });
      expect(store.frames.size()).toBe(1);
      // A stale asynchronous tab lookup cannot change the current binding.
      store.setTab(502, "old-session");
      ws.message({ type: "frame", sessionId: "trace-session", tabId: 502, payload });
      expect(store.frames.size()).toBe(1);
    } finally { store.detach(); client.disconnect(); }
  });

  test("picture verdicts cannot cross runs even when correlation IDs and clocks are reused", async () => {
    const { client, ws, store } = await connected();
    try {
      await client.sendPrompt("First", "first");
      tool(ws, "reused");
      const previousId = store.collector.snapshot().runId;
      store.reportPageChange("reused", true, previousId);
      expect(store.collector.snapshot().metrics.changedSteps).toBe(1);
      await client.sendPrompt("Second", "second");
      tool(ws, "reused");
      const nextId = store.collector.snapshot().runId;
      expect(nextId).not.toBe(previousId);
      store.reportPageChange("reused", false, previousId);
      expect(store.collector.snapshot().steps[0]!.pageChanged).toBeNull();
      store.reportPageChange("reused", false, nextId);
      expect(store.collector.snapshot().metrics.wastedSteps).toBe(1);
    } finally { store.detach(); client.disconnect(); }
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
    ws.message({ type: "session_created", payload: { sessionId: "frame-test-session" } });
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

    ws.message({ type: "frame", callId: "call-1", sessionId: "frame-test-session", payload });

    expect(first).toEqual(["call-1"]);
    expect(second).toEqual(["call-1"]);
    client.disconnect();
  });

  test("unsubscribing stops frame delivery", async () => {
    const { client, ws } = await connected();
    const seen: number[] = [];
    const off = client.onFrame((f) => seen.push(f.payload.width));

    off();
    ws.message({ type: "frame", callId: "call-1", sessionId: "frame-test-session", payload });

    expect(seen).toEqual([]);
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

  test("unowned frames and frames from an earlier session are dropped", async () => {
    const { client, ws } = await connected();
    const seen: Array<string | undefined> = [];
    client.onFrame(frame => seen.push(frame.callId));
    ws.message({ type: "frame", callId: "unowned", payload });
    ws.message({ type: "frame", callId: "foreign", sessionId: "other-session", payload });
    ws.message({ type: "session_created", payload: { sessionId: "next-session" } });
    ws.message({ type: "frame", callId: "stale", sessionId: "frame-test-session", payload });
    ws.message({ type: "frame", callId: "current", sessionId: "next-session", payload });
    expect(seen).toEqual(["current"]);
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

describe("ACPClient steering", () => {
  async function connected() {
    const { client } = newClient();
    const promise = client.connect();
    const ws = FakeWebSocket.last;
    ws.open();
    ws.message({ type: "status", payload: {
      connected: true, capabilities: { _meta: { siada: { steering: true } } },
    } });
    await promise;
    ws.message({ type: "session_created", payload: { sessionId: "steering-session" } });
    return { client, ws };
  }

  test("steering acknowledgements are correlated and do not complete the current prompt", async () => {
    const { client, ws } = await connected();
    const completed: string[] = [];
    client.setPromptCompleteHandler((reason) => completed.push(reason));
    await client.sendPrompt("main task", "main");
    const accepted = client.steer([{ type: "text", text: "correction" }], "steer-1");
    const rejected = client.steer([{ type: "text", text: "another" }], "steer-2");
    ws.message({ type: "steer_result", payload: { requestId: "steer-2", accepted: false, error: "busy" } });
    await expect(rejected).rejects.toThrow("busy");
    ws.message({ type: "steer_result", payload: { requestId: "steer-1", accepted: true } });
    await accepted;
    expect(completed).toEqual([]);
    ws.message({ type: "prompt_complete", payload: { stopReason: "end_turn", requestId: "main", sessionId: "steering-session" } });
    expect(completed).toEqual(["end_turn"]);
    client.disconnect();
  });

  test("transport close rejects pending steering and pauses the active prompt", async () => {
    const { client, ws } = await connected();
    const completed: string[] = [];
    client.setPromptCompleteHandler((reason) => completed.push(reason));
    await client.sendPrompt("main task", "main");
    const steering = client.steer([{ type: "text", text: "correction" }], "steer-1");
    ws.closeWith(1006, "");
    await expect(steering).rejects.toThrow("Disconnected");
    expect(completed).toEqual(["disconnected"]);
    client.disconnect();
  });
});
