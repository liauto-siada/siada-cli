import React from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';
import { ConversationViewport } from '../Chat/ConversationViewport.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { colors } from '../../utils/colors.js';
import type { Message } from '../../types/index.js';

export function DemoRecordDetail({ title, summary, messages, width, rows, onClose }: {
  title: string; summary?: string; messages: Message[]; width: number; rows: number; onClose: () => void;
}) {
  useUiLanguage();
  useKeypress(key => { if (key.name === 'escape' || key.ctrl && key.name === 'c') onClose(); });
  return <Box height={rows - 1} width={width} flexDirection="column">
    <Box paddingX={1} height={1} flexShrink={0}><Text bold wrap="truncate-end">{title}</Text></Box>
    <Box paddingX={1} height={1} flexShrink={0}>
      <Text color={colors.content.secondary} wrap="truncate-end">{summary || t('暂无记录', 'No records yet')}{PANEL_TIPS.recordReturn}</Text>
    </Box>
    <ConversationViewport messages={messages} width={width} height={Math.max(1, rows - 3)}
      isCollapsed presentation />
  </Box>;
}