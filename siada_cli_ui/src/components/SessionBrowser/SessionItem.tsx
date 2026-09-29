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
  // Collapse newlines (and runs of whitespace) in the message: a raw
  // firstUserMessage can span multiple lines, which would make the item
  // render 3+ rows and silently break the SessionBrowser row budget —
  // the frame then exceeds the terminal and the top of the list (header
  // and active item) is scrolled out of view.
  const rawMessage = session.displayName || session.firstUserMessage;
  const displayMessage = truncateText(
    rawMessage.replace(/[\n\r]+/g, ' ').replace(/\s+/g, ' ').trim(),
    60
  );

  // Indicator for current/active session
  const indicator = session.isCurrentSession ? '●' : (isActive ? '❯' : ' ');
  
  const messageDisplay = showProjectName && session.projectName 
    ? `[${session.projectName}] ${displayMessage}`
    : displayMessage;
  
  // Every line uses wrap="truncate" so an item always renders exactly 2 rows
  // (plus one row per snippet) — the SessionBrowser row budget relies on this.
  return (
    <Box flexDirection="column" paddingLeft={1}>
      <Box>
        <Text color={isActive ? 'cyan' : 'white'} bold={isActive} wrap="truncate">
          {indicator} {messageDisplay}
        </Text>
      </Box>
      <Box paddingLeft={2}>
        <Text color="gray" dimColor wrap="truncate">
          {timeAgo} · {session.messageCount} messages
          {session.matchCount && session.matchCount > 0 ? ` · ${session.matchCount} matches` : ''}
        </Text>
      </Box>
      {showMatchSnippets && session.matchSnippets && session.matchSnippets.length > 0 && (
        <Box paddingLeft={2} flexDirection="column">
          {session.matchSnippets.map((snippet, idx) => (
            <Text key={idx} color="yellow" dimColor wrap="truncate">
              → {truncateText(snippet, 70)}
            </Text>
          ))}
        </Box>
      )}
    </Box>
  );
};
