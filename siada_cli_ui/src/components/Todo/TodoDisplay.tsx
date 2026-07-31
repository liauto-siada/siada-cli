import React from 'react';
import { Box, Text } from '@jrichman/ink';
import type { TodoItem } from '../../hooks/useAcp/types.js';

export interface TodoDisplayProps {
  items: TodoItem[];
  activeIndex: number;  // -1 = panel visible but no row focused
  width?: number;
  onSelect: (index: number) => void;
  onClose: () => void;
}

const STATUS_ICONS: Record<string, string> = {
  pending:     '○',
  in_progress: '◐',
  completed:   '✓',
};

const STATUS_COLORS: Record<string, string> = {
  pending:     'gray',
  in_progress: 'yellow',
  completed:   'green',
};

const MAX_VISIBLE = 5;

export const TodoDisplay: React.FC<TodoDisplayProps> = ({
  items,
  activeIndex,
  width,
}) => {
  if (!items || items.length === 0) return null;

  const total = items.length;
  let effectiveActive = activeIndex;
  if (effectiveActive < 0) {
    // No row focused: auto-scroll to the current in-progress/pending item
    // so the visible window follows task progress instead of staying at top.
    const inProgressIdx = items.findIndex(item => item.status === 'in_progress');
    if (inProgressIdx >= 0) {
      effectiveActive = inProgressIdx;
    } else {
      const pendingIdx = items.findIndex(item => item.status === 'pending');
      effectiveActive = pendingIdx >= 0 ? pendingIdx : total - 1;
    }
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
        <Text color="cyan" dimColor>Todos</Text>
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
          <Box key={globalIdx} flexDirection="row">
            <Text color={isActive ? 'cyan' : 'gray'}>
              {isActive ? '▶ ' : '  '}
            </Text>
            <Text color={iconColor}>{icon} </Text>
            <Text
              color={isActive ? 'cyan' : undefined}
              bold={isActive}
              dimColor={item.status === 'completed' && !isActive}
            >
              {item.content}
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

export default TodoDisplay;
