/**
 * Session Browser State Hook
 * Manages the state for session browser using reducer pattern
 */

import { useReducer, Reducer } from 'react';
import { SessionBrowserState, SessionAction, SessionInfo } from '../../../types/session.js';
import { sortSessions, filterSessions } from '../../../utils/sessionUtils.js';

const initialState: SessionBrowserState = {
  sessions: [],
  filteredSessions: [],
  activeIndex: 0,
  searchQuery: '',
  isSearchMode: false,
  sortOrder: 'date',
  sortReverse: false,
  loading: true,
  error: null,
  scrollOffset: 0,
  terminalHeight: 20,
  scope: 'current',
  isRenameMode: false,
  renameInput: '',
  redirectCmd: null,
};

const sessionBrowserReducer: Reducer<SessionBrowserState, SessionAction> = (
  state,
  action
) => {
  switch (action.type) {
    case 'SET_SESSIONS': {
      const sessions = action.payload;
      const sorted = sortSessions(sessions, state.sortOrder, state.sortReverse);
      const filtered = filterSessions(sorted, state.searchQuery);
      return {
        ...state,
        sessions,
        filteredSessions: filtered,
        activeIndex: Math.min(state.activeIndex, filtered.length - 1),
      };
    }

    case 'SET_FILTERED_SESSIONS':
      return {
        ...state,
        filteredSessions: action.payload,
        activeIndex: Math.min(state.activeIndex, action.payload.length - 1),
      };

    case 'SET_ACTIVE_INDEX':
      return {
        ...state,
        activeIndex: Math.max(0, Math.min(action.payload, state.filteredSessions.length - 1)),
      };

    case 'SET_SEARCH_QUERY': {
      const query = action.payload;
      const sorted = sortSessions(state.sessions, state.sortOrder, state.sortReverse);
      const filtered = filterSessions(sorted, query);
      return {
        ...state,
        searchQuery: query,
        filteredSessions: filtered,
        activeIndex: 0, // Reset to top when searching
      };
    }

    case 'TOGGLE_SEARCH_MODE':
      return {
        ...state,
        isSearchMode: !state.isSearchMode,
      };

    case 'CYCLE_SORT_ORDER': {
      const orders: Array<'date' | 'messages' | 'name'> = ['date', 'messages', 'name'];
      const currentIndex = orders.indexOf(state.sortOrder);
      const nextOrder = orders[(currentIndex + 1) % orders.length];
      const sorted = sortSessions(state.sessions, nextOrder, state.sortReverse);
      const filtered = filterSessions(sorted, state.searchQuery);
      return {
        ...state,
        sortOrder: nextOrder,
        filteredSessions: filtered,
      };
    }

    case 'TOGGLE_SORT_REVERSE': {
      const sorted = sortSessions(state.sessions, state.sortOrder, !state.sortReverse);
      const filtered = filterSessions(sorted, state.searchQuery);
      return {
        ...state,
        sortReverse: !state.sortReverse,
        filteredSessions: filtered,
      };
    }

    case 'SET_LOADING':
      return {
        ...state,
        loading: action.payload,
      };

    case 'SET_ERROR':
      return {
        ...state,
        error: action.payload,
        loading: false,
      };

    case 'SET_SCROLL_OFFSET':
      return {
        ...state,
        scrollOffset: action.payload,
      };

    case 'SET_TERMINAL_HEIGHT':
      return {
        ...state,
        terminalHeight: action.payload,
      };

    case 'TOGGLE_SCOPE':
      return {
        ...state,
        scope: state.scope === 'current' ? 'all' : 'current',
      };

    case 'SET_SCOPE':
      return {
        ...state,
        scope: action.payload,
      };

    case 'ENTER_RENAME_MODE':
      return {
        ...state,
        isRenameMode: true,
        renameInput: action.payload,
      };

    case 'EXIT_RENAME_MODE':
      return {
        ...state,
        isRenameMode: false,
        renameInput: '',
      };

    case 'SET_RENAME_INPUT':
      return {
        ...state,
        renameInput: action.payload,
      };

    case 'APPEND_TO_SEARCH': {
      const query = state.searchQuery + action.payload;
      const sorted = sortSessions(state.sessions, state.sortOrder, state.sortReverse);
      const filtered = filterSessions(sorted, query);
      return {
        ...state,
        searchQuery: query,
        filteredSessions: filtered,
        activeIndex: 0,
      };
    }

    case 'BACKSPACE_SEARCH': {
      const query = state.searchQuery.slice(0, -1);
      const sorted = sortSessions(state.sessions, state.sortOrder, state.sortReverse);
      const filtered = filterSessions(sorted, query);
      return {
        ...state,
        searchQuery: query,
        filteredSessions: filtered,
        activeIndex: 0,
      };
    }

    case 'APPEND_TO_RENAME':
      return {
        ...state,
        renameInput: state.renameInput + action.payload,
      };

    case 'BACKSPACE_RENAME':
      return {
        ...state,
        renameInput: state.renameInput.slice(0, -1),
      };

    case 'SET_REDIRECT_CMD':
      return {
        ...state,
        redirectCmd: action.payload,
      };

    default:
      return state;
  }
};

export function useSessionBrowserState() {
  return useReducer(sessionBrowserReducer, initialState);
}
