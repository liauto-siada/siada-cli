import { spawn, type ChildProcess } from "node:child_process";
import { Writable, Readable } from "node:stream";
import * as acp from "@agentclientprotocol/sdk";
import { log } from "./logger.js";

// Rolling stderr tail kept for error reporting: when the agent fails to
// start, its stderr (Python traceback, missing dependency, config error) is
// the only place the actual reason lives, and it must be forwarded to the
// WebSocket client so the sidepanel can display it.
const STDERR_TAIL_MAX_LINES = 20;

export interface LaunchAgentOptions {
  command: string;
  args: string[];
  cwd?: string;
  // Builds the acp.Client that receives agent events (permissions, session
  // updates); passed straight to ClientSideConnection by the caller.
  clientFactory: (agent: acp.Agent) => acp.Client;
  // Called synchronously right after the process and connection objects are
  // created (before initialize resolves), so the caller can store them for
  // cleanup if the client disconnects while initialization is in flight.
  onSpawned?: (process: ChildProcess, connection: acp.ClientSideConnection) => void;
}

export interface LaunchedAgent {
  process: ChildProcess;
  connection: acp.ClientSideConnection;
  initResult: Awaited<ReturnType<acp.ClientSideConnection["initialize"]>>;
}

// Tee the agent's stderr to this server's stderr and append complete lines to
// `tail`. Returns a flush function for the trailing partial line.
function pipeStderr(child: ChildProcess, tail: string[]): () => void {
  let buffer = "";

  const pushLine = (line: string) => {
    if (!line.trim()) return;
    console.error(`[Agent stderr] ${line}`);
    tail.push(line);
    if (tail.length > STDERR_TAIL_MAX_LINES) tail.shift();
  };

  child.stderr?.on("data", (chunk: Buffer) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) pushLine(line);
  });

  return () => {
    if (buffer) {
      pushLine(buffer);
      buffer = "";
    }
  };
}

// Windows .cmd/.bat launchers (e.g. the installer's siada-cli.cmd shim) cannot
// be spawned directly: Node >= 18.20.2/20.12.2 throws EINVAL for them without
// a shell (CVE-2024-27980 hardening). Route them through cmd.exe instead.
export function shouldShellWrap(command: string, platform: string = process.platform): boolean {
  return platform === "win32" && /\.(cmd|bat)$/i.test(command);
}

// Tracks children launched through cmd.exe so killAgentProcess knows to take
// down the whole process tree instead of only the shell.
const shellSpawned = new WeakSet<ChildProcess>();

export function spawnAgentProcess(command: string, args: string[], cwd?: string): ChildProcess {
  if (shouldShellWrap(command)) {
    // `/s` makes cmd.exe strip the outer quotes so the quoted command still
    // resolves when its path contains spaces. Args come from the local manager
    // config (typically just "--acp"), not from user input.
    const commandLine = [
      `"${command}"`,
      ...args.map((arg) => (/\s/.test(arg) ? `"${arg}"` : arg)),
    ].join(" ");
    const child = spawn(commandLine, {
      cwd,
      shell: true,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    shellSpawned.add(child);
    return child;
  }
  return spawn(command, args, { cwd, stdio: ["pipe", "pipe", "pipe"] });
}

// Kill the agent process. For shell-wrapped launches the direct child is only
// cmd.exe; a plain kill() would orphan the actual agent running beneath it,
// so taskkill /T takes down the whole tree instead.
export function killAgentProcess(child: ChildProcess | null): void {
  if (!child || child.pid === undefined) return;
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (shellSpawned.has(child)) {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  child.kill();
}

/**
 * Spawn the ACP agent subprocess and run the initialize handshake.
 *
 * Startup failures are reported by REJECTING the returned promise with a
 * message that includes the failure reason and the agent's stderr tail. This
 * matters because the ACP SDK never settles a pending initialize() when the
 * process dies: pending JSON-RPC responses only resolve on a reply, and
 * stream write errors are swallowed — without the race below, a failed spawn
 * would leave the caller (and the extension sidepanel) stuck on
 * "Connecting..." forever with no error.
 */
export async function launchAgent(options: LaunchAgentOptions): Promise<LaunchedAgent> {
  const { command, args, cwd, clientFactory, onSpawned } = options;

  log.info("Spawning agent", { command, args });

  const child = spawnAgentProcess(command, args, cwd);

  const stderrTail: string[] = [];
  const flushStderr = pipeStderr(child, stderrTail);

  const input = Writable.toWeb(child.stdin!) as unknown as WritableStream<Uint8Array>;
  const output = Readable.toWeb(child.stdout!) as unknown as ReadableStream<Uint8Array>;
  const stream = acp.ndJsonStream(input, output);
  const connection = new acp.ClientSideConnection(clientFactory, stream);

  onSpawned?.(child, connection);

  // Rejects as soon as the process dies, whatever the reason. Once the race
  // below is settled this promise is a no-op, so a later (normal) agent exit
  // never surfaces as a startup failure.
  const death = new Promise<never>((_resolve, reject) => {
    child.on("error", (error) => {
      reject(new Error(`failed to start "${command}": ${error.message}`));
    });
    // 'close' (not 'exit'): fires after the stdio pipes have drained, so the
    // stderr tail is complete when the failure reason is assembled below.
    child.on("close", (code, signal) => {
      flushStderr();
      const detail = signal ? `signal ${signal}` : `exit code ${code ?? "unknown"}`;
      reject(new Error(`agent "${command}" exited before initialization completed (${detail})`));
    });
  });

  let initResult: LaunchedAgent["initResult"];
  try {
    initResult = await Promise.race([
      connection.initialize({
        protocolVersion: acp.PROTOCOL_VERSION,
        clientInfo: {
          name: "zed",
          version: "1.0.0",
        },
        clientCapabilities: {
          fs: {
            readTextFile: true,
            writeTextFile: true,
          },
        },
      }),
      death,
    ]);
  } catch (error) {
    const reason = (error as Error).message;
    const tail = stderrTail.join("\n").trim();
    log.error("Agent startup failed", { reason, stderr: tail });
    throw new Error(tail ? `${reason}\n${tail}` : reason);
  }

  return { process: child, connection, initResult };
}
