/**
 * ACP Protocol Type Definitions
 * Based on Agent Client Protocol specification
 */

export interface ACPRequest {
  jsonrpc: '2.0';
  id: string | number;
  method: string;
  params?: any;
}

export interface ACPResponse {
  jsonrpc: '2.0';
  id: string | number;
  result?: any;
  error?: ACPError;
}

export interface ACPNotification {
  jsonrpc: '2.0';
  method: string;
  params?: any;
}

export interface ACPError {
  code: number;
  message: string;
  data?: any;
}

export interface ACPMessage {
  jsonrpc: '2.0';
  id?: string | number;
  method: string;
  params?: any;
  result?: any;
  error?: ACPError;
}

// Agent capabilities
export interface AgentCapabilities {
  streaming?: boolean;
  files?: boolean;
  shell?: boolean;
  tools?: string[];
  multimodal?: boolean;
}

// Client capabilities
export interface ClientCapabilities {
  streaming?: boolean;
  notifications?: boolean;
  progress?: boolean;
}

// Initialize request/response
export interface InitializeParams {
  clientInfo: {
    name: string;
    version: string;
  };
  capabilities: ClientCapabilities;
  workingDirectory?: string;
}

export interface InitializeResult {
  agentInfo: {
    name: string;
    version: string;
    model?: string;
  };
  capabilities: AgentCapabilities;
}

// Agent execution
export interface AgentExecuteParams {
  prompt: string;
  stream?: boolean;
  context?: {
    files?: string[];
    variables?: Record<string, any>;
  };
}

export interface AgentExecuteResult {
  content: string;
  done: boolean;
  toolCalls?: ToolCallInfo[];
  fileEdits?: FileEditInfo[];
}

// Tool execution
export interface ToolCallInfo {
  id: string;
  name: string;
  arguments: Record<string, any>;
  result?: any;
  status: 'pending' | 'running' | 'success' | 'error';
  error?: string;
}

// File operations
export interface FileEditInfo {
  path: string;
  action: 'create' | 'update' | 'delete' | 'rename';
  content?: string;
  oldPath?: string; // for rename
  encoding?: string;
}

export interface FileReadParams {
  path: string;
  encoding?: string;
}

export interface FileReadResult {
  content: string;
  encoding: string;
  size: number;
}

export interface FileWriteParams {
  path: string;
  content: string;
  encoding?: string;
  createDirectories?: boolean;
}

export interface FileListParams {
  path: string;
  recursive?: boolean;
  pattern?: string;
}

export interface FileListResult {
  files: FileInfo[];
}

export interface FileInfo {
  path: string;
  type: 'file' | 'directory' | 'symlink';
  size?: number;
  modified?: string;
}

// Progress notifications
export interface ProgressParams {
  token: string | number;
  value: {
    kind: 'begin' | 'report' | 'end';
    title?: string;
    message?: string;
    percentage?: number;
  };
}

// Event types
export type ACPEventType = 
  | 'message'
  | 'toolUse'
  | 'fileEdit'
  | 'progress'
  | 'error'
  | 'thinking'
  | 'complete';

export interface ACPEvent {
  type: ACPEventType;
  data: any;
  timestamp: string;
}

// Protocol handler interface
export interface ProtocolHandler {
  handleRequest(request: ACPRequest): Promise<ACPResponse>;
  handleNotification(notification: ACPNotification): Promise<void>;
  sendRequest(method: string, params?: any): Promise<any>;
  sendNotification(method: string, params?: any): Promise<void>;
}
