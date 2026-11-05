// Trajectory writer: appends recorded browser-operation events to
// ~/.siada-cli/workspace/browser_trajectories/YYYY-MM-DD.jsonl.
//
// This is the sole persistence point for raw browser trajectories. The
// siada-agenthub daemon reads these files directly from disk to run its
// offline distillation pipeline (atomize -> classify -> bucket -> distill),
// producing reusable Skills. See design_docs/browser-skill-graph-design.md
// in the siada-agenthub repo for the full design.
//
// Superseded: the old ~/.chrome-acp/trajectories + LEARNING.md "agent
// manually summarizes pipelines" mechanism has been retired in favor of the
// automated distillation pipeline above.

import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { log } from "./logger.js";

export interface TrajectoryWriterOptions {
  /** Defaults to ~/.siada-cli/workspace/browser_trajectories */
  baseDir?: string;
  /** Defaults to () => new Date() */
  now?: () => Date;
}

export function getBaseDir(): string {
  return join(homedir(), ".siada-cli", "workspace", "browser_trajectories");
}

export function trajectoryFileFor(date: Date, baseDir = getBaseDir()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return join(baseDir, `${year}-${month}-${day}.jsonl`);
}

export function appendTrajectoryEvents(
  events: unknown[],
  options: TrajectoryWriterOptions = {},
): void {
  if (events.length === 0) return;
  const baseDir = options.baseDir ?? getBaseDir();
  const now = options.now ?? (() => new Date());

  mkdirSync(baseDir, { recursive: true });
  const file = trajectoryFileFor(now(), baseDir);
  const lines = events.map((event) => JSON.stringify(event)).join("\n") + "\n";
  appendFileSync(file, lines, "utf8");
  log.info("[STEP 7] trajectory persisted to jsonl", { file, count: events.length });
}
