/**
 * Session Browser Types
 * Type definitions for session management and browsing
 */

export interface SessionInfo {
  id: string;                    // Session ID
  index: number;                 // Display index
  sessionId: string;             // Full session ID
  firstUserMessage: string;      // First user message
  messageCount: number;          // Total message count
  lastUpdated: string;           // Last updated time (ISO)
  startTime: string;             // Start time (ISO)
  isCurrentSession: boolean;     // Whether this is the current session
  projectRoot?: string;          // Project root path
  projectName?: string;          // Project name
  displayName?: string;          // Display name
  matchSnippets?: string[];      // Search match snippets
  matchCount?: number;           // Match count
}

export interface SessionBrowserState {
  sessions: SessionInfo[];
  filteredSessions: SessionInfo[];
  activeIndex: number;
  searchQuery: string;
  isSearchMode: boolean;
  sortOrder: 'date' | 'messages' | 'name';
  sortReverse: boolean;
  loading: boolean;
  error: string | null;
  scrollOffset: number;
  terminalHeight: number;
  scope: 'current' | 'all';    // Session scope: current project or all
  isRenameMode: boolean;        // Whether rename mode is active
  renameInput: string;          // Rename input value
  redirectCmd: string | null;   // cd migration command shown when switching workspaces
}

export type SessionAction = 
  | { type: 'SET_SESSIONS'; payload: SessionInfo[] }
  | { type: 'SET_FILTERED_SESSIONS'; payload: SessionInfo[] }
  | { type: 'SET_ACTIVE_INDEX'; payload: number }
  | { type: 'SET_SEARCH_QUERY'; payload: string }
  | { type: 'TOGGLE_SEARCH_MODE' }
  | { type: 'CYCLE_SORT_ORDER' }
  | { type: 'TOGGLE_SORT_REVERSE' }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_SCROLL_OFFSET'; payload: number }
  | { type: 'SET_TERMINAL_HEIGHT'; payload: number }
  | { type: 'TOGGLE_SCOPE' }
  | { type: 'SET_SCOPE'; payload: 'current' | 'all' }
  | { type: 'ENTER_RENAME_MODE'; payload: string }                  // Enter rename mode; payload is current name
  | { type: 'EXIT_RENAME_MODE' }
  | { type: 'SET_RENAME_INPUT'; payload: string }                   // Set rename input to full string (used to clear)
  | { type: 'APPEND_TO_SEARCH'; payload: string }                   // Append char to search input (reducer-managed to avoid stale closure)
  | { type: 'BACKSPACE_SEARCH' }
  | { type: 'APPEND_TO_RENAME'; payload: string }
  | { type: 'BACKSPACE_RENAME' }
  | { type: 'SET_REDIRECT_CMD'; payload: string | null };           // Set or clear cross-workspace migration command

export interface SessionBrowserProps {
  projectRoot: string;
  onResume: (sessionId: string) => Promise<void>;
  onExit: () => void;
  currentSessionId?: string;
}

export interface SessionListProps {
  sessions: SessionInfo[];
  activeIndex: number;
  scrollOffset: number;
  visibleCount: number;
  onSelect: (session: SessionInfo) => void;
  showProjectName?: boolean;  // Whether to show project name
}

export interface SessionItemProps {
  session: SessionInfo;
  isActive: boolean;
  showMatchSnippets?: boolean;
  showProjectName?: boolean;  // Whether to show project name in global mode
}

export interface SearchBoxProps {
  query: string;
  isActive: boolean;
}

export interface RenameBoxProps {
  value: string;
  isActive: boolean;
}

export interface SessionBrowserHeaderProps {
  totalCount: number;
  filteredCount: number;
  currentPage: number;
  totalPages: number;
  sortOrder: 'date' | 'messages' | 'name';
  sortReverse: boolean;
  scope: 'current' | 'all';       // Session scope
  projectName?: string;            // Project name shown when scope=current
}

export interface SessionBrowserFooterProps {
  isSearchMode: boolean;
  hasResults: boolean;
  scope: 'current' | 'all';  // Used to display scope-specific shortcut hints
}
