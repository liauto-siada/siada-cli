// Replay injection entry: exposes the replay executor as a page-global so the
// extension can invoke it via chrome.scripting.executeScript (files + func
// share the same ISOLATED world global object).

import { runReplayStep } from "./executor";
import type { ReplayStep } from "@chrome-acp/shared/acp";

declare global {
  interface Window {
    __acpReplay?: { run: typeof runReplayStep };
  }
}

if (!window.__acpReplay) {
  window.__acpReplay = { run: runReplayStep };
}

export type { ReplayStep };
