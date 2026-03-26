/**
 * Search Box Component
 * Search input for filtering sessions
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { SearchBoxProps } from '../../types/session.js';

export const SearchBox: React.FC<SearchBoxProps> = ({ query, isActive }) => {
  if (!isActive && !query) {
    return null;
  }

  return (
    <Box
      borderStyle="round"
      borderColor={isActive ? 'cyan' : 'gray'}
      paddingX={1}
      marginBottom={1}
    >
      <Text color={isActive ? 'cyan' : 'gray'}>
        ⌕ {query}
        {isActive && <Text color="cyan">█</Text>}
      </Text>
    </Box>
  );
};
