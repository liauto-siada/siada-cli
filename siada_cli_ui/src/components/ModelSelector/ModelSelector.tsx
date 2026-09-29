/**
 * Model Selector Component
 * Displays a list of available models and allows the user to switch
 */

import React, { useState, useCallback } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { useClearScreenOnMount } from '../../hooks/useClearScreenOnMount.js';
import { calculateVisibleRange } from '../../utils/sessionUtils.js';

export interface ModelSelectorProps {
  models: string[];
  currentModel: string;
  modelNotes?: Record<string, string>;
  onSelect: (modelName: string) => void;
  onExit: () => void;
}

/**
 * Row budget for everything except the model rows themselves: header (6)
 * + footer (4) + scroll indicators (2) = 12, plus one extra row for the
 * renderer's trailing newline (the frame is written as `frame + '\n'`; a
 * frame exactly `terminalRows` tall scrolls its first line into scrollback
 * on every redraw). Each model renders exactly 1 row (all texts use
 * wrap="truncate"), so the rendered frame stays within
 * `terminalRows - 1` — otherwise Ink redraws the frame bottom-aligned and
 * the top of the list (including the active item) is pushed out of view.
 */
const CHROME_ROWS = 13;

export function calculateVisibleModelCount(terminalRows: number): number {
  return Math.max(1, terminalRows - CHROME_ROWS);
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  currentModel,
  modelNotes,
  onSelect,
  onExit,
}) => {
  // Start selection on the current model if present, otherwise 0
  const initialIndex = Math.max(0, models.indexOf(currentModel));
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const { rows: terminalRows } = useTerminalSize();
  // Fullscreen view: clear the screen on mount and paint the first frame
  // from row 1 instead of mid-screen (where it would scroll its top off).
  const cleared = useClearScreenOnMount();

  const moveSelection = useCallback((delta: number) => {
    setActiveIndex(prev => {
      const next = prev + delta;
      if (next < 0) return 0;
      if (next >= models.length) return models.length - 1;
      return next;
    });
  }, [models.length]);

  useKeypress((key) => {
    if (key.name === 'up' || key.sequence === 'k') {
      moveSelection(-1);
    } else if (key.name === 'down' || key.sequence === 'j') {
      moveSelection(1);
    } else if (key.name === 'return') {
      const selected = models[activeIndex];
      if (selected) {
        onSelect(selected);
      }
    } else if (
      key.name === 'escape' ||
      (key.ctrl && key.name === 'c') ||
      key.sequence === 'q' ||
      key.sequence === 'Q'
    ) {
      onExit();
    }
  });

  if (models.length === 0) {
    return (
      <Box flexDirection="column" paddingX={1}>
        <Box marginBottom={1} borderStyle="single" borderColor="yellow" paddingX={1}>
          <Text color="yellow" bold>No Models Available</Text>
        </Box>
        <Box paddingX={1}>
          <Text color="gray" dimColor>Press Esc or q to close</Text>
        </Box>
      </Box>
    );
  }

  // Wait for the mount clear so the first real frame paints from row 1.
  if (!cleared) return null;

  // Height-limited window centered on the active item (same approach as
  // SessionBrowser): the terminal only shows the bottom of a frame taller
  // than itself, so an unwindowed list hides the active item.
  const visibleCount = calculateVisibleModelCount(terminalRows);
  const { startIndex, endIndex } = calculateVisibleRange(
    models.length,
    activeIndex,
    visibleCount
  );
  const visibleModels = models.slice(startIndex, endIndex);

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box flexDirection="column" marginBottom={1}>
        <Box borderStyle="single" borderColor="cyan" paddingX={1}>
          <Text bold color="cyan" wrap="truncate">Switch Model</Text>
        </Box>
        <Box paddingX={1} marginTop={1}>
          <Text color="gray" dimColor wrap="truncate">
            Current: <Text color="green">{currentModel}</Text>
            {'  '}·{'  '}
            {models.length} models available
          </Text>
        </Box>
      </Box>

      {/* Model list (windowed so the frame fits the terminal) */}
      <Box flexDirection="column" paddingX={1}>
        {startIndex > 0 && (
          <Box paddingX={1}>
            <Text color="gray" dimColor>↑ More above...</Text>
          </Box>
        )}
        {visibleModels.map((model, idx) => {
          const index = startIndex + idx;
          const isActive = index === activeIndex;
          const isCurrent = model === currentModel;

          const note = modelNotes?.[model] ? `(${modelNotes[model]})` : '';

          return (
            <Box key={`${model}-${index}`} flexDirection="row">
              <Text color={isActive ? 'cyan' : 'white'}>
                {isActive ? '▶ ' : '  '}
              </Text>
              <Text
                color={isActive ? 'cyan' : isCurrent ? 'green' : 'white'}
                bold={isActive}
                wrap="truncate"
              >
                {model}
              </Text>
              {note && (
                <Text color={isActive ? 'cyan' : isCurrent ? 'green' : 'white'} wrap="truncate">
                  {'  '}{note}
                </Text>
              )}
              {isCurrent && (
                <Text color="green" dimColor wrap="truncate">
                  {'  '}(current)
                </Text>
              )}
            </Box>
          );
        })}
        {endIndex < models.length && (
          <Box paddingX={1}>
            <Text color="gray" dimColor>↓ More below...</Text>
          </Box>
        )}
      </Box>

      {/* Footer */}
      <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
        <Text color="gray" dimColor wrap="truncate">
          ↑↓/j/k navigate · Enter select · Esc/q exit
        </Text>
      </Box>
    </Box>
  );
};
