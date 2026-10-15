import pino from "pino";
import { join } from "node:path";
import { mkdirSync, existsSync, appendFileSync, statSync, renameSync, readdirSync, unlinkSync } from "node:fs";
import { Writable } from "node:stream";
import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

let logger: pino.Logger;
const context = new AsyncLocalStorage<Record<string, unknown>>();
const instanceId = randomUUID();

export function withLogContext<T>(fields: Record<string, unknown>, action: () => T): T {
  return context.run({ ...context.getStore(), ...fields }, action);
}

export class RotatingLogStream extends Writable {
  private size = 0;
  private lastCleanup = 0;
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
        const dir = join(this.file, "..");
        for (const name of readdirSync(dir)) {
          if (!/^acp-proxy-.+\.log(?:\.\d+)?$/.test(name)) continue;
          const target = join(dir, name);
          if (target === this.file) continue;
          try {
            if (Date.now() - statSync(target).mtimeMs > 7 * 86400000) unlinkSync(target);
          } catch { /* Concurrent cleanup may already have removed it. */ }
        }
      }
      callback();
    } catch (error) {
      callback(error as Error);
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

export function initLogger(config: LoggerConfig): pino.Logger {
  const { debug, logDir } = config;

  if (debug) {
    // Ensure log directory exists
    const dir = logDir || join(process.cwd(), ".acp-proxy");
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }

    // Format: acp-proxy-2026-01-24_22-30-45.log
    const now = new Date();
    const timestamp = now.toISOString()
      .replace(/T/, '_')
      .replace(/:/g, '-')
      .replace(/\..+/, '');
    const logFile = join(dir, `acp-proxy-${timestamp}-${process.pid}-${instanceId}.log`);
    const stream = new RotatingLogStream(logFile);
    stream.on("error", error => console.error("ACP proxy log write failed:", error.message));

    // Create logger with file transport for debug mode
    logger = pino(
      {
        ...loggerOptions,
        level: "debug",
      },
      stream
    );

    // Also log to console in debug mode
    console.log(`📝 Debug logging enabled: ${logFile}`);
  } else {
    // Normal mode: info level to stdout
    logger = pino({
      level: "info",
      ...loggerOptions,
      transport: {
        target: "pino/file",
        options: { destination: 1 }, // stdout
      },
    });
  }

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

