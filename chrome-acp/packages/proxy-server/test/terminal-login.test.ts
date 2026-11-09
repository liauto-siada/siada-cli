import { expect, mock, test } from "bun:test";
import { checkCliLogin, createTerminalLogin, terminalCommands } from "../src/terminal-login";
import { Hono } from "hono";
import { localBootstrapHandler } from "../src/local-bootstrap";

test("macOS quotes CLI paths without allowing shell substitution", () => {
  const commands = terminalCommands("/tmp/a ' $(touch unsafe)/siada-cli", "/tmp/work space", "darwin");
  expect(commands[0]?.command).toBe("osascript");
  expect(commands[0]?.args.join(" ")).toContain("'\\\\''");
});

test("Windows starts an encoded PowerShell command", () => {
  const command = terminalCommands("C:\\Program Files\\Siada\\siada-cli.exe", "C:\\Work", "win32")[0];
  expect(command?.command).toBe("powershell.exe");
  expect(command?.args.join(" ")).toContain("EncodedCommand");
});

test("concurrent login requests open one terminal with cooldown", async () => {
  const run = mock(async () => {});
  const open = createTerminalLogin("/tmp/siada-cli", "/tmp", run, "darwin");
  expect(await Promise.all([open(), open(), open()])).toEqual([true, true, true]);
  expect(run).toHaveBeenCalledTimes(1);
});

test("Linux tries next available terminal and reports total failure", async () => {
  const run = mock(async (command: string) => {
    if (command !== "konsole") throw new Error("unavailable");
  });
  expect(await createTerminalLogin("siada-cli", "/tmp", run, "linux")()).toBe(true);
  expect(run).toHaveBeenCalledTimes(3);
  expect(await createTerminalLogin("siada-cli", "/tmp", async () => { throw new Error("missing"); }, "linux")()).toBe(false);
});

test("generic ACP agents never trigger CLI terminal login", async () => {
  const run = mock(async () => {});
  expect(await createTerminalLogin("node", "/tmp", run)()).toBe(false);
  expect(run).not.toHaveBeenCalled();
});

test("login check skips generic agents and missing CLI without starting a UI", async () => {
  expect(await checkCliLogin("node")).toBe("unsupported");
  expect(await checkCliLogin("/nonexistent/siada-cli")).toBe("unknown");
});

test("only authorized POST opens login, status polling and denied requests do not", async () => {
  const id = "a".repeat(32);
  const open = mock(async () => true);
  const app = new Hono();
  const handler = localBootstrapHandler("synthetic", 19315, [id], { check: async () => "login_required", open });
  app.get("/local-bootstrap", handler);
  app.post("/local-bootstrap", handler);
  const env = { incoming: { socket: { remoteAddress: "127.0.0.1" } } };
  const headers = { "X-Siada-Extension-Id": id };
  const status = await app.request("http://127.0.0.1/local-bootstrap", { headers }, env);
  expect(await status.json()).toMatchObject({ authStatus: "login_required" });
  expect(open).not.toHaveBeenCalled();
  const denied = await app.request("http://127.0.0.1/local-bootstrap", { method: "POST" }, env);
  expect(denied.status).toBe(403);
  expect(open).not.toHaveBeenCalled();
  const response = await app.request("http://127.0.0.1/local-bootstrap", { method: "POST", headers }, env);
  const data = await response.json();
  expect(data).toMatchObject({ authStatus: "login_required", terminalOpened: true });
  expect(data.token).toBeUndefined();
  expect(open).toHaveBeenCalledTimes(1);
});