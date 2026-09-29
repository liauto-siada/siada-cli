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
import { THINKING_STEPS, ThinkingStep, SHORTCUT_TIPS, TIP_CHANGE_INTERVAL } from '../../constants/phrases.js';

export interface ThinkingIndicatorProps {
  /** Whether thinking indicator is active */
  active?: boolean;
  /** Custom phrases to rotate through */
  customPhrases?: string[];
  /** Whether to show elapsed time */
  showTime?: boolean;
  /** Current agent activity step — when set, the step phrase (e.g.
   * Executing tools...) replaces the rotating generic phrases. */
  step?: ThinkingStep | null;
}

/**
 * Thinking indicator with animated spinner, rotating phrases, and elapsed time
 * Wrapped with React.memo for performance optimization
 */
export const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = React.memo(({
  active = false,
  customPhrases,
  showTime = true,
  step = null,
}) => {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [tipIndex, setTipIndex] = useState(
    () => Math.floor(Math.random() * SHORTCUT_TIPS.length),
  );

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

  // Rotate through shortcut tips (one entry per shortcut) while active
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      setTipIndex((prev) => (prev + 1) % SHORTCUT_TIPS.length);
    }, TIP_CHANGE_INTERVAL);
    return () => clearInterval(timer);
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

  // A known activity step (model reasoning / tool execution / system
  // processing / compaction) is more informative than the rotating phrases.
  const displayPhrase = step ? THINKING_STEPS[step].phrase : currentPhrase;

  // Shortcut tip shown after the step phrase: "(tips: Ctrl+O toggles ...)"
  const tipText = SHORTCUT_TIPS[tipIndex % SHORTCUT_TIPS.length].replace(/^Tip:\s*/, '');

  return (
    <Box flexDirection="row" gap={1}>
      <ThinkingSpinner active={active} />
      <Text color="cyan">{displayPhrase}</Text>
      <Text color="gray">(tips: {tipText})</Text>
      {showTime && elapsedSeconds > 0 && (
        <Text color="gray">
          ({formatTime(elapsedSeconds)})
        </Text>
      )}
    </Box>
  );
});
