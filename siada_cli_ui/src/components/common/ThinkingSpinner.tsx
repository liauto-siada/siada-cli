/**
 * Thinking Spinner Component
 * Beautiful animated spinner using braille patterns with color cycling
 * Inspired by siada-agenthub's spinner.py
 */

import React, { useState, useEffect } from 'react';
import { Text } from '@jrichman/ink';

// Unicode braille patterns for smooth animation
const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

// Color cycle for beautiful visual effect
const COLORS = ['cyan', 'blueBright', 'magentaBright'] as const;

export interface ThinkingSpinnerProps {
  /** Whether the spinner is active */
  active?: boolean;
  /** Animation speed in milliseconds */
  interval?: number;
}

/**
 * Animated spinner component with braille patterns and color cycling
 */
export const ThinkingSpinner: React.FC<ThinkingSpinnerProps> = ({
  active = true,
  interval = 200, // Increased from 100ms to 200ms to reduce refresh rate
}) => {
  const [frameIndex, setFrameIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      return;
    }

    const timer = setInterval(() => {
      setFrameIndex((prev) => (prev + 1) % SPINNER_FRAMES.length);
    }, interval);

    return () => {
      clearInterval(timer);
    };
  }, [active, interval]);

  if (!active) {
    return null;
  }

  const frame = SPINNER_FRAMES[frameIndex];
  const color = COLORS[frameIndex % COLORS.length];

  return (
    <Text color={color} bold>
      {frame}
    </Text>
  );
};
