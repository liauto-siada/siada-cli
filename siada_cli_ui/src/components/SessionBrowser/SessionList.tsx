/**
 * Session List Component
 * Displays the list of sessions with pagination
 */

import React from 'react';
import { t } from '../../i18n/index.js';
import { PickerScrollHint } from '../Picker/Picker.js';
import { Box, Text } from '@jrichman/ink';
import { SessionListProps } from '../../types/session.js';
import { SessionItem } from './SessionItem.js';

export const SessionList: React.FC<SessionListProps> = ({
  sessions,
  activeIndex,
  scrollOffset,
  visibleCount,
  onSelect,
  showProjectName = false,
  maxSnippetRows,
}) => {
  if (sessions.length === 0) {
    return (
      <Box>
        <Text color="yellow">{t('没有匹配的会话。', 'No sessions found.')}</Text>
      </Box>
    );
  }

  // Calculate visible range
  const startIndex = scrollOffset;
  const endIndex = Math.min(startIndex + visibleCount, sessions.length);
  const visibleSessions = sessions.slice(startIndex, endIndex);

  return (
    <Box flexDirection="column">
      {/* Scroll indicators */}
      <PickerScrollHint visible={startIndex > 0} direction="up" />
      {visibleSessions.map((session, idx) => {
        const globalIndex = startIndex + idx;
        return (
          <SessionItem
            key={session.id}
            session={session}
            isActive={globalIndex === activeIndex}
            showMatchSnippets={!!session.matchSnippets && session.matchSnippets.length > 0}
            showProjectName={showProjectName}
            maxSnippetRows={maxSnippetRows}
          />
        );
      })}
      <PickerScrollHint visible={endIndex < sessions.length} direction="down" />
    </Box>
  );
};
