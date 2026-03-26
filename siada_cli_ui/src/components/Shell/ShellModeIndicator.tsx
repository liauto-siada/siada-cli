/**
 * Shell Mode Indicator Component
 * Displays shell mode status message
 */

import React from 'react';
import { Box, Text } from 'ink';
import { githubTheme } from '../Input/theme.js';

export interface ShellModeIndicatorProps {
  /** Whether shell mode is active */
  active: boolean;
  
  /** Current working directory */
  cwd?: string;
}

/**
 * Shell Mode Indicator
 * Shows "shell mode enabled (esc to disable)" message
 */
export const ShellModeIndicator: React.FC<ShellModeIndicatorProps> = ({ active, cwd }) => {
  if (!active) {
    return null;
  }

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        <Text color={githubTheme.success} bold>
          ⚡ Shell Mode Enabled
        </Text>
        <Text color={githubTheme.text.secondary} dimColor>
          {' '}(press ESC to disable)
        </Text>
      </Box>
      {cwd && (
        <Box marginTop={0}>
          <Text color={githubTheme.text.secondary} dimColor>
            Working directory: {cwd}
          </Text>
        </Box>
      )}
    </Box>
  );
};
