/**
 * Session Browser Component
 * Main component for browsing and resuming sessions
 */

import React, { useMemo } from 'react';
import { Box, Text } from '@jrichman/ink';
import Spinner from 'ink-spinner';
import { SessionBrowserProps } from '../../types/session.js';
import { useSessionBrowser } from './hooks/useSessionBrowser.js';
import { useSessionBrowserInput } from './hooks/useSessionBrowserInput.js';
import { SessionBrowserHeader } from './SessionBrowserHeader.js';
import { SessionBrowserFooter } from './SessionBrowserFooter.js';
import { SearchBox } from './SearchBox.js';
import { RenameBox } from './RenameBox.js';
import { SessionList } from './SessionList.js';
import { calculateVisibleRange } from '../../utils/sessionUtils.js';

export const SessionBrowser: React.FC<SessionBrowserProps> = ({
  projectRoot,
  onResume,
  onExit,
  currentSessionId,
}) => {
  const {
    state,
    moveSelection,
    handleSearchInput,
    toggleSearchMode,
    cycleSortOrder,
    toggleScope,
    resumeSession,
    dismissRedirect,
    startRename,
    handleRenameInput,
    confirmRename,
    cancelRename,
  } = useSessionBrowser({
    projectRoot,
    currentSessionId,
    onResume,
  });

  // Handle keyboard input
  useSessionBrowserInput({
    state,
    moveSelection,
    handleSearchInput,
    toggleSearchMode,
    cycleSortOrder,
    toggleScope,
    resumeSession,
    dismissRedirect,
    startRename,
    handleRenameInput,
    confirmRename,
    cancelRename,
    onExit,
  });

  // Calculate visible range for pagination (must be before conditional returns)
  const { startIndex, endIndex } = useMemo(() => {
    const visibleCount = Math.max(5, state.terminalHeight - 10); // Reserve space for header/footer
    return calculateVisibleRange(
      state.filteredSessions.length,
      state.activeIndex,
      visibleCount
    );
  }, [state.filteredSessions.length, state.activeIndex, state.terminalHeight]);

  // Derive project name from first session or projectRoot
  // Must be before conditional returns to maintain hook order
  const projectName = useMemo(() => {
    if (state.scope === 'current' && state.sessions.length > 0 && state.sessions[0].projectName) {
      return state.sessions[0].projectName;
    }
    // Fallback to extracting from projectRoot
    const parts = projectRoot.split('/');
    return parts[parts.length - 1] || 'Unknown';
  }, [state.scope, state.sessions, projectRoot]);

  const visibleCount = endIndex - startIndex;
  const currentPage = Math.floor(state.activeIndex / visibleCount) + 1;
  const totalPages = Math.ceil(state.filteredSessions.length / visibleCount);

  // Loading state
  if (state.loading) {
    return (
      <Box flexDirection="column" paddingX={1}>
        <Box marginBottom={1}>
          <Text color="cyan">
            <Spinner type="dots" />
          </Text>
          <Text> Loading sessions...</Text>
        </Box>
      </Box>
    );
  }

  // Error state
  if (state.error) {
    return (
      <Box flexDirection="column" paddingX={1}>
        <Box marginBottom={1} borderStyle="single" borderColor="red" paddingX={1}>
          <Text color="red" bold>Error</Text>
        </Box>
        <Box paddingX={1}>
          <Text color="red">{state.error}</Text>
        </Box>
        <Box marginTop={1} paddingX={1}>
          <Text color="gray" dimColor>Press Esc or q to close</Text>
        </Box>
      </Box>
    );
  }

  // Empty state
  if (state.sessions.length === 0) {
    return (
      <Box flexDirection="column" paddingX={1}>
        <Box marginBottom={1} borderStyle="single" borderColor="yellow" paddingX={1}>
          <Text color="yellow" bold>No Sessions Found</Text>
        </Box>
        <Box paddingX={1}>
          <Text>No saved sessions available.</Text>
        </Box>
        <Box marginTop={1} paddingX={1}>
          <Text color="gray" dimColor>Press Esc or q to close</Text>
        </Box>
      </Box>
    );
  }

  // Main view
  return (
    <Box flexDirection="column">
      <SessionBrowserHeader
        totalCount={state.sessions.length}
        filteredCount={state.filteredSessions.length}
        currentPage={currentPage}
        totalPages={totalPages}
        sortOrder={state.sortOrder}
        sortReverse={state.sortReverse}
        scope={state.scope}
        projectName={projectName}
      />

      <SearchBox
        query={state.searchQuery}
        isActive={state.isSearchMode}
      />

      <RenameBox
        value={state.renameInput}
        isActive={state.isRenameMode}
      />

      <SessionList
        sessions={state.filteredSessions}
        activeIndex={state.activeIndex}
        scrollOffset={startIndex}
        visibleCount={visibleCount}
        onSelect={resumeSession}
        showProjectName={state.scope === 'all'}
      />

      {state.redirectCmd && (
        <Box
          borderStyle="single"
          borderColor="yellow"
          flexDirection="column"
          paddingX={1}
          marginTop={1}
        >
          <Text color="yellow" bold>Session Workspace Mismatch</Text>
          <Text>This session belongs to a different workspace. To resume it, run:</Text>
          <Text color="cyan">  {state.redirectCmd}</Text>
          <Text color="gray" dimColor>Press any key to dismiss</Text>
        </Box>
      )}

      <SessionBrowserFooter
        isSearchMode={state.isSearchMode}
        hasResults={state.filteredSessions.length > 0}
        scope={state.scope}
      />
    </Box>
  );
};
