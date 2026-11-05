/**
 * Rename Box Component
 * Input box for renaming a session
 */

import React from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';
import { RenameBoxProps } from '../../types/session.js';

export const RenameBox: React.FC<RenameBoxProps> = ({ value, isActive }) => {
  useUiLanguage();
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
      <Text color="yellow">{t('✎ 重命名：', '✎ Rename: ')}</Text>
      <Text color="white" wrap="truncate">{value}</Text>
      <Text color="yellow">█</Text>
      <Text color="gray" dimColor>{PANEL_TIPS.rename}</Text>
    </Box>
  );
};
