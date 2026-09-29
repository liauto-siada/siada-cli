import { describe, expect, test, beforeAll } from "bun:test";
import { get as httpGet } from "node:http";
import { get as httpsGet } from "node:https";
import { createServer as createNetServer } from "node:net";
import { join } from "node:path";
import { getLanIPs } from "../src/cert.ts";
import { startServer } from "../src/server.ts";

// With --https the proxy must serve BOTH protocols on one port: TLS
// (wss/https) for remote peers and plaintext (ws/http) for loopback
// clients, so local users never have to trust the self-signed certificate.
// These tests start the real server in-process and exercise both legs.

const fakeAgentPath = join(import.meta.dir, "fixtures", "fake-agent.mjs");
const TOKEN = "dual-protocol-test-token";

// Pick a free TCP port: 9315 is often occupied by a locally running proxy.
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createNetServer();
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address() as { port: number };
      probe.close(() => resolve(port));
    });
    probe.on("error", reject);
  });
}

function fetchStatus(
  url: string,
  options: { rejectUnauthorized?: boolean } = {},
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const get = url.startsWith("https") ? httpsGet : httpGet;
    const req = get(url, options, (res) => {
      let body = "";
      res.on("data", (chunk: Buffer) => (body += chunk.toString()));
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on("error", reject);
    req.setTimeout(4000, () => req.destroy(new Error("request timed out")));
  });
}

// Open a WebSocket, run the "connect" handshake against the fake agent and
// resolve with the first status payload the proxy sends back.
function wsConnect(url: string): Promise<{ connected?: unknown }> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timeout = setTimeout(() => reject(new Error(`ws connect timed out (${url})`)), 8000);
    ws.addEventListener("open", () => {
      ws.send(JSON.stringify({ type: "connect" }));
    });
    ws.addEventListener("message", (event: MessageEvent) => {
      const msg = JSON.parse(String(event.data));
      if (msg.type === "status") {
        clearTimeout(timeout);
        ws.close();
        resolve(msg.payload);
      }
    });
    ws.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error(`ws error (${url})`));
    });
  });
}

let port = 0;

beforeAll(async () => {
  port = await freePort();
  // Never awaited: startServer keeps running (heartbeat, open listener) for
  // the lifetime of the test process.
  void startServer({
    port,
    host: "0.0.0.0",
    command: process.execPath,
    args: [fakeAgentPath],
    cwd: import.meta.dir,
    token: TOKEN,
    https: true,
  });
  const deadline = Date.now() + 10_000;
  for (;;) {
    try {
      await fetchStatus(`https://127.0.0.1:${port}/health`, { rejectUnauthorized: false });
      break;
    } catch {
      if (Date.now() > deadline) throw new Error("proxy did not become healthy");
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  // The TLS certificate is self-signed; let the wss test below connect.
  // Plain ws/http checks above are unaffected by this setting.
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
}, 30_000);

describe("--https dual-protocol port", () => {
  test("loopback plaintext HTTP is served on the TLS port", async () => {
    const { status, body } = await fetchStatus(`http://127.0.0.1:${port}/health`);
    expect(status).toBe(200);
    expect(JSON.parse(body)).toEqual({ status: "ok" });
  });

  test("TLS HTTPS is served on the same port", async () => {
    const { status, body } = await fetchStatus(`https://127.0.0.1:${port}/health`, {
      rejectUnauthorized: false,
    });
    expect(status).toBe(200);
    expect(JSON.parse(body)).toEqual({ status: "ok" });
  });

  test("loopback ws:// (plaintext) upgrades and completes the agent handshake", async () => {
    const payload = await wsConnect(`ws://127.0.0.1:${port}/ws?token=${TOKEN}`);
    expect(payload.connected).toBe(true);
  });

  test("wss:// (TLS) upgrades and completes the agent handshake", async () => {
    const payload = await wsConnect(`wss://127.0.0.1:${port}/ws?token=${TOKEN}`);
    expect(payload.connected).toBe(true);
  });

  test("plaintext from a non-loopback peer is refused", async () => {
    const lanIp = getLanIPs()[0];
    if (!lanIp) {
      // No routable IPv4 on this machine (bare CI sandbox) — nothing to
      // assert; the loopback tests above already cover the plaintext path.
      return;
    }
    // Reaching the server via its LAN IP makes the peer address non-loopback
    // even from the same machine: the sniffer must destroy the connection.
    await expect(fetchStatus(`http://${lanIp}:${port}/health`)).rejects.toThrow();
  });
});
