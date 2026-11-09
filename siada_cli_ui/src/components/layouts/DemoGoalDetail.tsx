import React from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';
import type { GoalState } from '../../hooks/useAcp/types.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { colors } from '../../utils/colors.js';
import { Scrollable } from '../common/Scrollable.js';
import { goalResultLabel, goalStatusLabel } from '../../utils/goalDisplay.js';
import { formatDate } from '../../utils/formatter.js';

export function DemoGoalDetail({ state, width, height, onClose }: {
  state?: GoalState | null; width: number; height: number; onClose: () => void;
}) {
  useUiLanguage();
  useKeypress(key => {
    if (key.name === 'escape' || key.ctrl && key.name === 'c') onClose();
  });
  const goal = state?.goal;
  const status = goalStatusLabel(state);
  const result = state?.latestResult ?? state?.result;
  return <Box height={height} width={width} paddingX={1} flexDirection="column">
    <Box height={1} flexShrink={0}><Text bold>Goal · Objective and verification</Text></Box>
    <Scrollable width={Math.max(1, width - 2)} height={Math.max(1, height - 2)}
      hasFocus scrollToBottom={false}>
      <Text>{goal?.objective || 'No active goal'}</Text>
      {goal && <Text color={colors.content.secondary}>
        Status: {status}{goal.turns !== undefined ? ` · ${goal.turns} check${goal.turns === 1 ? '' : 's'}` : ''}
      </Text>}
      {goal?.createdAt && <Text color={colors.content.secondary}>Started: {formatDate(goal.createdAt)}</Text>}
      {result && <>
        <Text color={result.achieved ? colors.success : colors.warning}>
          Last check: {goalResultLabel(result)}
        </Text>
        <Text>Reason: {result.reason}</Text>
        {result.nextAction && <Text>Next action: {result.nextAction}</Text>}
        <Text color={colors.content.secondary}>
          Elapsed: {result.elapsedSeconds}s
        </Text>
      </>}
      {goal?.status === 'blocked' && <Text color={colors.content.secondary}>
        Send a new message to continue this goal, or use /goal clear to remove it.
      </Text>}
    </Scrollable>
    <Text color={colors.content.tertiary} wrap="truncate-end">{PANEL_TIPS.demoGoal}</Text>
  </Box>;
}