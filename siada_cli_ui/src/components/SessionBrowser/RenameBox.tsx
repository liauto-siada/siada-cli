/**
 * Rename Box Component
 * Input box for renaming a session
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { RenameBoxProps } from '../../types/session.js';

export const RenameBox: React.FC<RenameBoxProps> = ({ value, isActive }) => {
  if (!isActive) {
    return null;
  }

  return (
    <Box
      borderStyle="round"
      borderColor="yellow"
      paddingX={1}
      marginBottom={1}
    >
      <Text color="yellow">✎ Rename: </Text>
      <Text color="white">{value}</Text>
      <Text color="yellow">█</Text>
      <Text color="gray" dimColor>  Enter to confirm · Esc to cancel</Text>
    </Box>
  );
};
