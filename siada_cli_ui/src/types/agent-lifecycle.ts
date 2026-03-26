/**
 * Agent Lifecycle Types
 * Based on ACP (Agent Communication Protocol) design patterns
 */

/**
 * Agent run status based on ACP RunStatus
 */
export enum AgentRunStatus {
  CREATED = 'created',
  IN_PROGRESS = 'in-progress',
  AWAITING = 'awaiting',
  CANCELLING = 'cancelling',
  CANCELLED = 'cancelled',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

/**
 * Check if status is terminal (no further transitions)
 */
export function isTerminalStatus(status: AgentRunStatus): boolean {
  return [
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
  ].includes(status);
}

/**
 * Check if agent is actively running
 */
export function isActiveStatus(status: AgentRunStatus): boolean {
  return [AgentRunStatus.IN_PROGRESS, AgentRunStatus.AWAITING].includes(status);
}

/**
 * Message event types based on ACP Event system
 */
export enum MessageEventType {
  MESSAGE_CREATED = 'message.created',
  MESSAGE_PART = 'message.part',
  MESSAGE_COMPLETED = 'message.completed',
  RUN_CREATED = 'run.created',
  RUN_IN_PROGRESS = 'run.in-progress',
  RUN_AWAITING = 'run.awaiting',
  RUN_CANCELLED = 'run.cancelled',
  RUN_FAILED = 'run.failed',
  RUN_COMPLETED = 'run.completed',
  TOOL_CALL_STARTED = 'toolCall.started',
  TOOL_CALL_COMPLETED = 'toolCall.completed',
  TOOL_CALL_FAILED = 'toolCall.failed',
  ERROR = 'error',
  GENERIC = 'generic',
}

/**
 * Message part for streaming content
 */
export interface MessagePart {
  content: string;
  contentType?: string;
  name?: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

/**
 * Agent message with metadata
 */
export interface AgentMessage {
  id: string;
  role: string;
  parts: MessagePart[];
  createdAt: string;
  completedAt?: string;
  metadata?: Record<string, any>;
}

/**
 * Agent error information
 */
export interface AgentError {
  code: string;
  message: string;
  details?: Record<string, any>;
  timestamp: string;
}

/**
 * Agent run information
 * Tracks the lifecycle of a single agent execution
 */
export interface AgentRun {
  runId: string;
  agentName: string;
  sessionId?: string;
  status: AgentRunStatus;
  inputMessages: AgentMessage[];
  outputMessages: AgentMessage[];
  error?: AgentError;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  metadata?: Record<string, any>;
  duration?: number; // in seconds
}

/**
 * Agent event for lifecycle tracking
 */
export interface AgentEvent {
  type: MessageEventType;
  runId: string;
  timestamp: string;
  data?: Record<string, any>;
  message?: AgentMessage;
  messagePart?: MessagePart;
  run?: AgentRun;
  error?: AgentError;
}

/**
 * Message state during lifecycle
 */
export enum MessageState {
  CREATING = 'creating',
  STREAMING = 'streaming',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

/**
 * Tracked message with state information
 */
export interface TrackedMessage {
  message: AgentMessage;
  state: MessageState;
  partCount: number;
  totalContentLength: number;
  error?: string;
  events: AgentEvent[];
}

/**
 * Run statistics
 */
export interface RunStatistics {
  total: number;
  byStatus: Record<string, number>;
  active: number;
  terminal: number;
}

/**
 * Message statistics
 */
export interface MessageStatistics {
  totalMessages: number;
  totalParts: number;
  totalContentLength: number;
  byState: Record<string, number>;
  byEventType: Record<string, number>;
  totalEvents: number;
}

/**
 * Event handler type
 */
export type EventHandler = (event: AgentEvent) => void;

/**
 * Event filter options
 */
export interface EventFilterOptions {
  eventType?: MessageEventType;
  since?: Date;
  runId?: string;
  messageId?: string;
}

/**
 * Status display configuration
 */
export interface StatusDisplayConfig {
  status: AgentRunStatus;
  label: string;
  color: string;
  icon: string;
  description?: string;
}

/**
 * Get status display configuration
 */
export function getStatusDisplay(status: AgentRunStatus): StatusDisplayConfig {
  const configs: Record<AgentRunStatus, StatusDisplayConfig> = {
    [AgentRunStatus.CREATED]: {
      status,
      label: 'Created',
      color: 'gray',
      icon: '○',
      description: 'Run has been created',
    },
    [AgentRunStatus.IN_PROGRESS]: {
      status,
      label: 'Running',
      color: 'blue',
      icon: '◐',
      description: 'Agent is executing',
    },
    [AgentRunStatus.AWAITING]: {
      status,
      label: 'Awaiting',
      color: 'yellow',
      icon: '⏸',
      description: 'Waiting for user input',
    },
    [AgentRunStatus.CANCELLING]: {
      status,
      label: 'Cancelling',
      color: 'orange',
      icon: '⊗',
      description: 'Cancelling execution',
    },
    [AgentRunStatus.CANCELLED]: {
      status,
      label: 'Cancelled',
      color: 'gray',
      icon: '⊗',
      description: 'Execution was cancelled',
    },
    [AgentRunStatus.COMPLETED]: {
      status,
      label: 'Completed',
      color: 'green',
      icon: '✓',
      description: 'Successfully completed',
    },
    [AgentRunStatus.FAILED]: {
      status,
      label: 'Failed',
      color: 'red',
      icon: '✗',
      description: 'Execution failed',
    },
  };

  return configs[status];
}

/**
 * Event type display configuration
 */
export interface EventTypeDisplay {
  type: MessageEventType;
  label: string;
  color: string;
  icon: string;
}

/**
 * Get event type display configuration
 */
export function getEventTypeDisplay(eventType: MessageEventType): EventTypeDisplay {
  const displays: Record<MessageEventType, EventTypeDisplay> = {
    [MessageEventType.MESSAGE_CREATED]: {
      type: eventType,
      label: 'Message Created',
      color: 'blue',
      icon: '✉',
    },
    [MessageEventType.MESSAGE_PART]: {
      type: eventType,
      label: 'Message Part',
      color: 'cyan',
      icon: '▸',
    },
    [MessageEventType.MESSAGE_COMPLETED]: {
      type: eventType,
      label: 'Message Completed',
      color: 'green',
      icon: '✓',
    },
    [MessageEventType.RUN_CREATED]: {
      type: eventType,
      label: 'Run Created',
      color: 'gray',
      icon: '○',
    },
    [MessageEventType.RUN_IN_PROGRESS]: {
      type: eventType,
      label: 'Run In Progress',
      color: 'blue',
      icon: '◐',
    },
    [MessageEventType.RUN_AWAITING]: {
      type: eventType,
      label: 'Run Awaiting',
      color: 'yellow',
      icon: '⏸',
    },
    [MessageEventType.RUN_CANCELLED]: {
      type: eventType,
      label: 'Run Cancelled',
      color: 'gray',
      icon: '⊗',
    },
    [MessageEventType.RUN_FAILED]: {
      type: eventType,
      label: 'Run Failed',
      color: 'red',
      icon: '✗',
    },
    [MessageEventType.RUN_COMPLETED]: {
      type: eventType,
      label: 'Run Completed',
      color: 'green',
      icon: '✓',
    },
    [MessageEventType.TOOL_CALL_STARTED]: {
      type: eventType,
      label: 'Tool Call Started',
      color: 'purple',
      icon: '🔧',
    },
    [MessageEventType.TOOL_CALL_COMPLETED]: {
      type: eventType,
      label: 'Tool Call Completed',
      color: 'green',
      icon: '✓',
    },
    [MessageEventType.TOOL_CALL_FAILED]: {
      type: eventType,
      label: 'Tool Call Failed',
      color: 'red',
      icon: '✗',
    },
    [MessageEventType.ERROR]: {
      type: eventType,
      label: 'Error',
      color: 'red',
      icon: '⚠',
    },
    [MessageEventType.GENERIC]: {
      type: eventType,
      label: 'Generic Event',
      color: 'gray',
      icon: '•',
    },
  };

  return displays[eventType];
}
