import { describe, expect, test, afterEach } from "bun:test";
import {
  executeBrowserTool,
  handleBrowserToolResponse,
  isMcpRequestAuthorized,
  setDedicatedExecutor,
  setFallbackExecutor,
  setMcpAuthToken,
  unregisterExecutor,
} from "../src/mcp/handler.ts";

interface FakeWs {
  readyState: number;
  sent: { type: string; callId: string; params?: unknown }[];
  send(data: string): void;
}

function fakeWs(readyState = 1): FakeWs {
  return {
    readyState,
    sent: [],
    send(data: string) {
      this.sent.push(JSON.parse(data));
    },
  };
}

const created: FakeWs[] = [];

function trackedFakeWs(readyState = 1): FakeWs {
  const ws = fakeWs(readyState);
  created.push(ws);
  return ws;
}

afterEach(() => {
  for (const ws of created.splice(0)) unregisterExecutor(ws);
  setMcpAuthToken(undefined);
});

describe("executor registry", () => {
  test("no executor -> executeBrowserTool rejects", async () => {
    await expect(executeBrowserTool({ action: "tabs" } as never)).rejects.toThrow(
      "No browser extension connected",
    );
  });

  test("fallback executor (legacy sidepanel) serves tool calls", async () => {
    const ws = trackedFakeWs();
    setFallbackExecutor(ws);

    const pending = executeBrowserTool({ action: "tabs" } as never);
    await Bun.sleep(10);
    expect(ws.sent.length).toBe(1);
    handleBrowserToolResponse(
      ws.sent[0].callId,
      { action: "tabs", ok: true, tabs: [] } as never,
    );
    await expect(pending).resolves.toBeTruthy();
  });

  test("dedicated executor preferred over fallback", async () => {
    const fallback = trackedFakeWs();
    const dedicated = trackedFakeWs();
    setFallbackExecutor(fallback);
    setDedicatedExecutor(dedicated);

    const pending = executeBrowserTool({ action: "tabs" } as never);
    await Bun.sleep(10);
    expect(dedicated.sent.length).toBe(1);
    expect(fallback.sent.length).toBe(0);
    handleBrowserToolResponse(dedicated.sent[0].callId, { action: "tabs", ok: true } as never);
    await expect(pending).resolves.toBeTruthy();
  });

  test("unregisterExecutor only removes the closing ws (dedicated survives sidepanel close)", async () => {
    const fallback = trackedFakeWs();
    const dedicated = trackedFakeWs();
    setFallbackExecutor(fallback);
    setDedicatedExecutor(dedicated);

    // sidepanel (fallback) closes: dedicated must keep serving tools
    unregisterExecutor(fallback);
    const pending = executeBrowserTool({ action: "tabs" } as never);
    await Bun.sleep(10);
    expect(dedicated.sent.length).toBe(1);
    handleBrowserToolResponse(dedicated.sent[0].callId, { action: "tabs", ok: true } as never);
    await expect(pending).resolves.toBeTruthy();
  });

  test("stale (non-open) executor is skipped", async () => {
    const stale = trackedFakeWs(3); // CLOSED
    const fresh = trackedFakeWs(1); // OPEN
    setDedicatedExecutor(stale);
    setFallbackExecutor(fresh);

    const pending = executeBrowserTool({ action: "tabs" } as never);
    await Bun.sleep(10);
    expect(fresh.sent.length).toBe(1);
    handleBrowserToolResponse(fresh.sent[0].callId, { action: "tabs", ok: true } as never);
    await expect(pending).resolves.toBeTruthy();
  });
});

describe("mcp auth", () => {
  test("no token configured -> always authorized", () => {
    setMcpAuthToken(undefined);
    expect(isMcpRequestAuthorized(undefined, new URL("http://x/mcp"))).toBeTrue();
  });

  test("token configured -> requires matching Bearer or ?token=", () => {
    setMcpAuthToken("secret");
    expect(isMcpRequestAuthorized(undefined, new URL("http://x/mcp"))).toBeFalse();
    expect(isMcpRequestAuthorized("Bearer wrong", new URL("http://x/mcp"))).toBeFalse();
    expect(isMcpRequestAuthorized("Bearer secret", new URL("http://x/mcp"))).toBeTrue();
    expect(isMcpRequestAuthorized(undefined, new URL("http://x/mcp?token=secret"))).toBeTrue();
    expect(isMcpRequestAuthorized(undefined, new URL("http://x/mcp?token=wrong"))).toBeFalse();
  });
});
