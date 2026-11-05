import React from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';
import type { TodoItem } from '../../hooks/useAcp/types.js';
import { decodeHtmlEntities } from '../../utils/htmlEntities.js';
import { getTodoVisibleRange } from '../../utils/todoDisplay.js';

export interface TodoDisplayProps {
  items: TodoItem[];
  activeIndex: number;  // -1 = panel visible but no row focused
  width?: number;
  onSelect: (index: number) => void;
  onClose: () => void;
  compact?: boolean;
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

export const TodoDisplay: React.FC<TodoDisplayProps> = ({
  items,
  activeIndex,
  width,
  compact = false,
}) => {
  useUiLanguage();
  if (!items || items.length === 0) return null;

  const total = items.length;
  const { start, end } = getTodoVisibleRange(items, activeIndex);
  const visible = items.slice(start, end);

  const hasAbove = start > 0;
  const hasBelow = end < total;
  const displayPos = activeIndex >= 0 ? `${activeIndex + 1}` : '-';

  return (
    <Box flexDirection="column" paddingX={compact ? 0 : 1} width={width}>
      {/* Header */}
      {!compact && <Box justifyContent="space-between">
        <Text color="cyan" dimColor>{t('待办清单', 'Todos')}</Text>
        <Text color="cyan" dimColor>
          {hasAbove ? ' ▲ ' : '   '}
          ({displayPos}/{total})
          {hasBelow ? ' ▼' : '  '}
        </Text>
      </Box>}

      {/* Items */}
      {visible.map((item, visIdx) => {
        const globalIdx = start + visIdx;
        const isActive = globalIdx === activeIndex;
        const icon = STATUS_ICONS[item.status] ?? '?';
        const iconColor = STATUS_COLORS[item.status] ?? 'white';

        return (
          <Box key={globalIdx} flexDirection="row" height={1} flexShrink={0} overflowX="hidden">
            <Box flexShrink={0}>
              <Text color={isActive ? 'cyan' : 'gray'}>
                {isActive ? '▶ ' : '  '}
              </Text>
              <Text color={iconColor}>{icon} </Text>
            </Box>
            <Box flexGrow={1} flexShrink={1} overflowX="hidden">
              <Text
                color={isActive ? 'cyan' : undefined}
                bold={isActive}
                dimColor={item.status === 'completed' && !isActive}
                wrap="truncate-end"
              >
                {decodeHtmlEntities(item.content).replace(/\s+/g, ' ').trim()}
              </Text>
            </Box>
          </Box>
        );
      })}

      {/* Footer */}
      {!compact && <Box>
        <Text color="gray">{PANEL_TIPS.todo}</Text>
      </Box>}
    </Box>
  );
};

export default TodoDisplay;
