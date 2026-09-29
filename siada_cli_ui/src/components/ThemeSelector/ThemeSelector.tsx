/**
 * Theme Selector Component
 * Displays available UI color themes and allows the user to switch.
 * Mirrors ModelSelector: ↑↓/j/k navigate, Enter select, Esc/q exit.
 */

import React, { useState, useCallback } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';

export interface ThemeSelectorProps {
  themes: string[];
  current: string;
  onSelect: (theme: string) => void;
  onExit: () => void;
}

const THEME_NOTES: Record<string, string> = {
  auto: 'Follow terminal/system background (default)',
  dark: 'GitHub Dark',
  light: 'GitHub Light',
};

export const ThemeSelector: React.FC<ThemeSelectorProps> = ({
  themes,
  current,
  onSelect,
  onExit,
}) => {
  const initialIndex = Math.max(0, themes.indexOf(current));
  const [activeIndex, setActiveIndex] = useState(initialIndex);

  const moveSelection = useCallback((delta: number) => {
    setActiveIndex(prev => {
      const next = prev + delta;
      if (next < 0) return 0;
      if (next >= themes.length) return themes.length - 1;
      return next;
    });
  }, [themes.length]);

  useKeypress((key) => {
    if (key.name === 'up' || key.sequence === 'k') {
      moveSelection(-1);
    } else if (key.name === 'down' || key.sequence === 'j') {
      moveSelection(1);
    } else if (key.name === 'return') {
      const selected = themes[activeIndex];
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

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box flexDirection="column" marginBottom={1}>
        <Box borderStyle="single" borderColor="cyan" paddingX={1}>
          <Text bold color="cyan">Switch Theme</Text>
        </Box>
        <Box paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>
            Current: <Text color="green">{current}</Text>
          </Text>
        </Box>
      </Box>

      {/* Theme list */}
      <Box flexDirection="column" paddingX={1}>
        {themes.map((themeName, index) => {
          const isActive = index === activeIndex;
          const isCurrent = themeName === current;
          const note = THEME_NOTES[themeName] ?? '';

          return (
            <Box key={themeName} flexDirection="row">
              <Text color={isActive ? 'cyan' : 'white'}>
                {isActive ? '▶ ' : '  '}
              </Text>
              <Text
                color={isActive ? 'cyan' : isCurrent ? 'green' : 'white'}
                bold={isActive}
              >
                {themeName}
              </Text>
              {note && (
                <Text color={isActive ? 'cyan' : isCurrent ? 'green' : 'white'}>
                  {'  '}({note})
                </Text>
              )}
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
