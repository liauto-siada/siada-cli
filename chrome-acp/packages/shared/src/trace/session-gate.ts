// Session isolation for the trace collector.
//
// ACP addresses every session update by session id, and the UI switches its
// active session *before* load/resume finishes (see SessionSwitchingHandler in
// acp/client.ts), so updates belonging to the session the user just left keep
// arriving for a while. Recording those in the new run would blend two
// sessions into one timeline — the trace would claim a step that was never
// part of the run it is showing.
//
// This gate applies the same rule ChatInterface applies to its own handler:
// before any session is active every update passes (pre-session noise lands in
// a run that gets discarded on activation), afterwards only the active
// session's updates do.

export interface SessionGate {
  /** Remember which session the viewer is now following. `null` = none yet. */
  setActive(sessionId: string | null): void;
  /** Whether an update for `sessionId` belongs to the current run. */
  accepts(sessionId: string): boolean;
}

export function createSessionGate(): SessionGate {
  let active: string | null = null;
  return {
    setActive(sessionId: string | null): void {
      active = sessionId;
    },
    accepts(sessionId: string): boolean {
      return active === null || sessionId === active;
    },
  };
}
