/**
 * Session Browser Hook
 * Main hook for session browser functionality
 */

import { useEffect, useCallback } from 'react';
import { useSessionBrowserState } from './useSessionBrowserState.js';
import { SessionInfo } from '../../../types/session.js';
import { logger } from '../../../utils/logger.js';
import { loadSessions, renameSession } from '../../../services/sessionLoader.js';

export interface UseSessionBrowserOptions {
  projectRoot: string;
  currentSessionId?: string;
  onResume: (sessionId: string) => Promise<void>;
  acpClient?: any; // ACP client for communication
}

export function useSessionBrowser({
  projectRoot,
  currentSessionId,
  onResume,
  acpClient,
}: UseSessionBrowserOptions) {
  const [state, dispatch] = useSessionBrowserState();

  // Load sessions from filesystem
  const loadSessionsData = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'SET_ERROR', payload: null });

    try {
      logger.info('Loading sessions', { projectRoot, scope: state.scope });

      // Load sessions directly from filesystem
      const sessions: SessionInfo[] = loadSessions(
        state.scope,
        projectRoot,
        currentSessionId
      );

      dispatch({ type: 'SET_SESSIONS', payload: sessions });
      
      logger.info('Sessions loaded successfully', { count: sessions.length });
    } catch (error) {
      logger.error('Failed to load sessions', { error });
      dispatch({ 
        type: 'SET_ERROR', 
        payload: error instanceof Error ? error.message : 'Unknown error'
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }, [projectRoot, currentSessionId, state.scope]);

  // Load sessions on mount and when scope changes
  useEffect(() => {
    loadSessionsData();
  }, [loadSessionsData]);

  // Move selection up/down
  const moveSelection = useCallback((delta: number) => {
    const newIndex = state.activeIndex + delta;
    dispatch({ type: 'SET_ACTIVE_INDEX', payload: newIndex });
  }, [state.activeIndex]);

  // Handle search input — dispatch delta only, reducer owns concatenation (no stale closure)
  const handleSearchInput = useCallback((char: string) => {
    if (char === '\x7f' || char === '\b') {
      dispatch({ type: 'BACKSPACE_SEARCH' });
    } else if (char === '') {
      dispatch({ type: 'SET_SEARCH_QUERY', payload: '' });
    } else {
      dispatch({ type: 'APPEND_TO_SEARCH', payload: char });
    }
  }, []);

  // Toggle search mode
  const toggleSearchMode = useCallback(() => {
    dispatch({ type: 'TOGGLE_SEARCH_MODE' });
  }, []);

  // Cycle sort order
  const cycleSortOrder = useCallback(() => {
    dispatch({ type: 'CYCLE_SORT_ORDER' });
  }, []);

  // Toggle scope between current and all
  const toggleScope = useCallback(() => {
    dispatch({ type: 'TOGGLE_SCOPE' });
    // Reload sessions after scope change
    setTimeout(() => {
      loadSessionsData();
    }, 0);
  }, [loadSessionsData]);

  // Resume selected session
  const resumeSession = useCallback(async () => {
    const session = state.filteredSessions[state.activeIndex];
    if (!session) {
      logger.warn('No session selected');
      return;
    }

    // Detect cross-workspace session: block resume and show migration instruction
    const originRoot = session.projectRoot;
    if (originRoot && originRoot !== 'Unknown' && originRoot !== projectRoot) {
      const cmd = `cd ${originRoot} && siada-cli --resume ${session.sessionId}`;
      logger.info('Cross-workspace session detected', { originRoot, projectRoot, sessionId: session.sessionId });
      dispatch({ type: 'SET_REDIRECT_CMD', payload: cmd });
      return;
    }

    try {
      logger.info('Resuming session', { sessionId: session.sessionId });
      await onResume(session.sessionId);
    } catch (error) {
      logger.error('Failed to resume session', { error });
      dispatch({ 
        type: 'SET_ERROR', 
        payload: error instanceof Error ? error.message : 'Failed to resume session'
      });
    }
  }, [state.filteredSessions, state.activeIndex, projectRoot, onResume]);

  // Dismiss cross-workspace redirect panel
  const dismissRedirect = useCallback(() => {
    dispatch({ type: 'SET_REDIRECT_CMD', payload: null });
  }, []);

  // Delete session
  const deleteSession = useCallback(async () => {
    const session = state.filteredSessions[state.activeIndex];
    if (!session) {
      return;
    }

    try {
      logger.info('Deleting session', { sessionId: session.sessionId });
      
      if (acpClient) {
        await acpClient.send({
          type: 'delete_session',
          sessionId: session.sessionId,
          projectRoot,
        });
      }

      // Reload sessions
      await loadSessionsData();
    } catch (error) {
      logger.error('Failed to delete session', { error });
      dispatch({ 
        type: 'SET_ERROR', 
        payload: error instanceof Error ? error.message : 'Failed to delete session'
      });
    }
  }, [state.filteredSessions, state.activeIndex, acpClient, projectRoot, loadSessionsData]);

  // Enter rename mode for the selected session
  const startRename = useCallback(() => {
    const session = state.filteredSessions[state.activeIndex];
    if (!session) return;
    const currentName = session.displayName || session.firstUserMessage || '';
    dispatch({ type: 'ENTER_RENAME_MODE', payload: currentName });
  }, [state.filteredSessions, state.activeIndex]);

  // Update rename input — dispatch delta only, reducer owns concatenation (no stale closure)
  const handleRenameInput = useCallback((char: string) => {
    if (char === '\x7f' || char === '\b') {
      dispatch({ type: 'BACKSPACE_RENAME' });
    } else {
      dispatch({ type: 'APPEND_TO_RENAME', payload: char });
    }
  }, []);

  // Confirm rename
  const confirmRename = useCallback(async () => {
    const session = state.filteredSessions[state.activeIndex];
    if (!session) {
      dispatch({ type: 'EXIT_RENAME_MODE' });
      return;
    }

    const newName = state.renameInput.trim();
    const sessionProjectRoot = session.projectRoot && session.projectRoot !== 'Unknown'
      ? session.projectRoot
      : projectRoot;

    try {
      logger.info('Renaming session', { sessionId: session.sessionId, newName });
      renameSession(session.sessionId, sessionProjectRoot, newName);
      dispatch({ type: 'EXIT_RENAME_MODE' });
      await loadSessionsData();
    } catch (error) {
      logger.error('Failed to rename session', { error });
      dispatch({ type: 'EXIT_RENAME_MODE' });
      dispatch({
        type: 'SET_ERROR',
        payload: error instanceof Error ? error.message : 'Failed to rename session',
      });
    }
  }, [state.filteredSessions, state.activeIndex, state.renameInput, projectRoot, loadSessionsData]);

  // Cancel rename
  const cancelRename = useCallback(() => {
    dispatch({ type: 'EXIT_RENAME_MODE' });
  }, []);

  return {
    state,
    dispatch,
    loadSessionsData,
    moveSelection,
    handleSearchInput,
    toggleSearchMode,
    cycleSortOrder,
    toggleScope,
    resumeSession,
    dismissRedirect,
    deleteSession,
    startRename,
    handleRenameInput,
    confirmRename,
    cancelRename,
  };
}
