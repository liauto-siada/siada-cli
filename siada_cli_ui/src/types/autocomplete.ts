/**
 * AutoComplete Types
 * Type definitions for autocomplete functionality
 */

export interface Suggestion {
  /** Display text shown to user */
  label: string;
  
  /** Actual value to be inserted */
  value: string;
  
  /** Optional description */
  description?: string;
  
  /** Type of suggestion */
  type: 'file' | 'command' | 'checkpoint' | 'resource' | 'prompt';
  
  /** Matched index for highlighting */
  matchedIndex?: number;
  
  /** Icon or prefix */
  icon?: string;
  
  /** Match positions for highlighting (from fzf) */
  positions?: number[];
  
  /** Match score (from fzf) */
  score?: number;
  
  /** Command kind (for slash commands) */
  commandKind?: CommandKind;
}

export interface AutoCompleteState {
  /** List of suggestions */
  suggestions: Suggestion[];
  
  /** Currently active suggestion index */
  activeIndex: number;
  
  /** Loading state */
  isLoading: boolean;
  
  /** Whether to show suggestions */
  showSuggestions: boolean;
  
  /** Current search pattern */
  pattern: string;
  
  /** Type of autocomplete */
  mode: CompletionMode;
  
  /** Visible start index for scrolling */
  visibleStartIndex: number;
  
  /** Whether current match is perfect */
  isPerfectMatch: boolean;
}

export enum CompletionMode {
  IDLE = 'IDLE',
  AT = 'AT',
  SLASH = 'SLASH',
  PROMPT = 'PROMPT',
}

export enum AutoCompleteType {
  AT_COMMAND = '@',
  SLASH_COMMAND = '/',
  NONE = ''
}

export enum CommandKind {
  BUILTIN = 'BUILTIN',
  CUSTOM = 'CUSTOM',
  MCP_PROMPT = 'MCP_PROMPT',
  SHELL = 'SHELL',
}

export interface AutoCompleteConfig {
  /** Maximum number of suggestions to show */
  maxResults?: number;
  
  /** Enable fuzzy search */
  fuzzySearch?: boolean;
  
  /** Debounce delay in ms */
  debounceMs?: number;
  
  /** Respect .gitignore */
  respectGitIgnore?: boolean;
  
  /** Maximum search depth */
  maxDepth?: number;
  
  /** Enable @ completion */
  enableAtCompletion?: boolean;
  
  /** Enable / completion */
  enableSlashCompletion?: boolean;
  
  /** Enable prompt completion */
  enablePromptCompletion?: boolean;
  
  /** Minimum length for prompt completion */
  promptCompletionMinLength?: number;
}

export interface FileSearchOptions {
  /** Pattern to search for */
  pattern: string;
  
  /** Current working directory */
  cwd: string;
  
  /** File extensions to include */
  include?: string[];
  
  /** File patterns to exclude */
  exclude?: string[];
  
  /** Maximum results */
  maxResults?: number;
}

export interface CommandDefinition {
  /** Command name (without /) */
  name: string;
  
  /** Alternative names/aliases */
  aliases?: string[];
  
  /** Command description */
  description: string;
  
  /** Sub-commands */
  subCommands?: CommandDefinition[];
  
  /** Whether command can auto-execute on Enter */
  autoExecute?: boolean;
  
  /** Command kind */
  kind?: CommandKind;
  
  /** Whether this command requires session argument */
  requiresSession?: boolean;
  
  /** Completion function for arguments */
  completion?: (context: CommandContext, args: string) => Promise<Suggestion[]>;
}

export interface CommandContext {
  /** Current session */
  session?: any;
  
  /** Current working directory */
  cwd: string;
  
  /** Verbose mode */
  verbose?: boolean;
  
  /** Additional context data */
  [key: string]: any;
}

export interface CompletionRange {
  /** Start position of completion */
  start: number;
  
  /** End position of completion */
  end: number;
  
  /** Current query string */
  query: string;
}
