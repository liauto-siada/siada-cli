/**
 * Shell Types
 * Type definitions for shell command execution
 */

/**
 * Shell execution result
 */
export interface ShellExecutionResult {
  /** Exit code */
  exitCode: number | null;
  
  /** Standard output */
  stdout: string;
  
  /** Standard error */
  stderr: string;
  
  /** Whether command was killed/aborted */
  killed: boolean;
  
  /** Error message if execution failed */
  error?: string;
  
  /** Process ID */
  pid?: number;
  
  /** Execution duration in ms */
  duration?: number;
  
  /** Whether binary output was detected */
  isBinary?: boolean;
  
  /** Final working directory (if changed) */
  finalCwd?: string;
}

/**
 * Shell execution options
 */
export interface ShellExecutionOptions {
  /** Working directory */
  cwd: string;
  
  /** Environment variables */
  env?: Record<string, string>;
  
  /** Timeout in ms (0 = no timeout) */
  timeout?: number;
  
  /** Abort signal */
  signal?: AbortSignal;
  
  /** Enable interactive shell (PTY) */
  interactive?: boolean;
  
  /** Max stdout buffer size (bytes) */
  maxBuffer?: number;
  
  /** Shell to use (default: /bin/sh or cmd.exe) */
  shell?: string;
}

/**
 * Shell execution event types
 */
export type ShellExecutionEvent =
  | { type: 'start'; pid: number }
  | { type: 'data'; chunk: string; stream: 'stdout' | 'stderr' }
  | { type: 'binary_detected'; bytesReceived: number }
  | { type: 'binary_progress'; bytesReceived: number }
  | { type: 'exit'; exitCode: number | null; killed: boolean }
  | { type: 'error'; error: Error };

/**
 * Shell execution callback
 */
export type ShellExecutionCallback = (event: ShellExecutionEvent) => void;

/**
 * Shell history entry
 */
export interface ShellHistoryEntry {
  /** Command text */
  command: string;
  
  /** Timestamp */
  timestamp: number;
  
  /** Working directory */
  cwd: string;
  
  /** Exit code */
  exitCode?: number;
}

/**
 * Shell history options
 */
export interface ShellHistoryOptions {
  /** History file path */
  historyFile?: string;
  
  /** Maximum history entries */
  maxEntries?: number;
  
  /** Auto-save on add */
  autoSave?: boolean;
}

/**
 * Shell command validation result
 */
export interface CommandValidationResult {
  /** Whether command is allowed */
  allowed: boolean;
  
  /** List of disallowed commands found */
  disallowedCommands?: string[];
  
  /** Reason for blocking */
  blockReason?: string;
  
  /** Whether this is a hard denial (cannot be overridden) */
  isHardDenial?: boolean;
}

/**
 * Dangerous commands that require confirmation
 */
export const DANGEROUS_COMMANDS = [
  'rm',
  'rmdir',
  'del',
  'format',
  'mkfs',
  'dd',
  'shutdown',
  'reboot',
  'init',
  'halt',
  'poweroff',
];

/**
 * Blocked commands that are never allowed
 */
export const BLOCKED_COMMANDS = [
  'fork',
  'forkbomb',
  ':()',
];
