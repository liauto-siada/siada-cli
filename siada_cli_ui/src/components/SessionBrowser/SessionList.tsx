/**
 * Session List Component
 * Displays the list of sessions with pagination
 */

import React from 'react';
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
}) => {
  if (sessions.length === 0) {
    return (
      <Box paddingX={1} marginY={2}>
        <Text color="yellow">No sessions found.</Text>
      </Box>
    );
  }

  // Calculate visible range
  const startIndex = scrollOffset;
  const endIndex = Math.min(startIndex + visibleCount, sessions.length);
  const visibleSessions = sessions.slice(startIndex, endIndex);

  return (
    <Box flexDirection="column" paddingX={1}>
      {visibleSessions.map((session, idx) => {
        const globalIndex = startIndex + idx;
        return (
          <SessionItem
            key={session.id}
            session={session}
            isActive={globalIndex === activeIndex}
            showMatchSnippets={!!session.matchSnippets && session.matchSnippets.length > 0}
            showProjectName={showProjectName}
          />
        );
      })}
      
      {/* Scroll indicators */}
      {startIndex > 0 && (
        <Box paddingX={1}>
          <Text color="gray" dimColor>↑ More above...</Text>
        </Box>
      )}
      {endIndex < sessions.length && (
        <Box paddingX={1}>
          <Text color="gray" dimColor>↓ More below...</Text>
        </Box>
      )}
    </Box>
  );
};
