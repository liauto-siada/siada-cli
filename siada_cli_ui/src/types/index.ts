/**
 * Core type definitions for siada-cli-ui
 */

// Re-export ClientConfig from config types
export { ClientConfig } from './config';

export type MessageType = 'user' | 'agent' | 'system' | 'error' | 'tool';

export type AgentMessageSubtype = 'thinking' | 'tool_use' | 'answer' | 'process' | 'shell';

export interface Message {
  id: string;
  type: MessageType;
  content: string;
  timestamp: string;
  author: string;
  toolCalls?: ToolCall[];
  fileEdits?: FileEdit[];
  metadata?: {
    subtype?: AgentMessageSubtype;
    blockType?: string;
    conversationId?: string;
    streamStartId?: string;         // Start ID of streaming message, used for stable React keys
    isSplitContent?: boolean;      // Marks this as a split message fragment
    splitIndex?: number;            // Index of the split fragment (0, 1, 2...)
    isLastSplit?: boolean;          // Whether this is the last fragment
    originalMessageId?: string;     // Original message ID, used to trace split origin
    group_key?: string;             // Group key; messages with the same key belong to the same group
    shellExecution?: ShellExecution; // Shell execution details (used when subtype='shell')
    [key: string]: any;
  };
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  result?: any;
  status: 'pending' | 'running' | 'success' | 'error';
  timestamp: string;
}

export interface FileEdit {
  path: string;
  action: 'create' | 'update' | 'delete' | 'rename';
  content?: string;
  diff?: string;
  timestamp: string;
  oldPath?: string;
}

export interface ConnectionStatus {
  connected: boolean;
  connecting: boolean;
  ready: boolean;  // Agent is ready to receive messages
  error?: string;
}

export interface ACPMessage {
  method: string;
  params?: any;
  id?: string | number;
}

export interface ACPEvent {
  type: string;
  data: any;
  timestamp: string;
}

export interface ShellExecution {
  command: string;
  executing: boolean;
  stdout: string;
  stderr: string;
  exitCode?: number | null;
  error?: string;
  duration?: number;
  isBinary?: boolean;
}

export interface AppState {
  messages: Message[];
  connectionStatus: ConnectionStatus;
  loading: boolean;
  shellModeActive: boolean;
  shellExecution?: ShellExecution;
}

// Re-export session types
export * from './session.js';
