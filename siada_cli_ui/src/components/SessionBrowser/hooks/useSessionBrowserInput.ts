/**
 * Session Browser Input Hook
 * Handles keyboard input for session browser
 */

import { useEffect } from 'react';
import { useKeypress, type Key } from '../../../hooks/useKeypress.js';
import { SessionBrowserState } from '../../../types/session.js';

export interface UseSessionBrowserInputOptions {
  state: SessionBrowserState;
  moveSelection: (delta: number) => void;
  handleSearchInput: (char: string) => void;
  toggleSearchMode: () => void;
  cycleSortOrder: () => void;
  toggleScope: () => void;
  resumeSession: () => Promise<void>;
  dismissRedirect: () => void;
  startRename: () => void;
  handleRenameInput: (char: string) => void;
  confirmRename: () => Promise<void>;
  cancelRename: () => void;
  onExit: () => void;
}

export function useSessionBrowserInput({
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
}: UseSessionBrowserInputOptions) {
  useKeypress((key: Key) => {
    // Redirect panel mode: any key dismisses the panel
    if (state.redirectCmd) {
      dismissRedirect();
      return;
    }

    // Rename mode takes priority
    if (state.isRenameMode) {
      if (key.name === 'escape' || (key.ctrl && key.name === 'c')) {
        cancelRename();
      } else if (key.name === 'return') {
        confirmRename();
      } else if (key.name === 'backspace' || key.name === 'delete') {
        handleRenameInput('\x7f');
      } else if (key.insertable && !key.ctrl && !key.cmd) {
        handleRenameInput(key.sequence);
      }
      return;
    }

    // Search mode
    if (state.isSearchMode) {
      if (key.name === 'escape' || (key.ctrl && key.name === 'c')) {
        // Exit search mode and clear query
        toggleSearchMode();
        handleSearchInput(''); // Clear by setting empty
      } else if (key.name === 'return') {
        // Confirm search
        toggleSearchMode();
      } else if (key.name === 'backspace' || key.name === 'delete') {
        // Delete last character
        handleSearchInput('\x7f');
      } else if (key.insertable && !key.ctrl && !key.cmd) {
        // Add character to search
        handleSearchInput(key.sequence);
      }
      return;
    }

    // Navigation mode
    if (key.name === 'up' || key.sequence === 'k') {
      moveSelection(-1);
    } else if (key.name === 'down' || key.sequence === 'j') {
      moveSelection(1);
    } else if (key.name === 'return') {
      // Resume selected session
      resumeSession();
    } else if (key.sequence === 's' || key.sequence === 'S') {
      // Cycle sort order
      cycleSortOrder();
    } else if (key.ctrl && key.name === 'a') {
      // Toggle scope (Ctrl+A)
      toggleScope();
    } else if (key.ctrl && key.name === 'r') {
      // Enter rename mode (Ctrl+R)
      startRename();
    } else if (key.sequence === '/') {
      // Enter search mode
      toggleSearchMode();
    } else if (key.name === 'escape' || (key.ctrl && key.name === 'c')) {
      // Exit
      onExit();
    } else if (key.name === 'pageup') {
      // Page up
      moveSelection(-10);
    } else if (key.name === 'pagedown') {
      // Page down
      moveSelection(10);
    }
  });
}
