import { expect, test } from "bun:test";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { join } from "node:path";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";

class Inbox {
  messages: any[] = [];
  private waiters = new Set<() => void>();
  constructor(public ws: WebSocket) {
    ws.addEventListener("message", event => {
      this.messages.push(JSON.parse(String(event.data)));
      for (const waiter of this.waiters) waiter();
    });
  }
  send(message: unknown) { this.ws.send(JSON.stringify(message)); }
  next(type: string): Promise<any> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.waiters.delete(check); reject(new Error(`Missing ${type}`)); }, 7000);
      const check = () => {
        const index = this.messages.findIndex(message => message.type === type);
        if (index < 0) return;
        clearTimeout(timer);
        this.waiters.delete(check);
        resolve(this.messages.splice(index, 1)[0]);
      };
      this.waiters.add(check);
      check();
    });
  }
  close(): Promise<void> {
    return new Promise(resolve => {
      this.ws.addEventListener("close", () => resolve(), { once: true });
      this.ws.close();
    });
  }
}

async function runProxy(slow = false) {
  const port = await new Promise<number>(resolve => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as { port: number }).port;
      server.close(() => resolve(port));
    });
  });
  const directory = await mkdtemp(join(tmpdir(), "siada-retention-test-"));
  const launchLog = join(directory, "launches.txt");
  let output = "";
  const proc = spawn("node", [
    join(import.meta.dir, "../dist/cli/bin.js"),
    "--host", "127.0.0.1", "--port", String(port),
    "node", "--", join(import.meta.dir, "fixtures/fake-agent.mjs"),
    "--retention", ...(slow ? ["--slow-init"] : []),
  ], {
    env: {
      ...process.env, ACP_AUTH_TOKEN: "synthetic-retention", SIADA_PROXY_MANAGED: "1",
      SIADA_PROXY_LOG_DIR: directory, SIADA_RETENTION_TEST_LAUNCH_LOG: launchLog,
    },
    cwd: directory, stdio: ["ignore", "pipe", "pipe"],
  });
  proc.stdout.on("data", chunk => { output += chunk; });
  proc.stderr.on("data", chunk => { output += chunk; });
  const url = `http://127.0.0.1:${port}`;
  const status = async () => (await fetch(`${url}/status`)).json() as Promise<{ retainedAgentSessions: number; agentSessions: number }>;
  const until = async (predicate: () => Promise<boolean>) => {
    const deadline = Date.now() + 5000;
    while (!await predicate()) {
      if (Date.now() >= deadline) throw new Error(`Proxy timeout: ${output.slice(-2000)}`);
      await new Promise(resolve => setTimeout(resolve, 20));
    }
  };
  await until(async () => { try { return (await fetch(`${url}/health`)).ok; } catch { return false; } });
  return {
    url,
    status, until, output: () => output,
    starts: async () => {
      try { return (await readFile(launchLog, "utf8")).trim().split("\n"); } catch { return []; }
    },
    open: async (id?: string) => {
      const ws = new WebSocket(`ws://127.0.0.1:${port}/ws?token=synthetic-retention`);
      const inbox = new Inbox(ws);
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error("WebSocket open failed"));
      });
      inbox.send({ type: "connect", ...(id ? { payload: { retentionId: id } } : {}) });
      return inbox;
    },
    stop: async () => {
      const exited = new Promise<void>(resolve => proc.once("exit", () => resolve()));
      proc.kill("SIGTERM");
      await exited;
      await rm(directory, { recursive: true, force: true });
    },
  };
}

const ID = "11111111-1111-4111-8111-111111111111";
test("reopen reuses the agent, restores history through the new socket, and explicit disconnect releases it", async () => {
  const proxy = await runProxy();
  try {
    const first = await proxy.open(ID);
    const initial = await first.next("status");
    first.send({ type: "new_session" });
    const created = await first.next("session_created");
    await first.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
    const second = await proxy.open(ID);
    const attached = await second.next("status");
    expect(attached.payload.agentInfo).toEqual(initial.payload.agentInfo);
    expect(attached.payload.retainedSessionId).toBe(created.payload.sessionId);
    second.send({ type: "load_session", payload: { sessionId: created.payload.sessionId } });
    expect((await second.next("session_update")).payload.update.content.text).toContain("retained history");
    expect((await second.next("session_loaded")).payload.sessionId).toBe(created.payload.sessionId);
    second.send({ type: "prompt", payload: { content: [{ type: "text", text: "retention-echo" }], requestId: "echo-1" } });
    expect((await second.next("session_update")).payload.update.content.text).toBe("retention test update");
    expect((await second.next("prompt_complete")).payload.stopReason).toBe("end_turn");

    const duplicate = await proxy.open(ID);
    expect((await duplicate.next("error")).payload.message).toContain("already attached");
    await duplicate.close();
    second.send({ type: "disconnect" });
    expect((await second.next("status")).payload.connected).toBe(false);
    await second.close();
    expect((await proxy.status()).retainedAgentSessions).toBe(0);
    const fresh = await proxy.open(ID);
    expect((await fresh.next("status")).payload.agentInfo).not.toEqual(initial.payload.agentInfo);
    await fresh.close();
  } finally { await proxy.stop(); }
}, 20_000);

test("different identities do not share agents and legacy clients release immediately", async () => {
  const proxy = await runProxy();
  try {
    const first = await proxy.open(ID);
    const initial = await first.next("status");
    await first.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
    const unauthorized = new WebSocket(`${proxy.url.replace("http:", "ws:")}/ws?token=incorrect`);
    const code = await new Promise<number>(resolve => {
      unauthorized.onclose = event => resolve(event.code);
    });
    expect(code).toBe(4001);
    expect((await proxy.status()).retainedAgentSessions).toBe(1);
    const other = await proxy.open("22222222-2222-4222-8222-222222222222");
    expect((await other.next("status")).payload.agentInfo).not.toEqual(initial.payload.agentInfo);
    other.send({ type: "disconnect" });
    await other.next("status");
    await other.close();
    const legacy = await proxy.open();
    await legacy.next("status");
    await legacy.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
  } finally { await proxy.stop(); }
}, 20_000);

test("pending permissions are cancelled on close and cannot keep a retained session stuck", async () => {
  const proxy = await runProxy();
  try {
    const first = await proxy.open(ID);
    const initialized = await first.next("status");
    first.send({ type: "new_session" });
    await first.next("session_created");
    first.send({ type: "prompt", payload: { content: [{ type: "text", text: "retention-permission" }] } });
    await first.next("permission_request");
    await first.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
    const second = await proxy.open(ID);
    expect((await second.next("status")).payload.agentInfo).toEqual(initialized.payload.agentInfo);
    expect(second.messages.some(message => message.type === "permission_request")).toBe(false);
    await second.close();
  } finally { await proxy.stop(); }
}, 20_000);

test("close during initialization reattaches to the same in-flight startup", async () => {
  const proxy = await runProxy(true);
  try {
    const first = await proxy.open(ID);
    await proxy.until(async () => (await proxy.starts()).length === 1);
    expect(first.messages.some(message => message.type === "status")).toBe(false);
    await first.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
    const second = await proxy.open(ID);
    expect((await second.next("status")).payload.connected).toBe(true);
    expect((await proxy.starts()).length).toBe(1);
    await second.close();
  } finally { await proxy.stop(); }
}, 20_000);

test("closing an active prompt finishes cancellation before the retained session is reattached", async () => {
  const proxy = await runProxy();
  try {
    const first = await proxy.open(ID);
    const initialized = await first.next("status");
    first.send({ type: "new_session" });
    await first.next("session_created");
    first.send({ type: "prompt", payload: { content: [{ type: "text", text: "retention-hold" }] } });
    await first.next("session_update");
    await first.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
    const second = await proxy.open(ID);
    expect((await second.next("status")).payload.agentInfo).toEqual(initialized.payload.agentInfo);
    second.send({ type: "prompt", payload: { content: [{ type: "text", text: "retention-echo" }] } });
    expect((await second.next("prompt_complete")).payload.stopReason).toBe("end_turn");
    await second.close();
  } finally { await proxy.stop(); }
}, 20_000);

test("an agent that ignores cancellation is replaced instead of hanging reopen", async () => {
  const proxy = await runProxy();
  try {
    const first = await proxy.open(ID);
    const initialized = await first.next("status");
    first.send({ type: "new_session" });
    await first.next("session_created");
    first.send({ type: "prompt", payload: { content: [{ type: "text", text: "retention-ignore-cancel" }] } });
    await first.next("session_update");
    await first.close();
    await proxy.until(async () => (await proxy.status()).retainedAgentSessions === 1);
    const second = await proxy.open(ID);
    expect((await second.next("status")).payload.agentInfo).not.toEqual(initialized.payload.agentInfo);
    expect(second.messages.some(message => message.type === "prompt_complete")).toBe(false);
    await second.close();
  } finally { await proxy.stop(); }
}, 20_000);