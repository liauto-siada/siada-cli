// Trajectory writer: appends recorded browser-operation events to
// ~/.siada-cli/workspace/browser_trajectories/YYYY-MM-DD.jsonl — one file per
// day, the on-disk record of the `/ws/trajectory` step events (documented in
// docs/docs/reference/architecture.md).
//
// The same batch received on /ws/trajectory is also forwarded to the tab's
// agent subprocess over ACP (`_trajectory_event`), which is the path
// siada-agenthub's browser-skill pipeline consumes
// (`siada/services/browser_skill/`); this directory is documented as the
// recording location there (`siada/services/browser_skill/paths.py`).

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
