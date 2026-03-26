/**
 * Message Type Definitions
 * Defines all message-related types
 */

/**
 * Message type enum
 */
export type MessageType = 'user' | 'agent' | 'system' | 'error' | 'tool';

/**
 * Message subtype for agent messages
 */
export type AgentMessageSubtype = 'thinking' | 'tool_use' | 'answer' | 'process';

/**
 * Message role
 */
export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * Tool call status
 */
export type ToolCallStatus = 'pending' | 'running' | 'success' | 'error';

/**
 * File action types
 */
export type FileActionType = 'create' | 'update' | 'delete' | 'rename' | 'read';

/**
 * Tool call information
 */
export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  result?: any;
  status: ToolCallStatus;
  timestamp: string;
  error?: string;
  duration?: number;
}

/**
 * File edit information
 */
export interface FileEdit {
  path: string;
  action: FileActionType;
  content?: string;
  diff?: string;
  timestamp: string;
  oldPath?: string; // For rename operations
  encoding?: string;
  size?: number;
}

/**
 * Message metadata
 */
export interface MessageMetadata {
  model?: string;
  temperature?: number;
  tokens?: {
    prompt: number;
    completion: number;
    total: number;
  };
  cost?: number;
  duration?: number;
  context?: {
    files?: string[];
    variables?: Record<string, any>;
  };
  subtype?: AgentMessageSubtype; // Subtype for agent messages
  conversationId?: string; // Group messages from same conversation turn
  [key: string]: any;
}

/**
 * Message attachment
 */
export interface MessageAttachment {
  type: 'file' | 'image' | 'link' | 'code';
  url?: string;
  path?: string;
  content?: string;
  mimeType?: string;
  size?: number;
  name?: string;
}

/**
 * Message entity (for mentions, links, etc.)
 */
export interface MessageEntity {
  type: 'mention' | 'file' | 'link' | 'code';
  text: string;
  offset: number;
  length: number;
  metadata?: any;
}

/**
 * Core message interface
 */
export interface Message {
  id: string;
  type: MessageType;
  content: string;
  timestamp: string;
  author: string;
  role?: MessageRole;
  toolCalls?: ToolCall[];
  fileEdits?: FileEdit[];
  metadata?: MessageMetadata;
  attachments?: MessageAttachment[];
  entities?: MessageEntity[];
  parentId?: string; // For threaded conversations
  replyToId?: string; // For replies
  edited?: boolean;
  editedAt?: string;
}

/**
 * Message thread
 */
export interface MessageThread {
  id: string;
  rootMessageId: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

/**
 * Conversation context
 */
export interface ConversationContext {
  id: string;
  messages: Message[];
  workingDirectory: string;
  files: string[];
  variables: Record<string, any>;
  metadata: Record<string, any>;
}

/**
 * Message filter criteria
 */
export interface MessageFilter {
  type?: MessageType | MessageType[];
  author?: string;
  startDate?: Date | string;
  endDate?: Date | string;
  hasToolCalls?: boolean;
  hasFileEdits?: boolean;
  searchQuery?: string;
}

/**
 * Message sort options
 */
export interface MessageSortOptions {
  field: 'timestamp' | 'author' | 'type';
  order: 'asc' | 'desc';
}

/**
 * Message pagination
 */
export interface MessagePagination {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

/**
 * Message create options
 */
export interface CreateMessageOptions {
  type: MessageType;
  content: string;
  author: string;
  role?: MessageRole;
  toolCalls?: ToolCall[];
  fileEdits?: FileEdit[];
  metadata?: MessageMetadata;
  parentId?: string;
  replyToId?: string;
}

/**
 * Message update options
 */
export interface UpdateMessageOptions {
  content?: string;
  toolCalls?: ToolCall[];
  fileEdits?: FileEdit[];
  metadata?: Partial<MessageMetadata>;
  edited?: boolean;
}

/**
 * Streaming message chunk
 */
export interface MessageChunk {
  id: string;
  content: string;
  done: boolean;
  index?: number;
  delta?: string;
}

/**
 * Message event types
 */
export type MessageEventType =
  | 'message.created'
  | 'message.updated'
  | 'message.deleted'
  | 'message.streaming'
  | 'message.complete'
  | 'toolCall.started'
  | 'toolCall.completed'
  | 'toolCall.failed'
  | 'fileEdit.started'
  | 'fileEdit.completed'
  | 'fileEdit.failed';

/**
 * Message event
 */
export interface MessageEvent {
  type: MessageEventType;
  messageId: string;
  message?: Message;
  chunk?: MessageChunk;
  toolCall?: ToolCall;
  fileEdit?: FileEdit;
  timestamp: string;
}

/**
 * Message statistics
 */
export interface MessageStatistics {
  total: number;
  byType: Record<MessageType, number>;
  byAuthor: Record<string, number>;
  withToolCalls: number;
  withFileEdits: number;
  totalToolCalls: number;
  totalFileEdits: number;
  averageLength: number;
  timeRange: {
    start: string;
    end: string;
  };
}

/**
 * Message export format
 */
export interface MessageExport {
  version: string;
  exportedAt: string;
  messageCount: number;
  messages: Message[];
  metadata?: Record<string, any>;
}

/**
 * Message import result
 */
export interface MessageImportResult {
  success: boolean;
  imported: number;
  skipped: number;
  errors: Array<{
    messageId?: string;
    error: string;
  }>;
}
