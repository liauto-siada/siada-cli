import { describe, expect, mock, test } from "bun:test";
import { DEFAULT_SETTINGS } from "@chrome-acp/shared/acp";
import { discoverLocalSettings, localBootstrapUrl } from "./local-bootstrap";

const ID = "a".repeat(32);
const settings = { ...DEFAULT_SETTINGS, proxyUrl: "ws://localhost:19315/ws", token: "old" };
const payload = { schemaVersion: 1, proxyUrl: "ws://127.0.0.1:19315/ws", token: "synthetic" };

describe("extension local discovery", () => {
  test("drops query credentials and uses loopback HTTP", () => {
    expect(localBootstrapUrl("wss://localhost:19315/ws?token=old")).toBe("http://localhost:19315/local-bootstrap");
    expect(localBootstrapUrl("ws://[::1]:9315/ws")).toBe("http://[::1]:9315/local-bootstrap");
    expect(localBootstrapUrl("wss://proxy.example.test/ws")).toBeNull();
    expect(localBootstrapUrl("ws://localhost.example.test/ws")).toBeNull();
  });

  test("obtains token while preserving other connection settings", async () => {
    const fetcher = mock(async () => Response.json(payload));
    const result = await discoverLocalSettings(settings, ID, fetcher);
    expect(result).toEqual({ ...settings, proxyUrl: payload.proxyUrl, token: payload.token });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  test("remote connection never requests or replaces its token", async () => {
    const fetcher = mock(async () => Response.json(payload));
    expect(await discoverLocalSettings({ ...settings, proxyUrl: "wss://proxy.example.test/ws" }, ID, fetcher)).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });

  test("offline or unauthorized discovery preserves manual fallback", async () => {
    expect(await discoverLocalSettings(settings, ID, async () => { throw new Error("offline"); })).toBeNull();
    expect(await discoverLocalSettings(settings, ID, async () => new Response("Forbidden", { status: 403 }))).toBeNull();
  });

  test("login response blocks token connection and launch uses POST", async () => {
    const fetcher = mock(async (_url: string, options?: RequestInit) => {
      expect(options?.method).toBe("POST");
      return Response.json({ schemaVersion: 1, authStatus: "login_required", terminalOpened: true });
    });
    expect(await discoverLocalSettings(settings, ID, fetcher, true)).toEqual({
      loginRequired: true, terminalOpened: true,
    });
  });

  test("rejects malformed or redirected connection data", async () => {
    for (const invalid of [
      { ...payload, schemaVersion: 2 }, { ...payload, token: null },
      { ...payload, proxyUrl: "ws://proxy.example.test:19315/ws" },
      { ...payload, proxyUrl: "ws://127.0.0.1:19316/ws" },
      { ...payload, proxyUrl: "ws://127.0.0.1:19315/other" },
    ]) {
      expect(await discoverLocalSettings(settings, ID, async () => Response.json(invalid))).toBeNull();
    }
  });
});