import { afterAll, beforeAll, expect, mock, test } from "bun:test";

const originalChrome = globalThis.chrome;
const originalWebSocket = globalThis.WebSocket;
const sockets: FakeSocket[] = [];
const attached = new Set<number>();
const attachments: number[] = [];
let attachGate: Promise<void> | null = null;
let failAttach = false;

function event() {
  return { addListener: () => {}, removeListener: () => {} };
}

class FakeSocket {
  static OPEN = 1;
  readyState = 1;
  messages: any[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(public url: string) { sockets.push(this); }
  send(message: string) { this.messages.push(JSON.parse(message)); }
  receive(enabled: boolean, tabId?: number) {
    this.onmessage?.({ data: JSON.stringify({ type: "screencast", payload: { enabled, tabId } }) });
  }
}

// Drain promise continuations without involving clocks, Chrome, or a real proxy.
async function settle() {
  for (let i = 0; i < 50; i++) await Promise.resolve();
}

function toolSocket() {
  return sockets.find(socket => new URL(socket.url).pathname === "/ws")!;
}

beforeAll(async () => {
  // Unrelated tool and PDF modules have browser side effects of their own.
  mock.module("./tools/browser", () => ({ executeBrowserTool: async () => ({}) }));
  mock.module("./pdf/pdf-handler", () => ({}));
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
  globalThis.chrome = {
    action: { onClicked: event() },
    runtime: { id: "synthetic-extension", onConnect: event(), onMessage: event() },
    sidePanel: { open: async () => {} },
    storage: {
      local: {
        get: async () => ({ acp_settings: { proxyUrl: "ws://localhost:9315/ws", token: "synthetic-token" } }),
        set: async () => {}, remove: async () => {},
      },
      onChanged: event(),
    },
    alarms: { create: () => {}, onAlarm: event() },
    tabs: { get: async (id: number) => ({ id, active: true }) },
    debugger: {
      onEvent: event(), onDetach: event(),
      attach: async ({ tabId }: { tabId: number }) => {
        attachments.push(tabId);
        await attachGate;
        if (failAttach) throw new Error("Synthetic attach failure");
        attached.add(tabId);
      },
      detach: async ({ tabId }: { tabId: number }) => { attached.delete(tabId); },
      sendCommand: async () => ({}),
    },
  } as unknown as typeof chrome;
  await import("./background");
  await settle();
});

afterAll(() => {
  globalThis.chrome = originalChrome;
  globalThis.WebSocket = originalWebSocket;
  mock.restore();
});

test("the background trajectory connection carries the configured token", () => {
  const trajectory = sockets.find(socket => new URL(socket.url).pathname === "/ws/trajectory")!;
  expect(new URL(trajectory.url).searchParams.get("token")).toBe("synthetic-token");
});

test("a stop for another tab preserves the active stream and reports that tab", async () => {
  const socket = toolSocket();
  socket.receive(true, 501);
  await settle();
  expect(attached.has(501)).toBe(true);
  socket.receive(false, 502);
  await settle();
  expect(attached.has(501)).toBe(true);
  expect(socket.messages.at(-1)).toMatchObject({
    type: "screencast_state", payload: { active: false, tabId: 502 },
  });
  socket.receive(false, 501);
  await settle();
  expect(attached.size).toBe(0);
});

test("a stop during attach runs after startup and releases the debugger", async () => {
  const socket = toolSocket();
  const gate = Promise.withResolvers<void>();
  attachGate = gate.promise;
  try {
    socket.receive(true, 601);
    await settle();
    socket.receive(false, 601);
    await settle();
    gate.resolve();
    await settle();
    expect(attached.size).toBe(0);
    expect(socket.messages.at(-1)).toMatchObject({
      type: "screencast_state", payload: { active: false, tabId: 601 },
    });
  } finally {
    gate.resolve();
    attachGate = null;
  }
});

test("overlapping starts attach each tab once and keep the newest stream stoppable", async () => {
  const socket = toolSocket();
  const gate = Promise.withResolvers<void>();
  attachGate = gate.promise;
  const start = attachments.length;
  try {
    socket.receive(true, 701);
    await settle();
    socket.receive(true, 702);
    await settle();
    expect(attachments.slice(start)).toEqual([701]);
    gate.resolve();
    await settle();
    expect([...attached]).toEqual([702]);
    expect(attachments.slice(start)).toEqual([701, 702]);
    socket.receive(false, 702);
    await settle();
    expect(attached.size).toBe(0);
  } finally {
    gate.resolve();
    attachGate = null;
  }
});

test("a failed start does not prevent the next stream from starting and stopping", async () => {
  const socket = toolSocket();
  failAttach = true;
  try {
    socket.receive(true, 801);
    await settle();
    expect(socket.messages.at(-1)).toMatchObject({
      type: "screencast_state", payload: { active: false, tabId: 801, error: "Synthetic attach failure" },
    });
  } finally {
    failAttach = false;
  }
  socket.receive(true, 802);
  await settle();
  expect([...attached]).toEqual([802]);
  socket.receive(false, 802);
  await settle();
  expect(attached.size).toBe(0);
});