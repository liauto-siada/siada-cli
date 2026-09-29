import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import * as acp from "@agentclientprotocol/sdk";
import { launchAgent, shouldShellWrap } from "../src/agent-connection.ts";

const fakeAgentPath = join(import.meta.dir, "fixtures", "fake-agent.mjs");

function noClient(): acp.Client {
  // The fake agents in these tests never emit client-facing events; the
  // handlers below are never called.
  return {
    async requestPermission() {
      return { outcome: { outcome: "cancelled" } };
    },
    async sessionUpdate() {},
    async readTextFile() {
      return { content: "" };
    },
    async writeTextFile() {
      return {};
    },
  } as unknown as acp.Client;
}

// Guard against a hung handshake turning the suite into a timeout.
function withTimeout<T>(promise: Promise<T>, ms = 5000): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("timed out")), ms),
    ),
  ]);
}

describe("launchAgent", () => {
  test("nonexistent agent command rejects with the spawn failure", async () => {
    await expect(
      withTimeout(
        launchAgent({
          command: "chrome-acp-no-such-command",
          args: [],
          clientFactory: noClient,
        }),
      ),
    ).rejects.toThrow("chrome-acp-no-such-command");
  });

  test("agent crashing during initialization rejects with exit code and stderr", async () => {
    const error = await withTimeout(
      launchAgent({
        command: process.execPath,
        args: ["-e", "console.error('boom: agent crashed on startup'); process.exit(3)"],
        clientFactory: noClient,
      }),
    ).then(
      () => {
        throw new Error("expected launchAgent to reject");
      },
      (e: Error) => e,
    );

    expect(error.message).toContain("exit code 3");
    expect(error.message).toContain("boom: agent crashed on startup");
  });

  test("successful handshake resolves with agent info and reports spawned objects", async () => {
    let spawned = false;
    const launched = await withTimeout(
      launchAgent({
        command: process.execPath,
        args: [fakeAgentPath],
        clientFactory: noClient,
        onSpawned: () => {
          spawned = true;
        },
      }),
    );

    expect(spawned).toBe(true);
    expect(launched.initResult.agentInfo?.name).toBe("fake-agent");
    launched.process.kill();
  });
});

describe("shouldShellWrap", () => {
  test("only wraps .cmd/.bat launchers on Windows", () => {
    // The Windows installer's launcher that hit "spawn EINVAL" (CVE-2024-27980
    // hardening rejects shell-less .cmd/.bat spawns on patched Node).
    expect(shouldShellWrap("C:\\Users\\u\\.local\\bin\\siada-cli.CMD", "win32")).toBe(true);
    expect(shouldShellWrap("C:\\tools\\agent.bat", "win32")).toBe(true);
    expect(shouldShellWrap("C:\\venv\\Scripts\\python.exe", "win32")).toBe(false);
    expect(shouldShellWrap("/usr/local/bin/siada-cli", "darwin")).toBe(false);
    expect(shouldShellWrap("C:\\x\\siada-cli.CMD", "darwin")).toBe(false);
  });
});
