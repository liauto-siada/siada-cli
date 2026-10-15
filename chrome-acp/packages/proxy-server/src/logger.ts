import pino from "pino";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import { mkdirSync, existsSync, appendFileSync, statSync, renameSync, readdirSync, unlinkSync } from "node:fs";
import { Writable } from "node:stream";
import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

let logger: pino.Logger;
const context = new AsyncLocalStorage<Record<string, unknown>>();
const instanceId = randomUUID();
const writeDiagnostic = process.stderr.write.bind(process.stderr);

export function withLogContext<T>(fields: Record<string, unknown>, action: () => T): T {
  return context.run({ ...context.getStore(), ...fields }, action);
}

export class RotatingLogStream extends Writable {
  private size = 0;
  private lastCleanup = 0;
  private lastWarning = -Infinity;
  constructor(readonly file: string, readonly maxBytes = 10 * 1024 * 1024,
              readonly backupCount = 30) {
    super();
    this.size = existsSync(file) ? statSync(file).size : 0;
  }

  override _write(chunk: Buffer, _encoding: BufferEncoding, callback: (error?: Error | null) => void): void {
    try {
      if (this.size > 0 && this.size + chunk.length > this.maxBytes) {
        const oldest = `${this.file}.${this.backupCount}`;
        if (existsSync(oldest)) unlinkSync(oldest);
        for (let i = this.backupCount - 1; i >= 1; i--) {
          if (existsSync(`${this.file}.${i}`)) renameSync(`${this.file}.${i}`, `${this.file}.${i + 1}`);
        }
        renameSync(this.file, `${this.file}.1`);
        this.size = 0;
      }
      appendFileSync(this.file, chunk);
      this.size += chunk.length;
      if (Date.now() - this.lastCleanup > 3600000) {
        this.lastCleanup = Date.now();
        const dir = dirname(this.file);
        for (const name of readdirSync(dir)) {
          if (!/^acp-proxy-.+\.log(?:\.\d+)?$/.test(name) || name.startsWith("acp-proxy-launch")) continue;
          const target = join(dir, name);
          if (target === this.file) continue;
          try {
            const active = /-(\d+)-[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\.log$/.exec(name);
            if (active) {
              try { process.kill(Number(active[1]), 0); continue; }
              catch (error) { if ((error as NodeJS.ErrnoException).code !== "ESRCH") continue; }
            }
            if (Date.now() - statSync(target).mtimeMs > 7 * 86400000) unlinkSync(target);
          } catch { /* Concurrent cleanup may already have removed it. */ }
        }
      }
      callback();
    } catch (error) {
      if (Date.now() - this.lastWarning >= 60_000) {
        this.lastWarning = Date.now();
        writeDiagnostic(`ACP proxy log write failed [pid=${process.pid} file=${this.file}]: ${(error as Error).message}\n`);
      }
      // Keep the stream usable so the next record can retry after an I/O failure.
      callback();
    }
  }
}

const loggerOptions = {
  timestamp: pino.stdTimeFunctions.isoTime,
  mixin: () => ({
    instanceId, sessionId: "-", requestId: "-", agent: "-", agentRunId: "-",
    ...context.getStore(),
  }),
};

export interface LoggerConfig {
  debug: boolean;
  logDir?: string;
}

export function proxyLogDirectory(explicitDir?: string): string {
  return explicitDir || process.env.SIADA_PROXY_LOG_DIR ||
    join(process.env.SIADA_CLI_LOG_DIR || join(homedir(), ".siada-cli", "logs"), "proxy");
}

export function captureManagedOutput(target: pino.Logger): () => void {
  const stdoutWrite = process.stdout.write;
  const stderrWrite = process.stderr.write;
  const output = (source: "stdout" | "stderr") => new Writable({
    write(chunk, _encoding, callback) {
      target[source === "stderr" ? "warn" : "info"]({
        source, output: chunk.toString().slice(0, 8192),
      }, `Proxy ${source}`);
      callback();
    },
  });
  const stdout = output("stdout");
  const stderr = output("stderr");
  process.stdout.write = stdout.write.bind(stdout) as typeof process.stdout.write;
  process.stderr.write = stderr.write.bind(stderr) as typeof process.stderr.write;
  return () => {
    process.stdout.write = stdoutWrite;
    process.stderr.write = stderrWrite;
    stdout.end();
    stderr.end();
  };
}

export function initLogger(config: LoggerConfig): pino.Logger {
  const { debug, logDir } = config;
  const dir = proxyLogDirectory(logDir);
  mkdirSync(dir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/T/, "_").replace(/:/g, "-").replace(/\..+/, "");
  const logFile = join(dir, `acp-proxy-${timestamp}-${process.pid}-${randomUUID()}.log`);
  logger = pino({ ...loggerOptions, level: debug ? "debug" : "info" }, new RotatingLogStream(logFile));
  return logger;
}

export function getLogger(): pino.Logger {
  if (!logger) {
    // Default logger if not initialized
    logger = pino({ ...loggerOptions, level: "info" });
  }
  return logger;
}

export const log = {
  trace: (msg: string, obj?: object) => getLogger().trace(obj, msg),
  debug: (msg: string, obj?: object) => getLogger().debug(obj, msg),
  info: (msg: string, obj?: object) => getLogger().info(obj, msg),
  warn: (msg: string, obj?: object) => getLogger().warn(obj, msg),
  error: (msg: string, obj?: object) => getLogger().error(obj, msg),
  fatal: (msg: string, obj?: object) => getLogger().fatal(obj, msg),
};

