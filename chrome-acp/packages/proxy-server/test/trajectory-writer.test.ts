import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  appendTrajectoryEvents,
  trajectoryFileFor,
} from "../src/trajectory-writer.ts";

let baseDir: string;

beforeEach(() => {
  baseDir = mkdtempSync(join(tmpdir(), "chrome-acp-test-"));
});

afterEach(() => {
  rmSync(baseDir, { recursive: true, force: true });
});

describe("trajectoryFileFor", () => {
  test("names files by local date", () => {
    const date = new Date(2025, 0, 15, 12, 0, 0); // 2025-01-15 local time
    expect(trajectoryFileFor(date, baseDir)).toBe(
      join(baseDir, "2025-01-15.jsonl"),
    );
  });

  test("zero-pads month and day", () => {
    const date = new Date(2025, 11, 5, 12, 0, 0); // 2025-12-05
    expect(trajectoryFileFor(date, baseDir)).toBe(
      join(baseDir, "2025-12-05.jsonl"),
    );
  });
});

describe("appendTrajectoryEvents", () => {
  test("creates the base directory and writes one JSON line per event", () => {
    const events = [
      { ts: 1, type: "navigation", url: "https://a.com", title: "A" },
      { ts: 2, type: "action", url: "https://a.com", title: "A", action: { kind: "click" } },
    ];
    appendTrajectoryEvents(events, { baseDir, now: () => new Date(2025, 0, 15) });

    const file = join(baseDir, "2025-01-15.jsonl");
    const lines = readFileSync(file, "utf8").trim().split("\n");
    expect(lines.length).toBe(2);
    expect(JSON.parse(lines[0]!)).toEqual(events[0]);
    expect(JSON.parse(lines[1]!)).toEqual(events[1]);
  });

  test("appends to an existing file instead of overwriting", () => {
    const options = { baseDir, now: () => new Date(2025, 0, 15) };
    appendTrajectoryEvents([{ ts: 1 }], options);
    appendTrajectoryEvents([{ ts: 2 }], options);

    const file = join(baseDir, "2025-01-15.jsonl");
    const lines = readFileSync(file, "utf8").trim().split("\n");
    expect(lines.length).toBe(2);
  });

  test("ignores empty event batches", () => {
    appendTrajectoryEvents([], { baseDir });
    expect(existsSync(join(baseDir, "2025-01-15.jsonl"))).toBe(false);
  });
});
