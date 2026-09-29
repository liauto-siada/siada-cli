/**
 * Session Browser Footer Component
 * Displays keyboard shortcuts help
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { SessionBrowserFooterProps } from '../../types/session.js';

export const SessionBrowserFooter: React.FC<SessionBrowserFooterProps> = ({
  isSearchMode,
  hasResults,
  scope,
}) => {
  // wrap="truncate" keeps the footer at exactly 4 rows (margin 1 + border 3)
  // even on narrow terminals — the SessionBrowser row budget relies on this.
  if (isSearchMode) {
    return (
      <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
        <Text color="gray" dimColor wrap="truncate">
          Type to search · Enter to confirm · Esc to cancel
        </Text>
      </Box>
    );
  }

  if (!hasResults) {
    return (
      <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
        <Text color="gray" dimColor wrap="truncate">
          Ctrl+A {scope === 'current' ? 'all projects' : 'current only'} · Esc to exit
        </Text>
      </Box>
    );
  }

  const scopeHint = scope === 'current' ? 'all projects' : 'current only';

  return (
    <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
      <Text color="gray" dimColor wrap="truncate">
        ↑↓/j/k navigate · Enter resume · Ctrl+R rename · s sort · Ctrl+A {scopeHint} · / search · Esc exit
      </Text>
    </Box>
  );
};
