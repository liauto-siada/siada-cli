/**
 * Session Item Component
 * Displays a single session in the browser list
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { SessionItemProps } from '../../types/session.js';
import { formatTimeAgo, truncateText } from '../../utils/sessionUtils.js';

export const SessionItem: React.FC<SessionItemProps> = ({
  session,
  isActive,
  showMatchSnippets = false,
  showProjectName = false,
}) => {
  const timeAgo = formatTimeAgo(session.lastUpdated);
  const displayMessage = truncateText(session.displayName || session.firstUserMessage, 60);

  // Indicator for current/active session
  const indicator = session.isCurrentSession ? '●' : (isActive ? '❯' : ' ');
  
  const messageDisplay = showProjectName && session.projectName 
    ? `[${session.projectName}] ${displayMessage}`
    : displayMessage;
  
  return (
    <Box flexDirection="column" paddingLeft={1}>
      <Box>
        <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>
          {indicator} {messageDisplay}
        </Text>
      </Box>
      <Box paddingLeft={2}>
        <Text color="gray" dimColor>
          {timeAgo} · {session.messageCount} messages
          {session.matchCount && session.matchCount > 0 ? ` · ${session.matchCount} matches` : ''}
        </Text>
      </Box>
      {showMatchSnippets && session.matchSnippets && session.matchSnippets.length > 0 && (
        <Box paddingLeft={2} flexDirection="column">
          {session.matchSnippets.map((snippet, idx) => (
            <Text key={idx} color="yellow" dimColor>
              → {truncateText(snippet, 70)}
            </Text>
          ))}
        </Box>
      )}
    </Box>
  );
};
