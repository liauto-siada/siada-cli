/**
 * Model Selector Component
 * Displays a list of available models and allows the user to switch
 */

import React, { useState, useCallback } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';

export interface ModelSelectorProps {
  models: string[];
  currentModel: string;
  onSelect: (modelName: string) => void;
  onExit: () => void;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  currentModel,
  onSelect,
  onExit,
}) => {
  // Start selection on the current model if present, otherwise 0
  const initialIndex = Math.max(0, models.indexOf(currentModel));
  const [activeIndex, setActiveIndex] = useState(initialIndex);

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

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box flexDirection="column" marginBottom={1}>
        <Box borderStyle="single" borderColor="cyan" paddingX={1}>
          <Text bold color="cyan">Switch Model</Text>
        </Box>
        <Box paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>
            Current: <Text color="green">{currentModel}</Text>
            {'  '}·{'  '}
            {models.length} models available
          </Text>
        </Box>
      </Box>

      {/* Model list */}
      <Box flexDirection="column" paddingX={1}>
        {models.map((model, index) => {
          const isActive = index === activeIndex;
          const isCurrent = model === currentModel;

          return (
            <Box key={`${model}-${index}`} flexDirection="row">
              <Text color={isActive ? 'cyan' : 'white'}>
                {isActive ? '▶ ' : '  '}
              </Text>
              <Text
                color={isActive ? 'cyan' : isCurrent ? 'green' : 'white'}
                bold={isActive}
              >
                {model}
              </Text>
              {isCurrent && (
                <Text color="green" dimColor>
                  {'  '}(current)
                </Text>
              )}
            </Box>
          );
        })}
      </Box>

      {/* Footer */}
      <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
        <Text color="gray" dimColor>
          ↑↓/j/k navigate · Enter select · Esc/q exit
        </Text>
      </Box>
    </Box>
  );
};
