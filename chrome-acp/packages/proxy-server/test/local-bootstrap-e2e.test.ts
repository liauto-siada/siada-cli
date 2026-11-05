import { expect, test } from "bun:test";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { join } from "node:path";
import { discoverLocalSettings } from "../../chrome-extension/src/local-bootstrap";
import { DEFAULT_SETTINGS } from "../../shared/src/acp/types";

test("running proxy supplies token and authenticates ACP connection", async () => {
  const port = await new Promise<number>((resolve) => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as { port: number }).port;
      server.close(() => resolve(port));
    });
  });
  const extensionId = "a".repeat(32);
  const proc = spawn("node", [
    join(import.meta.dir, "../dist/cli/bin.js"),
    "--host", "127.0.0.1", "--port", String(port),
    "node", "--", join(import.meta.dir, "fixtures/fake-agent.mjs"),
  ], {
    env: { ...process.env, ACP_AUTH_TOKEN: "synthetic-e2e", SIADA_BROWSER_EXTENSION_IDS: extensionId, SIADA_PROXY_MANAGED: "1" },
    stdio: "ignore",
  });
  try {
    const url = `http://127.0.0.1:${port}`;
    const deadline = Date.now() + 10_000;
    while (true) {
      try {
        if ((await fetch(`${url}/health`)).ok) break;
      } catch {}
      if (Date.now() > deadline) throw new Error("proxy did not start");
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    expect((await fetch(`${url}/local-bootstrap`)).status).toBe(403);
    expect((await fetch(`${url}/local-bootstrap`, {
      headers: { Origin: "https://example.test", "X-Siada-Extension-Id": extensionId },
    })).status).toBe(403);
    const discovered = await discoverLocalSettings({
      ...DEFAULT_SETTINGS, proxyUrl: `ws://127.0.0.1:${port}/ws`, token: "",
    }, extensionId);
    expect(discovered && "token" in discovered ? discovered.token : null).toBe("synthetic-e2e");
    expect(discovered).not.toBeNull();
    if (!discovered || !("token" in discovered)) throw new Error("unexpected login state");
    await new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(`${discovered.proxyUrl}?token=${encodeURIComponent(discovered.token)}`);
      const timer = setTimeout(() => { ws.close(); reject(new Error("handshake timeout")); }, 5000);
      ws.onopen = () => ws.send(JSON.stringify({ type: "connect" }));
      ws.onmessage = (event) => {
        const message = JSON.parse(String(event.data));
        if (message.type === "status" && message.payload.connected) {
          clearTimeout(timer);
          ws.close();
          resolve();
        }
      };
      ws.onerror = () => { clearTimeout(timer); ws.close(); reject(new Error("websocket error")); };
    });
  } finally {
    proc.kill("SIGTERM");
  }
}, 20_000);