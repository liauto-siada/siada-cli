import { describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { RotatingLogStream, initLogger, withLogContext } from "../src/logger.ts";

describe("proxy logging", () => {
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