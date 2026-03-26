/**
 * Session Browser Header Component
 * Displays title and summary information
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { SessionBrowserHeaderProps } from '../../types/session.js';

export const SessionBrowserHeader: React.FC<SessionBrowserHeaderProps> = ({
  totalCount,
  filteredCount,
  currentPage,
  totalPages,
  sortOrder,
  sortReverse,
  scope,
  projectName,
}) => {
  const sortLabel = {
    date: 'Date',
    messages: 'Messages',
    name: 'Name',
  }[sortOrder];

  const sortIcon = sortReverse ? '↓' : '↑';
  
  const scopeLabel = scope === 'all' 
    ? 'All Projects' 
    : projectName 
      ? `Current Project: ${projectName}` 
      : 'Current Project';

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box borderStyle="single" borderColor="cyan" paddingX={1}>
        <Text bold color="cyan">
          Resume Session ({scopeLabel})
        </Text>
      </Box>
      <Box paddingX={1} marginTop={1}>
        <Text color="gray" dimColor>
          Showing {filteredCount} of {totalCount} sessions · Page {currentPage}/{totalPages} · Sort: {sortLabel} {sortIcon}
        </Text>
      </Box>
    </Box>
  );
};
