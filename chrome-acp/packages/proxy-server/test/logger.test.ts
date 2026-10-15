import { describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync, utimesSync, mkdirSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";
import { RotatingLogStream, initLogger, withLogContext, proxyLogDirectory, captureManagedOutput } from "../src/logger.ts";

describe("proxy logging", () => {
  test("default and custom roots are independent of the proxy workspace", () => {
    const before = { cli: process.env.SIADA_CLI_LOG_DIR, proxy: process.env.SIADA_PROXY_LOG_DIR };
    try {
      delete process.env.SIADA_CLI_LOG_DIR;
      delete process.env.SIADA_PROXY_LOG_DIR;
      expect(proxyLogDirectory()).toBe(join(homedir(), ".siada-cli", "logs", "proxy"));
      process.env.SIADA_CLI_LOG_DIR = "/synthetic/logs";
      expect(proxyLogDirectory()).toBe(join("/synthetic/logs", "proxy"));
      process.env.SIADA_PROXY_LOG_DIR = "/synthetic/proxy";
      expect(proxyLogDirectory()).toBe("/synthetic/proxy");
      expect(proxyLogDirectory("/explicit")).toBe("/explicit");
    } finally {
      if (before.cli === undefined) delete process.env.SIADA_CLI_LOG_DIR;
      else process.env.SIADA_CLI_LOG_DIR = before.cli;
      if (before.proxy === undefined) delete process.env.SIADA_PROXY_LOG_DIR;
      else process.env.SIADA_PROXY_LOG_DIR = before.proxy;
    }
  });

  test("normal mode writes INFO once and suppresses 1000 DEBUG chunks", () => {
    const dir = mkdtempSync(join(tmpdir(), "proxy-log-test-"));
    try {
      const logger = initLogger({ debug: false, logDir: dir });
      for (let i = 0; i < 1000; i++) logger.debug({ i }, "synthetic chunk");
      logger.info("completed");
      const records = readFileSync(join(dir, readdirSync(dir)[0]), "utf8").trim().split("\n");
      expect(records).toHaveLength(1);
      expect(JSON.parse(records[0]).msg).toBe("completed");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("managed stdout and stderr enter the rotating logger without duplicate INFO", () => {
    const dir = mkdtempSync(join(tmpdir(), "proxy-log-test-"));
    try {
      const logger = initLogger({ debug: false, logDir: dir });
      const restore = captureManagedOutput(logger);
      try {
        process.stdout.write("synthetic stdout\n");
        process.stderr.write("synthetic stderr\n");
        logger.info("direct marker");
      } finally {
        restore();
      }
      const records = readFileSync(join(dir, readdirSync(dir)[0]), "utf8").trim().split("\n").map(line => JSON.parse(line));
      expect(records).toHaveLength(3);
      expect(records[0].source).toBe("stdout");
      expect(records[1].level).toBe(40);
      expect(records[2].msg).toBe("direct marker");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("retention protects other live process logs and bootstrap diagnostics", () => {
    const dir = mkdtempSync(join(tmpdir(), "proxy-log-test-"));
    try {
      const alive = join(dir, `acp-proxy-synthetic-${process.pid}-12345678-1234-1234-1234-123456789012.log`);
      const orphan = join(dir, "acp-proxy-synthetic-9999999-12345678-1234-1234-1234-123456789012.log");
      const bootstrap = join(dir, "acp-proxy-launch.log");
      const old = new Date(Date.now() - 8 * 86400000);
      for (const file of [alive, orphan, bootstrap]) {
        writeFileSync(file, "synthetic");
        utimesSync(file, old, old);
      }
      const stream = new RotatingLogStream(join(dir, "acp-proxy-current.log"));
      stream.write("current\n");
      stream.end();
      expect(readdirSync(dir)).toContain(alive.split(/[/\\]/).at(-1)!);
      expect(readdirSync(dir)).not.toContain(orphan.split(/[/\\]/).at(-1)!);
      expect(readdirSync(dir)).toContain("acp-proxy-launch.log");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("a failed write does not destroy the stream and recovery can retry", () => {
    const dir = mkdtempSync(join(tmpdir(), "proxy-log-test-"));
    const missing = join(dir, "missing");
    try {
      const stream = new RotatingLogStream(join(missing, "acp-proxy-test.log"));
      stream.write("failure\n");
      expect(stream.destroyed).toBe(false);
      mkdirSync(missing);
      stream.write("recovered\n");
      stream.end();
      expect(readFileSync(stream.file, "utf8")).toBe("recovered\n");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("size rotation retains bounded backups and preserves the latest record", () => {
    const dir = mkdtempSync(join(tmpdir(), "proxy-log-test-"));
    try {
      const stream = new RotatingLogStream(join(dir, "acp-proxy-test.log"), 32, 3);
      for (let i = 0; i < 20; i++) stream.write(`record-${i}\n`);
      stream.end();
      expect(readdirSync(dir).length).toBe(4);
      expect(readFileSync(stream.file, "utf8")).toContain("record-19");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("parallel requests have isolated session and request fields", async () => {
    const dir = mkdtempSync(join(tmpdir(), "proxy-log-test-"));
    try {
      const logger = initLogger({ debug: true, logDir: dir });
      await Promise.all(["a", "b"].map(requestId =>
        withLogContext({ sessionId: `session-${requestId}`, requestId, agent: `agent-${requestId}` }, async () => {
          await Promise.resolve();
          logger.info("synthetic request");
        })));
      logger.info("idle");
      const file = readdirSync(dir)[0];
      const records = readFileSync(join(dir, file), "utf8").trim().split("\n").map(line => JSON.parse(line));
      expect(records[0].requestId).toBe("a");
      expect(records[1].sessionId).toBe("session-b");
      expect(records[1].agent).toBe("agent-b");
      expect(records[2].requestId).toBe("-");
      expect(records[0].pid).toBe(process.pid);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});