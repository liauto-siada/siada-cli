/**
 * Task Selector Component
 * Displays a list of pending tasks discovered by the proactive agent.
 * Arrow keys navigate, Enter selects a task and sends it to the agent.
 */

import React, { useState, useCallback } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';

export interface TaskItem {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  category: string;
  status: string;
  needs_confirmation: boolean;
  suggested_actions: string[];
  confidence: number;
}

export interface TaskSelectorProps {
  tasks: TaskItem[];
  onSelect: (task: TaskItem) => void;
  onExit: () => void;
}

const PRIORITY_LABEL: Record<string, { label: string; color: string }> = {
  high:   { label: '!!!', color: 'red' },
  medium: { label: '!  ', color: 'yellow' },
  low:    { label: '   ', color: 'gray' },
};

const CATEGORY_COLOR: Record<string, string> = {
  feature:  'cyan',
  bug:      'red',
  refactor: 'magenta',
  doc:      'blue',
  test:     'green',
  other:    'gray',
};

export const TaskSelector: React.FC<TaskSelectorProps> = ({ tasks, onSelect, onExit }) => {
  const [activeIndex, setActiveIndex] = useState(0);

  const moveSelection = useCallback((delta: number) => {
    setActiveIndex(prev => {
      const next = prev + delta;
      if (next < 0) return 0;
      if (next >= tasks.length) return tasks.length - 1;
      return next;
    });
  }, [tasks.length]);

  useKeypress((key) => {
    if (key.name === 'up' || key.sequence === 'k') {
      moveSelection(-1);
    } else if (key.name === 'down' || key.sequence === 'j') {
      moveSelection(1);
    } else if (key.name === 'return') {
      const selected = tasks[activeIndex];
      if (selected) onSelect(selected);
    } else if (
      key.name === 'escape' ||
      (key.ctrl && key.name === 'c') ||
      key.sequence === 'q' ||
      key.sequence === 'Q'
    ) {
      onExit();
    }
  });

  if (tasks.length === 0) {
    return (
      <Box flexDirection="column" paddingX={1}>
        <Box marginBottom={1} borderStyle="single" borderColor="yellow" paddingX={1}>
          <Text color="yellow" bold>No Tasks Found</Text>
        </Box>
        <Box paddingX={1}>
          <Text color="gray" dimColor>Run the proactive daemon to discover tasks.  Esc/q to close</Text>
        </Box>
      </Box>
    );
  }

  const activeTask = tasks[activeIndex];

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box flexDirection="column" marginBottom={1}>
        <Box borderStyle="single" borderColor="cyan" paddingX={1}>
          <Text bold color="cyan">Pending Tasks</Text>
        </Box>
        <Box paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>
            {tasks.length} task{tasks.length !== 1 ? 's' : ''} discovered
          </Text>
        </Box>
      </Box>

      {/* Task list */}
      <Box flexDirection="column" paddingX={1}>
        {tasks.map((task, index) => {
          const isActive = index === activeIndex;
          const prio = PRIORITY_LABEL[task.priority] ?? { label: '   ', color: 'gray' };
          const catColor = CATEGORY_COLOR[task.category] ?? 'white';
          const conf = task.confidence.toFixed(2);
          const cat = task.category.slice(0, 5).padEnd(5);

          return (
            <Box key={task.id} flexDirection="column">
              {/* Main row */}
              <Box flexDirection="row">
                <Text color={isActive ? 'cyan' : 'white'}>
                  {isActive ? '▶ ' : '  '}
                </Text>
                <Text color={prio.color} bold={isActive}>
                  {prio.label}
                </Text>
                <Text> </Text>
                <Text color={catColor} dimColor={!isActive}>
                  {cat}
                </Text>
                <Text color="gray" dimColor>
                  {' '}{conf}{'  '}
                </Text>
                <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>
                  {task.title}
                </Text>
                {task.needs_confirmation && (
                  <Text color="yellow" dimColor> [confirm]</Text>
                )}
              </Box>

              {/* Description row — only for active item */}
              {isActive && (
                <Box paddingLeft={10} marginBottom={1}>
                  <Text color="gray" dimColor wrap="wrap">
                    {task.description.length > 120
                      ? task.description.slice(0, 120) + '…'
                      : task.description}
                  </Text>
                </Box>
              )}
            </Box>
          );
        })}
      </Box>

      {/* Footer */}
      <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
        <Text color="gray" dimColor>
          ↑↓/j/k navigate · Enter execute · Esc/q exit
        </Text>
      </Box>
    </Box>
  );
};
