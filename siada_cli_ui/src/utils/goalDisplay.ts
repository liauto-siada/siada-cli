import type { GoalResult, GoalState } from '../hooks/useAcp/types.js';
import stringWidth from './terminalWidth.js';

/** Extrapolate active snapshots and keep stopped goals stable across remounts. */
export function goalElapsedSeconds(state?: GoalState | null, nowMs = Date.now()): number | undefined {
  const goal = state?.goal;
  if (!goal) return undefined;
  if (typeof goal.elapsedSeconds === 'number' && Number.isFinite(goal.elapsedSeconds)) {
    const snapshotMs = Date.parse(goal.elapsedUpdatedAt ?? '');
    const liveSeconds = goal.status === 'active' && Number.isFinite(snapshotMs)
      ? Math.max(0, (nowMs - snapshotMs) / 1000) : 0;
    return Math.max(0, Math.floor(goal.elapsedSeconds + liveSeconds));
  }
  const startMs = Date.parse(goal.createdAt ?? '');
  const endMs = goal.status === 'active' ? nowMs : Date.parse(goal.updatedAt ?? '');
  if (Number.isFinite(startMs) && Number.isFinite(endMs)) {
    return Math.max(0, Math.floor((endMs - startMs) / 1000));
  }
  const result = state?.result ?? state?.latestResult;
  return goal.status !== 'active' && typeof result?.elapsedSeconds === 'number' &&
    Number.isFinite(result.elapsedSeconds) ? Math.max(0, Math.floor(result.elapsedSeconds)) : undefined;
}

/** Compact objective previews use terminal columns, including CJK width. */
export function goalObjectivePreview(objective: string, maxWidth = 24): string {
  const text = objective.replace(/\s+/g, ' ').trim();
  if (maxWidth <= 0) return '';
  if (stringWidth(text) <= maxWidth) return text;
  let preview = '';
  for (const character of text) {
    if (stringWidth(preview + character) > maxWidth - 1) break;
    preview += character;
  }
  return `${preview}…`;
}

export function goalResultLabel(result: GoalResult): string {
  if (result.outcome === 'blocked') return 'Automatic continuation stopped';
  if (result.outcome === 'system_error') return 'Verification error';
  return result.achieved ? 'Achieved' : 'Not achieved';
}

export function goalResultSummary(result: GoalResult, maxWidth = 64): string {
  const label = result.outcome === 'blocked' ? 'Stopped'
    : result.outcome === 'system_error' ? 'Check error' : goalResultLabel(result);
  const continuation = result.continuing ?? (!result.achieved && !result.outcome);
  const suffix = continuation ? ' · Continuing'
    : result.outcome === 'system_error' ? ' · Stopped' : '';
  const prefix = `Goal ${label}`;
  const objective = goalObjectivePreview(result.objective,
    Math.min(24, Math.max(0, maxWidth - stringWidth(prefix + suffix + ' · '))));
  return `${prefix}${objective ? ` · ${objective}` : ''}${suffix}`;
}

export function goalStatusLabel(state?: GoalState | null): string {
  if (state?.verifying) return 'Verifying…';
  if (state?.goal?.status === 'blocked') return 'Automatic continuation stopped';
  if (state?.goal?.status === 'paused') return 'Paused';
  if (state?.goal?.status === 'complete') return 'Achieved';
  if (state?.result?.outcome === 'system_error') return 'Verification error';
  return 'In progress';
}