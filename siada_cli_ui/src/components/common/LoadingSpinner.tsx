/**
 * LoadingSpinner Component
 * 
 * Displays a loading spinner for async operations (e.g., Slash commands)
 * Can be controlled to show/hide based on task state
 */

import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';

export interface LoadingSpinnerProps {
  /** Text to display next to the spinner */
  text: string;
  /** Whether the spinner is active/visible */
  isActive: boolean;
  /** Optional color for the spinner (default: cyan) */
  color?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ 
  text, 
  isActive,
  color = 'cyan'
}) => {
  if (!isActive) {
    return null;
  }
  
  return (
    <Box>
      <Text color={color}>
        <Spinner type="dots" />
      </Text>
      <Text> {text}</Text>
    </Box>
  );
};

export default LoadingSpinner;
