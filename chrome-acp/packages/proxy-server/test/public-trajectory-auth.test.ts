import {beforeAll, describe, expect, test} from "bun:test";
import {createServer} from "node:net";
import {startServer} from "../src/server";

let port = 0;
const token = "synthetic-trajectory-token";

beforeAll(async () => {
  port = await new Promise<number>(resolve => {
    const probe = createServer();
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address() as {port: number};
      probe.close(() => resolve(address.port));
    });
  });
  void startServer({
    port, host: "127.0.0.1", command: process.execPath,
    args: [], cwd: import.meta.dir, token, https: false,
  });
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/health`)).ok) return;
    } catch {}
    await Bun.sleep(20);
  }
  throw new Error("Proxy did not become healthy");
});

describe("public trajectory authentication", () => {
  test.each(["", "?token=wrong"])("rejects a producer with %s", async query => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws/trajectory${query}`);
    const closed = await new Promise<number>((resolve, reject) => {
      const timeout = setTimeout(() => { ws.close(); reject(new Error("Unauthorized producer stayed connected")); }, 2000);
      ws.addEventListener("close", event => { clearTimeout(timeout); resolve(event.code); });
      ws.addEventListener("error", () => {});
    });
    expect([4001, 1006]).toContain(closed);
  });

  test("accepts an authorized producer without writing any events", async () => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws/trajectory?token=${token}`);
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => { ws.close(); reject(new Error("Connection timed out")); }, 2000);
      ws.addEventListener("open", () => { clearTimeout(timeout); resolve(); });
      ws.addEventListener("error", () => { clearTimeout(timeout); reject(new Error("Connection failed")); });
    });
    expect(ws.readyState).toBe(WebSocket.OPEN);
    ws.close();
  });
});