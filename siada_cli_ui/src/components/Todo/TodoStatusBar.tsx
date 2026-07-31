import React from 'react';
import { Box, Text } from '@jrichman/ink';
import type { TodoItem } from '../../hooks/useAcp/types.js';

export type { TodoItem };

interface TodoStatusBarProps {
  items: TodoItem[];
}

const STATUS_ICONS: Record<string, string> = {
  pending: '○',
  in_progress: '◐',
  completed: '✓',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'gray',
  in_progress: 'yellow',
  completed: 'green',
};

/**
 * TodoStatusBar — a compact persistent status bar rendered beneath the main chat layout.
 * Receives live todo state pushed via context/todoState ACP notifications.
 * Renders nothing when the todo list is empty.
 */
export const TodoStatusBar: React.FC<TodoStatusBarProps> = ({ items }) => {
  if (!items || items.length === 0) return null;

  const total = items.length;
  const done = items.filter(t => t.status === 'completed').length;
  const inProgress = items.find(t => t.status === 'in_progress');

  return (
    <Box
      borderStyle="single"
      borderColor="cyan"
      paddingX={1}
      flexDirection="column"
      flexShrink={0}
    >
      <Box>
        <Text color="cyan" bold>Todos </Text>
        <Text dimColor>{`[${done}/${total}]`}</Text>
        {inProgress && (
          <Box marginLeft={2}>
            <Text color="yellow">◐ </Text>
            <Text>{inProgress.content}</Text>
          </Box>
        )}
      </Box>
      <Box flexDirection="row" flexWrap="wrap">
        {items.map((item, idx) => {
          const icon = STATUS_ICONS[item.status] ?? '?';
          const color = STATUS_COLORS[item.status] ?? 'white';
          return (
            <Box key={idx} marginRight={2}>
              <Text color={color}>{icon} </Text>
              <Text dimColor={item.status === 'completed'}>{item.content}</Text>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

export default TodoStatusBar;
