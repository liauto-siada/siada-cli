/**
 * Thinking Indicator Component
 * Displays animated spinner with rotating phrases and elapsed time
 * 
 * OPTIMIZED: Uses React.memo to prevent re-renders when props don't change
 */

import React, { useState, useEffect } from 'react';
import { Box, Text } from '@jrichman/ink';
import { ThinkingSpinner } from './ThinkingSpinner.js';
import { useThinkingPhrases } from '../../hooks/useThinkingPhrases.js';

export interface ThinkingIndicatorProps {
  /** Whether thinking indicator is active */
  active?: boolean;
  /** Custom phrases to rotate through */
  customPhrases?: string[];
  /** Whether to show elapsed time */
  showTime?: boolean;
}

/**
 * Thinking indicator with animated spinner, rotating phrases, and elapsed time
 * Wrapped with React.memo for performance optimization
 */
export const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = React.memo(({
  active = false,
  customPhrases,
  showTime = true,
}) => {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const currentPhrase = useThinkingPhrases({
    isActive: active,
    customPhrases,
  });

  // Track elapsed time
  useEffect(() => {
    if (!active) {
      setElapsedSeconds(0);
      return;
    }

    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, [active]);

  if (!active) {
    return null;
  }

  const formatTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}m ${secs}s`;
  };

  return (
    <Box flexDirection="row" gap={1}>
      <ThinkingSpinner active={active} />
      <Text color="cyan">{currentPhrase}</Text>
      {showTime && elapsedSeconds > 0 && (
        <Text color="gray" dimColor>
          ({formatTime(elapsedSeconds)})
        </Text>
      )}
    </Box>
  );
});
