import { describe, expect, test } from "bun:test";
import { Hono } from "hono";
import { allowLocalBootstrap, localBootstrapHandler } from "../src/local-bootstrap";

const ID = "a".repeat(32);
const valid = {
  url: "http://127.0.0.1:19315/local-bootstrap",
  origin: `chrome-extension://${ID}`,
  extensionId: ID,
  peer: "127.0.0.1",
};

describe("local token discovery boundary", () => {
  test("allows registered extension from loopback", () => {
    expect(allowLocalBootstrap(valid, [ID])).toBe(true);
    expect(allowLocalBootstrap({ ...valid, origin: undefined }, [ID])).toBe(true);
    expect(allowLocalBootstrap({ ...valid, peer: "::ffff:127.0.0.1" }, [ID])).toBe(true);
  });

  test("rejects remote peers, TLS forwarding and spoofed origins", () => {
    for (const override of [
      { peer: "192.0.2.1" }, { peer: undefined }, { encrypted: true },
      { origin: "https://example.test" }, { origin: "null" },
      { origin: `chrome-extension://${"b".repeat(32)}` },
      { extensionId: "b".repeat(32) }, { extensionId: undefined },
      { url: "http://localhost.example.test/local-bootstrap" },
      { url: "https://127.0.0.1/local-bootstrap" },
      { url: "http://192.0.2.1/local-bootstrap" },
    ]) {
      expect(allowLocalBootstrap({ ...valid, ...override }, [ID])).toBe(false);
    }
    expect(allowLocalBootstrap(valid, [])).toBe(false);
  });

  test("endpoint is not cached and never permits website preflight", async () => {
    const app = new Hono();
    app.get("/local-bootstrap", localBootstrapHandler("synthetic", 19315, [ID]));
    const bindings = { incoming: { socket: { remoteAddress: "127.0.0.1" } } };
    const response = await app.request(valid.url, {
      headers: { Origin: valid.origin, "X-Siada-Extension-Id": ID },
    }, bindings);
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toEqual({
      schemaVersion: 1, proxyUrl: "ws://127.0.0.1:19315/ws", token: "synthetic",
    });
    const forbidden = await app.request(valid.url, {
      headers: { Origin: "https://example.test", "X-Siada-Extension-Id": ID },
    }, bindings);
    expect(forbidden.status).toBe(403);
    expect(await forbidden.text()).not.toContain("synthetic");
    const preflight = await app.request(valid.url, {
      method: "OPTIONS",
      headers: { Origin: "https://example.test", "Access-Control-Request-Headers": "X-Siada-Extension-Id" },
    }, bindings);
    expect(preflight.headers.get("Access-Control-Allow-Origin")).toBeNull();
  });
});