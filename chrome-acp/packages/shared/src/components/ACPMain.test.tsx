import { afterAll, afterEach, beforeAll, expect, mock, test } from "bun:test";
import { act, StrictMode, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ACPClient, type TurnLifecycleEvent } from "../acp/client";
import type { SessionUpdate } from "../acp/types";
import type { TraceRun } from "../trace/types";

let currentRun: TraceRun;
let root: Root | undefined;
const originalActEnvironment = (globalThis as any).IS_REACT_ACT_ENVIRONMENT;

mock.module("./ChatInterface", () => ({
  ChatInterface: ({ onSessionActive }: { onSessionActive?: (id: string) => void }) => {
    useEffect(() => { onSessionActive?.("ui-session"); }, [onSessionActive]);
    return <div>Chat</div>;
  },
}));
mock.module("./FileExplorer", () => ({ FileExplorer: () => null }));
mock.module("./ThreadHistory", () => ({ ThreadHistory: () => null }));
mock.module("./trace/TraceView", () => ({
  TraceView: ({ run }: { run: TraceRun }) => {
    currentRun = run;
    return <div data-testid="trace-status">{run.endedAtMs === null ? "running" : "finished"}</div>;
  },
}));
const { ACPMain } = await import("./ACPMain");

class TestClient extends ACPClient {
  failLiveView = false;
  updates = new Set<(id: string, update: SessionUpdate) => void>();
  turns = new Set<(event: TurnLifecycleEvent) => void>();
  constructor() { super({ proxyUrl: "ws://localhost:9315/ws" }); }
  override getSessionId() { return "ui-session"; }
  override addSessionUpdateListener(handler: (id: string, update: SessionUpdate) => void) {
    this.updates.add(handler);
    return () => { this.updates.delete(handler); };
  }
  override addTurnLifecycleListener(handler: (event: TurnLifecycleEvent) => void) {
    this.turns.add(handler);
    return () => { this.turns.delete(handler); };
  }
  override setScreencast() {
    if (this.failLiveView) throw new Error("Synthetic disconnected live view");
  }
  emit(event: TurnLifecycleEvent) {
    for (const handler of this.turns) handler(event);
  }
  tool() {
    for (const handler of this.updates) handler("ui-session", {
      sessionUpdate: "tool_call", toolCallId: "ui-tool", title: "browser_read", status: "in_progress",
    });
  }
}

beforeAll(() => { (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  document.body.innerHTML = "";
});
afterAll(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = originalActEnvironment;
  mock.restore();
});

test("ACPMain follows request lifecycle once in StrictMode and unsubscribes on unmount", async () => {
  const client = new TestClient();
  const container = document.createElement("div");
  document.body.append(container);
  await act(async () => {
    root = createRoot(container);
    root.render(<StrictMode><ACPMain client={client} /></StrictMode>);
  });
  expect(client.turns.size).toBe(1);
  expect(client.updates.size).toBe(1);
  expect(currentRun!.endedAtMs).not.toBeNull();
  await act(async () => {
    client.emit({ kind: "started", sessionId: "ui-session", requestId: "first" });
    client.tool();
  });
  expect(currentRun!.endedAtMs).toBeNull();
  expect(currentRun!.steps).toHaveLength(1);
  await act(async () => { client.emit({ kind: "cancel-requested", sessionId: "ui-session", requestId: "first" }); });
  expect(currentRun!.endedAtMs).not.toBeNull();
  expect(currentRun!.steps[0]!.status).toBe("canceled");
  await act(async () => { client.emit({ kind: "started", sessionId: "ui-session", requestId: "second" }); });
  expect(currentRun!.steps).toHaveLength(0);
  expect(currentRun!.endedAtMs).toBeNull();
  act(() => root?.unmount());
  root = undefined;
  expect(client.turns.size).toBe(0);
  expect(client.updates.size).toBe(0);
});

test("live-view errors appear in the UI and do not break unmount cleanup", async () => {
  const client = new TestClient();
  client.failLiveView = true;
  const container = document.createElement("div");
  document.body.append(container);
  await act(async () => {
    root = createRoot(container);
    root.render(<ACPMain client={client} />);
  });
  const button = Array.from(container.querySelectorAll("button")).find(value => value.textContent?.includes("Go live"));
  expect(button).toBeDefined();
  await act(async () => { button!.click(); });
  expect(container.textContent).toContain("Synthetic disconnected live view");
  expect(() => act(() => root?.unmount())).not.toThrow();
  root = undefined;
});