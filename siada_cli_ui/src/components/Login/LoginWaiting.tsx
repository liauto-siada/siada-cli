/**
 * LoginWaiting Component
 * Shown while the backend polls for a device-code token.
 * Displays the verification URL and a spinner.
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import Spinner from 'ink-spinner';

export interface LoginWaitingProps {
  url: string;
  openBrowser: boolean;
}

export const LoginWaiting: React.FC<LoginWaitingProps> = ({ url, openBrowser }) => {
  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
        <Text bold color="cyan">Authenticating</Text>
      </Box>

      <Box flexDirection="column" paddingX={1}>
        {openBrowser ? (
          <Box marginBottom={1}>
            <Text>Browser opened. If it did not open automatically, visit:</Text>
          </Box>
        ) : (
          <Box marginBottom={1}>
            <Text>Visit the following URL on any device to authenticate:</Text>
          </Box>
        )}

        {/* URL */}
        <Box marginBottom={1} paddingX={1}>
          <Text color="cyan" bold>{url}</Text>
        </Box>

        {/* Spinner */}
        <Box>
          <Text color="yellow"><Spinner type="dots" /></Text>
          <Text> Waiting for authentication...</Text>
        </Box>

        <Box marginTop={1}>
          <Text dimColor>Press Ctrl+C to cancel</Text>
        </Box>
      </Box>
    </Box>
  );
};
