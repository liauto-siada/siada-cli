import React from 'react';
import { Box, Text } from '@jrichman/ink';
import type { SubAgentItem } from '../../hooks/useAcp/types.js';

export interface SubAgentDisplayProps {
  items: SubAgentItem[];
  activeIndex: number;  // -1 = panel visible but no row focused
  width?: number;
}

const STATUS_ICONS: Record<string, string> = {
  running:   '◐',
  completed: '✓',
  failed:    '✗',
};

const STATUS_COLORS: Record<string, string> = {
  running:   'yellow',
  completed: 'green',
  failed:    'red',
};

const MAX_VISIBLE = 5;

export const SubAgentDisplay: React.FC<SubAgentDisplayProps> = ({
  items,
  activeIndex,
  width,
}) => {
  if (!items || items.length === 0) return null;

  const total = items.length;
  let effectiveActive = activeIndex;
  if (effectiveActive < 0) {
    // No row focused: follow the first running item, else the last one.
    const runningIdx = items.findIndex(item => item.status === 'running');
    effectiveActive = runningIdx >= 0 ? runningIdx : total - 1;
  }
  const start = Math.max(0, Math.min(effectiveActive - 2, total - MAX_VISIBLE));
  const end = Math.min(total, start + MAX_VISIBLE);
  const visible = items.slice(start, end);

  const hasAbove = start > 0;
  const hasBelow = end < total;
  const displayPos = activeIndex >= 0 ? `${activeIndex + 1}` : '-';

  return (
    <Box flexDirection="column" paddingX={1} width={width}>
      {/* Header */}
      <Box justifyContent="space-between">
        <Text color="cyan" dimColor>Sub Agents</Text>
        <Text color="cyan" dimColor>
          {hasAbove ? ' ▲ ' : '   '}
          ({displayPos}/{total})
          {hasBelow ? ' ▼' : '  '}
        </Text>
      </Box>

      {/* Items */}
      {visible.map((item, visIdx) => {
        const globalIdx = start + visIdx;
        const isActive = globalIdx === activeIndex;
        const icon = STATUS_ICONS[item.status] ?? '?';
        const iconColor = STATUS_COLORS[item.status] ?? 'white';

        return (
          <Box key={item.id} flexDirection="row">
            <Text color={isActive ? 'cyan' : 'gray'}>
              {isActive ? '▶ ' : '  '}
            </Text>
            <Text color={iconColor}>{icon} </Text>
            <Text
              color={isActive ? 'cyan' : undefined}
              bold={isActive}
              dimColor={item.status === 'completed' && !isActive}
            >
              {item.title}
            </Text>
          </Box>
        );
      })}

      {/* Footer */}
      <Box>
        <Text color="gray">↑↓ navigate • Tab focus • Enter open • Esc close</Text>
      </Box>
    </Box>
  );
};

export default SubAgentDisplay;
