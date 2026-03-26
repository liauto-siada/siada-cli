/**
 * ShellOutput Component
 * Displays shell command execution results
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { githubTheme } from '../Input/theme.js';
import Spinner from 'ink-spinner';
import { truncateByLines } from '../../utils/contentTruncator.js';

export interface ShellOutputProps {
  command: string;
  stdout?: string;
  stderr?: string;
  exitCode?: number | null;
  duration?: number;
  executing?: boolean;
  isBinary?: boolean;
  error?: string;
  /**
   * When true, render full stdout/stderr without truncation.
   * Used for staticGroups in MessageList where history should not be truncated.
   */
  disableTruncation?: boolean;
}

export const ShellOutput: React.FC<ShellOutputProps> = ({
  command,
  stdout = '',
  stderr = '',
  exitCode,
  duration,
  executing = false,
  isBinary = false,
  error,
  disableTruncation = false,
}) => {
  // Calculate dynamic max lines based on terminal height (same logic as Message.tsx)
  const terminalHeight = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.rows) || 24;
  const dynamicMaxLines = Math.max(terminalHeight / 2, 5);

  // Truncate stdout and stderr to prevent terminal overflow
  const stdoutResult = disableTruncation
    ? { content: stdout, hiddenLines: 0 }
    : truncateByLines(stdout, dynamicMaxLines, 'both');
  const stderrResult = disableTruncation
    ? { content: stderr, hiddenLines: 0 }
    : truncateByLines(stderr, dynamicMaxLines, 'both');

  // Format duration
  const formatDuration = (ms?: number): string => {
    if (!ms) return '';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  // Get exit code color
  const getExitCodeColor = (code?: number | null): string => {
    if (code === undefined || code === null) return githubTheme.text.secondary;
    return code === 0 ? githubTheme.success : githubTheme.danger;
  };

  return (
    <Box flexDirection="column" marginY={1}>
      {/* Command line */}
      <Box marginBottom={1}>
        <Text color={githubTheme.text.secondary}>$ </Text>
        <Text color={githubTheme.text.primary}>{command}</Text>
      </Box>

      {/* Executing indicator */}
      {executing && (
        <Box marginBottom={1}>
          <Text color={githubTheme.primary}>
            <Spinner type="dots" />
          </Text>
          <Text color={githubTheme.text.secondary}> Executing...</Text>
        </Box>
      )}

      {/* Binary output warning */}
      {isBinary && (
        <Box marginBottom={1}>
          <Text color={githubTheme.warning}>
            ⚠️  Binary output detected
          </Text>
        </Box>
      )}

      {/* Error message */}
      {error && (
        <Box marginBottom={1}>
          <Text color={githubTheme.danger}>Error: {error}</Text>
        </Box>
      )}

      {/* Stdout */}
      {stdout && (
        <Box flexDirection="column" marginBottom={1}>
          {stdoutResult.hiddenLines > 0 && (
            <Text color={githubTheme.warning} dimColor>
              ... {stdoutResult.hiddenLines} lines hidden ...
            </Text>
          )}
          <Text color={githubTheme.text.primary}>{stdoutResult.content}</Text>
        </Box>
      )}

      {/* Stderr */}
      {stderr && (
        <Box flexDirection="column" marginBottom={1}>
          {stderrResult.hiddenLines > 0 && (
            <Text color={githubTheme.warning} dimColor>
              ... {stderrResult.hiddenLines} lines hidden ...
            </Text>
          )}
          <Text color={githubTheme.danger}>{stderrResult.content}</Text>
        </Box>
      )}

      {/* Exit status */}
      {!executing && exitCode !== undefined && exitCode !== null && (
        <Box>
          <Text color={getExitCodeColor(exitCode)}>
            {exitCode === 0 ? '✓' : '✗'} Exit code: {exitCode}
          </Text>
          {duration !== undefined && duration !== null && (
            <Text color={githubTheme.text.secondary}>
              {' '}({formatDuration(duration)})
            </Text>
          )}
        </Box>
      )}
    </Box>
  );
};
