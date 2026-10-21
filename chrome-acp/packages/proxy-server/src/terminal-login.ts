import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import { basename, dirname, join } from "node:path";
import { realpath } from "node:fs/promises";

const execute = promisify(execFile);

async function runTerminal(command: string, args: string[], options: { cwd: string; timeout: number }): Promise<unknown> {
  if (command === "osascript" || command === "powershell.exe") {
    return execute(command, args, options);
  }
  // Terminal emulators may stay alive until the interactive CLI exits.
  // Wait for successful spawning, not termination; never timeout-kill them.
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, { cwd: options.cwd, detached: true, stdio: "ignore" });
    child.once("error", reject);
    child.once("spawn", () => { child.unref(); resolve(); });
  });
}

export async function checkCliLogin(command: string): Promise<string> {
  if (!/^siada-cli(?:\.exe)?$/i.test(basename(command))) return "unsupported";
  try {
    // Installed console scripts share a directory with their interpreter.
    // Older launchers accept unknown flags and can start an interactive UI.
    const resolved = await realpath(command);
    const python = join(dirname(resolved), process.platform === "win32" ? "python.exe" : "python");
    const { stdout: capability } = await execute(python, ["-c",
      "import importlib.util,pathlib; s=importlib.util.find_spec('siada.entrypoint.launch_ui_with_acp'); print(bool(s and s.origin and '--browser-check' in pathlib.Path(s.origin).read_text()))",
    ], { timeout: 2000, maxBuffer: 1024 });
    if (capability.trim() !== "True") return "unsupported";
    const { stdout } = await execute(command, ["--browser-check"], {
      timeout: 8000, maxBuffer: 64 * 1024,
    });
    const data = JSON.parse(stdout);
    const status = data?.auth?.status;
    return data?.schemaVersion === 1 && ["ready", "login_required", "unknown"].includes(status)
      ? status : "unknown";
  } catch {
    return "unknown";
  }
}

const shellQuote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'";

export function terminalCommands(command: string, cwd: string, platform: string): Array<{ command: string; args: string[] }> {
  if (platform === "darwin") {
    const script = `cd ${shellQuote(cwd)} && ${shellQuote(command)}`;
    return [{
      command: "osascript",
      args: ["-e", 'tell application "Terminal" to activate', "-e",
        `tell application "Terminal" to do script ${JSON.stringify(script)}`],
    }];
  }
  if (platform === "win32") {
    const psQuote = (value: string) => "'" + value.replaceAll("'", "''") + "'";
    const script = `Set-Location -LiteralPath ${psQuote(cwd)}; & ${psQuote(command)}`;
    const encoded = Buffer.from(script, "utf16le").toString("base64");
    return [{
      command: "powershell.exe",
      args: ["-NoProfile", "-Command",
        `Start-Process powershell.exe -ArgumentList '-NoExit','-NoProfile','-EncodedCommand','${encoded}'`],
    }];
  }
  return [
    { command: "x-terminal-emulator", args: ["-e", command] },
    { command: "gnome-terminal", args: ["--", command] },
    { command: "konsole", args: ["-e", command] },
    { command: "xterm", args: ["-e", command] },
  ];
}

export function createTerminalLogin(
  command: string, cwd: string,
  run: (command: string, args: string[], options: { cwd: string; timeout: number }) => Promise<unknown> = runTerminal,
  platform = process.platform,
) {
  let pending: Promise<boolean> | undefined;
  let lastOpened = 0;
  return async () => {
    if (!/^siada-cli(?:\.exe)?$/i.test(basename(command))) return false;
    if (pending) return pending;
    if (Date.now() - lastOpened < 60_000) return true;
    pending = (async () => {
      for (const terminal of terminalCommands(command, cwd, platform)) {
        try {
          await run(terminal.command, terminal.args, { cwd, timeout: 5000 });
          lastOpened = Date.now();
          return true;
        } catch {}
      }
      return false;
    })();
    try { return await pending; } finally { pending = undefined; }
  };
}