/**
 * Status Bar Dialog
 * Allows users to toggle visibility of individual status bar items
 */

import React, { useState } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';

// Full 12-item definition: key → label preview
const STATUSBAR_ITEM_LABELS: Record<string, string> = {
  model: 'Model: kivy-glm-5.2',
  balance: 'Balance: 25.34%',
  input_cost: 'in:¥0.0012(12,345)',
  output_cost: 'out:¥0.0034(6,789)',
  cache_write_cost: 'cw:¥0.0001(100)',
  cache_read_cost: 'cr:¥0.0023(1,234)',
  total_cost: 'cost:¥0.0046(19,234)',
  hit_rate: 'hit:45.2%',
  git_branch: '⎇ main',
  workspace: '~/projects/foo',
  cost_time: '12.3s',
  token_usage: '68,284 / 600,000 tokens',
};

// Description for each status bar item, shown below the list and follows the current selection
const STATUSBAR_ITEM_DESCRIPTIONS: Record<string, string> = {
  model: 'Name of the model currently in use',
  balance: 'Account balance, as a percentage of remaining quota',
  input_cost: 'Cost and token count for input not served from cache',
  output_cost: 'Cost and token count for model output',
  cache_write_cost: 'Cost and token count for writing context into the cache (first-time context)',
  cache_read_cost: 'Cost and token count for context served from cache (reused context)',
  total_cost: 'Total accumulated cost and token count for this turn',
  hit_rate: 'Cache hit rate = cache-read tokens / (input + cache-read) tokens; higher means more context reuse',
  git_branch: 'Git branch of the current working directory',
  workspace: 'Path of the current working directory',
  cost_time: 'Elapsed time for this turn (from turn start to the latest model response)',
  token_usage: 'Tokens used in the current context / the model\'s context window limit',
};

const STATUSBAR_KEYS = Object.keys(STATUSBAR_ITEM_LABELS);

interface StatusBarDialogProps {
  visibleItems: string[];
  onToggle: (key: string) => void;
  onClose: () => void;
}

export function StatusBarDialog({
  visibleItems,
  onToggle,
  onClose,
}: StatusBarDialogProps): React.JSX.Element {
  const [selectedIndex, setSelectedIndex] = useState(0);

  useKeypress(
    (key) => {
      // Up arrow
      if (key.name === 'up') {
        setSelectedIndex((prev) => Math.max(0, prev - 1));
        return;
      }

      // Down arrow
      if (key.name === 'down') {
        setSelectedIndex((prev) => Math.min(STATUSBAR_KEYS.length - 1, prev + 1));
        return;
      }

      // Space or Enter to toggle
      if (key.name === 'space' || key.name === 'return') {
        onToggle(STATUSBAR_KEYS[selectedIndex]);
        return;
      }

      // Escape to close
      if (key.name === 'escape') {
        onClose();
        return;
      }
    },
    { isActive: true }
  );

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="gray"
      paddingX={2}
      paddingY={1}
      width="100%"
    >
      <Box marginBottom={1}>
        <Text bold color="white">
          Status Bar Items
        </Text>
      </Box>

      {STATUSBAR_KEYS.map((key, index) => {
        const isSelected = index === selectedIndex;
        const isVisible = visibleItems.includes(key);
        const label = STATUSBAR_ITEM_LABELS[key];

        return (
          <Box key={key} marginLeft={1}>
            <Text
              color={isSelected ? 'cyan' : 'white'}
              bold={isSelected}
            >
              {isVisible ? '● ' : '○ '}
              {label}
            </Text>
          </Box>
        );
      })}

      <Box marginTop={1} paddingX={1}>
        <Text color="gray">
          {STATUSBAR_ITEM_DESCRIPTIONS[STATUSBAR_KEYS[selectedIndex]]}
        </Text>
      </Box>

      <Box marginTop={1} borderStyle="single" borderColor="gray" paddingX={1}>
        <Text>
          ↑↓ Navigate • Space/Enter Toggle • Esc Close
        </Text>
      </Box>
    </Box>
  );
}