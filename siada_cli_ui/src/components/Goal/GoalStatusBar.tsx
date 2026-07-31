import React, { useState, useEffect } from 'react';
import { Box, Text } from '@jrichman/ink';
import stringWidth from 'string-width';
import type { GoalState } from '../../hooks/useAcp/types.js';
import { formatDate } from '../../utils/formatter.js';



export interface GoalStatusBarProps {
  goalState: GoalState | null;
  width?: number;
  /**
   * Transient one-line flash for /goal set / pass-fail results (App.tsx's
   * `goalNotice`). Rendered on the SAME row as the status label — left-
   * aligned with a small purple "●" bullet — instead of stacking on its
   * own line below, so the notice and the persistent status never visually
   * separate into two bars.
   */
  notice?: string | null;
  /**
   * Mirrors the app-wide Ctrl+O "collapsed" state used elsewhere (e.g. the
   * goal_result chat message's "(ctrl+o to expand)" convention in
   * Message.tsx). When false, this bar expands below the single-line
   * status row to show the full goal objective/status/start time.
   */
  isCollapsed?: boolean;
}


const STATUS_COLORS: Record<string, string> = {
  active: 'cyan',
  blocked: 'red',
  complete: 'green',
};

const STATUS_LABELS: Record<string, string> = {
  active: 'Goal (active)',
  blocked: 'Goal (blocked)',
  complete: 'Goal complete',
};

/** Mirrors ThinkingIndicator's formatTime — keeps the "Ns" / "Nm Ns" style
 * consistent across every elapsed-time display in the UI. */
const formatElapsed = (seconds: number): string => {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
};

/**
 * Truncate `text` to fit within `maxWidth` *display columns*, ending with
 * "..." when it would otherwise overflow. The notice (e.g. "Goal set:
 * <objective>" / "Goal reached: <objective>") embeds a user-supplied
 * objective that can be arbitrarily long — and often contains CJK text,
 * where each character occupies 2 terminal columns instead of 1. Truncating
 * by `.length` (UTF-16 code units) under-counts CJK width, so a notice that
 * "fits" by length can still overflow the row and wrap onto a second line.
 * `string-width` measures actual terminal display width, and we trim one
 * grapheme at a time so the result never overshoots `maxWidth` columns.
 */
const truncateNotice = (text: string, maxWidth: number): string => {
  if (maxWidth <= 0) return '';
  if (stringWidth(text) <= maxWidth) return text;
  if (maxWidth <= 3) {
    // Not even room for "...": hard-trim by display width, char by char.
    let result = '';
    for (const ch of text) {
      if (stringWidth(result + ch) > maxWidth) break;
      result += ch;
    }
    return result;
  }
  const budget = maxWidth - 3;
  let result = '';
  for (const ch of text) {
    if (stringWidth(result + ch) > budget) break;
    result += ch;
  }
  return `${result}...`;
};


export const GoalStatusBar: React.FC<GoalStatusBarProps> = ({ goalState, width, notice, isCollapsed = true }) => {
  const goal = goalState?.goal;
  const createdAt = goal?.createdAt;
  const status = goal?.status;
  const turns = goal?.turns;


  // Live "time since goal was set" counter, ticking every second — same
  // pattern as ThinkingIndicator's elapsedSeconds timer. Computed from the
  // backend's ISO-8601 `createdAt` rather than incrementing a local counter,
  // so it stays correct across re-renders/remounts (e.g. resumed sessions)
  // instead of resetting to 0.
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!createdAt) {
      setElapsedSeconds(0);
      return;
    }
    const startMs = new Date(createdAt).getTime();
    const tick = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    tick(); // paint immediately instead of waiting a full second for the first tick

    // Once the goal is complete, freeze the counter at whatever it just
    // computed above instead of continuing to tick — the goal is done, so
    // "time elapsed" should stop advancing rather than keep counting up
    // toward the moment the status bar eventually disappears.
    if (status === 'complete') {
      return;
    }

    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [createdAt, status]);

  // Nothing to show at all — no persistent goal AND no transient notice.
  if (!goal && !notice) return null;

  const color = goal ? (STATUS_COLORS[goal.status] ?? 'white') : 'white';
  const label = goal ? (STATUS_LABELS[goal.status] ?? 'Goal') : null;

  // Plain-text width of the right-side label block (status label + elapsed
  // time), so the notice on the left can be truncated to whatever room is
  // actually left on this single row instead of overflowing onto a second
  // line. Mirrors the exact text rendered further below.
  const elapsedText = createdAt && elapsedSeconds > 0
    ? ` (${formatElapsed(elapsedSeconds)}${
        typeof turns === 'number' && turns > 0 ? ` · ${turns} turn${turns === 1 ? '' : 's'}` : ''
      })`
    : '';
  // Same "(ctrl+o to expand)" convention as the goal_result chat message
  // (Message.tsx) — only shown while collapsed, so the hint disappears once
  // the user has already expanded the detail block below.
  const hintText = goal && isCollapsed ? ' (ctrl+o for details)' : '';
  const labelWidth = label ? label.length + elapsedText.length + hintText.length : 0;

  const rowWidth = width ? width - 2 : 80;
  // Reserve: "●" bullet (1) + gap between bullet/text (1) + gap between the
  // notice block and the label block (1) + label block width.
  const noticeMaxWidth = rowWidth - 2 - (labelWidth ? labelWidth + 1 : 0);
  const displayNotice = notice ? truncateNotice(notice, noticeMaxWidth) : notice;

  const elapsedCore = createdAt && elapsedSeconds > 0 ? formatElapsed(elapsedSeconds) : '';
  const turnsSuffix = typeof turns === 'number' && turns > 0
    ? ` · ${turns} turn${turns === 1 ? '' : 's'}`
    : '';
  const hintChunk = goal && isCollapsed ? '(ctrl+o for details)' : '';

  const noticeBlockWidth = displayNotice ? 2 + stringWidth(displayNotice) : 0;
  const availableForLabelBlock = Math.max(
    0,
    rowWidth - noticeBlockWidth - (noticeBlockWidth > 0 ? 1 : 0),
  );

  let includeHint = Boolean(hintChunk) && Boolean(label);
  let includeTurns = Boolean(turnsSuffix);
  let includeElapsed = Boolean(elapsedCore);
  let displayLabel = label ?? '';

  if (label) {
    const measure = (withHint: boolean, withTurns: boolean, withElapsed: boolean): number => {
      const chunks = [displayLabel];
      if (withElapsed) chunks.push(`(${elapsedCore}${withTurns ? turnsSuffix : ''})`);
      if (withHint) chunks.push(hintChunk);
      return chunks.reduce((sum, c) => sum + stringWidth(c), 0) + (chunks.length - 1);
    };

    if (measure(includeHint, includeTurns, includeElapsed) > availableForLabelBlock) {
      includeHint = false;
    }
    if (measure(includeHint, includeTurns, includeElapsed) > availableForLabelBlock) {
      includeTurns = false;
    }
    if (measure(includeHint, includeTurns, includeElapsed) > availableForLabelBlock) {
      includeElapsed = false;
    }
    if (measure(includeHint, includeTurns, includeElapsed) > availableForLabelBlock) {
      displayLabel = truncateNotice(displayLabel, availableForLabelBlock);
    }
  }

  return (
    <Box flexDirection="column" paddingX={1} width={width}>
      {/* Only the status label is shown here — the goal objective text is
          intentionally omitted since it can be arbitrarily long and would
          overflow/clutter this persistent single-line bar. Full objective
          text is available in the /goal set confirmation and the
          collapsible Goal achieved/not-yet-achieved chat message instead.

          The transient notice (left, purple "●" bullet) and the persistent
          status label (right) share this ONE row via `space-between` — they
          used to be two stacked rows, which visually read as two separate
          bars whenever a notice was showing. */}
      <Box flexDirection="row" justifyContent="space-between" width={width ? width - 2 : undefined}>
        {/* NOTE: the "goal verifying..." spinner is intentionally NOT
            rendered here anymore -- it now lives in MainLayout, in the
            EXACT SAME row/slot as the normal per-turn ThinkingIndicator
            (immediately above this status bar), so both animations share
            one consistent position instead of the goal spinner living in
            a different place. See MainLayout.tsx. */}
        <Box flexDirection="row" gap={1}>
          {displayNotice && (
            <>
              <Text color="#c5a3ff">●</Text>
              <Text color="gray">{displayNotice}</Text>
            </>
          )}
        </Box>

        {label && (
          // Rendered as ONE <Text> (not separate sibling <Text> elements in a
          // gapped Box) with wrap="truncate-end" — this is a hard guarantee
          // against ever wrapping onto a second line, regardless of how Yoga
          // ends up distributing width between this block and the notice
          // block on the left. The width-budget logic above (measure() /
          // includeHint / includeTurns / includeElapsed) already tries to
          // proactively drop the least essential pieces so truncation is
          // rarely needed in practice, but wrap="truncate-end" is the actual
          // mechanism that prevents Ink/Yoga from ever emitting a second
          // line here — which, when it happened, visually bled into
          // whatever renders directly below (e.g. the input box's border).
          // Multiple <Text> elements as flex siblings can each wrap
          // independently even when their combined content technically
          // "fits" by our own measurement, if Yoga's actual width allocation
          // for this flex child differs even slightly from what we assumed;
          // nesting everything inside one wrap-controlled <Text> removes
          // that assumption entirely.
          <Text wrap="truncate-end">
            <Text color={color} bold={goal?.status === 'complete'}>
              {displayLabel}
            </Text>
            {includeElapsed && (
              <Text color="gray" dimColor>
                {' '}({elapsedCore}{includeTurns ? turnsSuffix : ''})
              </Text>
            )}
            {includeHint && (
              <Text color="gray" dimColor>
                {' '}{hintChunk}
              </Text>
            )}
          </Text>
        )}

      </Box>

      {/* Expanded goal detail — mirrors the app-wide Ctrl+O convention
          (isCollapsed=false) used by the goal_result chat summary in
          Message.tsx. Full objective text lives here instead of the
          single-line bar above, in its own bordered panel so it reads as a
          distinct detail block rather than just more status-bar text. */}
      {goal && !isCollapsed && (
        <Box
          flexDirection="column"
          marginTop={1}
          paddingX={1}
          borderStyle="single"
          borderColor="gray"
          width={width ? width - 2 : undefined}
        >
          <Text>
            <Text dimColor>Objective: </Text>
            <Text color="gray">{goal.objective}</Text>
          </Text>
          <Text color="gray" dimColor>
            Status: {goal.status}
            {createdAt ? ` · Started: ${formatDate(createdAt)}` : ''}
            {typeof turns === 'number' ? ` · Turns: ${turns}` : ''}
          </Text>
        </Box>
      )}
    </Box>
  );
};



export default GoalStatusBar;
