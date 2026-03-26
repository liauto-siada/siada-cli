/**
 * State Reducers
 * Defines actions and state update logic
 */

import { AppState, Message, ShellExecution } from '../types/index.js';
import { MAX_MESSAGE_HISTORY } from '../constants/limits.js';
import { logger } from '../utils/logger.js';

/**
 * Action Types
 */
export type AppAction =
  // Message Actions
  | { type: 'ADD_MESSAGE'; payload: Message }
  | { type: 'UPDATE_MESSAGE'; payload: { id: string; updates: Partial<Message> } }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'SET_MESSAGES'; payload: Message[] }
  | { type: 'REMOVE_MESSAGE'; payload: string }

  // Connection Actions
  | { type: 'SET_CONNECTING' }
  | { type: 'SET_CONNECTED' }
  | { type: 'SET_DISCONNECTED'; payload?: string }
  | { type: 'SET_CONNECTION_ERROR'; payload: string }

  // UI Actions
  | { type: 'SET_LOADING'; payload: boolean }

  // Shell Actions
  | { type: 'TOGGLE_SHELL_MODE' }
  | { type: 'SET_SHELL_MODE'; payload: boolean }
  | { type: 'SET_SHELL_EXECUTION'; payload: ShellExecution }
  | { type: 'CLEAR_SHELL_EXECUTION' }

  // Reset Action
  | { type: 'RESET_STATE' };

/**
 * Trim message array to prevent unbounded growth
 * Keeps the most recent messages up to MAX_MESSAGE_HISTORY
 * Ensures at least MIN_MESSAGE_HISTORY messages are kept
 */
function trimMessages(messages: Message[]): Message[] {
  if (messages.length <= MAX_MESSAGE_HISTORY) {
    return messages;
  }

  const trimCount = messages.length - MAX_MESSAGE_HISTORY;
  const trimmed = messages.slice(trimCount);
  
  logger.warn(`Message array trimmed to prevent memory leak`, {
    component: 'Reducer',
    operation: 'trim_messages',
    originalCount: messages.length,
    trimmedCount: trimCount,
    newCount: trimmed.length,
    maxAllowed: MAX_MESSAGE_HISTORY,
  });

  
  return trimmed;
}

/**
 * App Reducer - main state reducer
 */
export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    // Message Actions
    case 'ADD_MESSAGE': {
      const newMessages = [...state.messages, action.payload];
      const trimmedMessages = trimMessages(newMessages);
      
      // Log message addition
      logger.debug(`Message added`, {
        component: 'Reducer',
        operation: 'add_message',
        messageId: action.payload.id,
        messageType: action.payload.type,
        totalMessages: trimmedMessages.length,
        contentLength: action.payload.content.length,
      });

      // // Periodic memory check (every 10 messages)
      // if (trimmedMessages.length % 10 === 0) {
      //   logger.logMemoryUsage('Reducer');
      //   logger.logMessageStats(trimmedMessages.length);
      // }

      return {
        ...state,
        messages: trimmedMessages,
      };
    }

    case 'UPDATE_MESSAGE': {
      const updatedMessages = state.messages.map(msg =>
        msg.id === action.payload.id
          ? { ...msg, ...action.payload.updates }
          : msg
      );
      
      logger.debug(`Message updated`, {
        component: 'Reducer',
        operation: 'update_message',
        messageId: action.payload.id,
        updatedFields: Object.keys(action.payload.updates),
      });
      
      return {
        ...state,
        messages: updatedMessages,
      };
    }

    case 'CLEAR_MESSAGES':
      logger.info(`All messages cleared`, {
        component: 'Reducer',
        operation: 'clear_messages',
        clearedCount: state.messages.length,
      });
      
      // Force garbage collection hint
      if (global.gc) {
        global.gc();
        logger.info(`Manual garbage collection triggered after clearing messages`);
      }
      
      return {
        ...state,
        messages: [],
      };

    case 'SET_MESSAGES': {
      const trimmedMessages = trimMessages(action.payload);
      
      logger.info(`Messages set`, {
        component: 'Reducer',
        operation: 'set_messages',
        originalCount: action.payload.length,
        finalCount: trimmedMessages.length,
      });
      
      return {
        ...state,
        messages: trimmedMessages,
      };
    }

    case 'REMOVE_MESSAGE': {
      const filteredMessages = state.messages.filter(msg => msg.id !== action.payload);
      
      logger.debug(`Message removed`, {
        component: 'Reducer',
        operation: 'remove_message',
        messageId: action.payload,
        remainingCount: filteredMessages.length,
      });
      
      return {
        ...state,
        messages: filteredMessages,
      };
    }

    // Connection Actions
    case 'SET_CONNECTING':
      return {
        ...state,
        connectionStatus: {
          connected: false,
          connecting: true,
          ready: false,
          error: undefined,
        },
      };

    case 'SET_CONNECTED':
      return {
        ...state,
        connectionStatus: {
          connected: true,
          connecting: false,
          ready: false,
          error: undefined,
        },
      };

    case 'SET_DISCONNECTED':
      return {
        ...state,
        connectionStatus: {
          connected: false,
          connecting: false,
          ready: false,
          error: action.payload,
        },
      };

    case 'SET_CONNECTION_ERROR':
      return {
        ...state,
        connectionStatus: {
          ...state.connectionStatus,
          error: action.payload,
        },
      };

    // UI Actions
    case 'SET_LOADING':
      return {
        ...state,
        loading: action.payload,
      };

    // Shell Actions
    case 'TOGGLE_SHELL_MODE':
      return {
        ...state,
        shellModeActive: !state.shellModeActive,
      };

    case 'SET_SHELL_MODE':
      return {
        ...state,
        shellModeActive: action.payload,
      };

    case 'SET_SHELL_EXECUTION':
      return {
        ...state,
        shellExecution: action.payload,
      };

    case 'CLEAR_SHELL_EXECUTION':
      return {
        ...state,
        shellExecution: undefined,
      };

    // Reset Action
    case 'RESET_STATE':
      return {
        messages: [],
        connectionStatus: {
          connected: false,
          connecting: false,
          ready: false,
        },
        loading: false,
        shellModeActive: false,
        shellExecution: undefined,
      };

    default:
      return state;
  }
}

/**
 * Action Creators
 */

// Shell Action Creators
export const toggleShellMode = (): AppAction => ({
  type: 'TOGGLE_SHELL_MODE',
});

export const setShellMode = (active: boolean): AppAction => ({
  type: 'SET_SHELL_MODE',
  payload: active,
});

export const setShellExecution = (execution: ShellExecution): AppAction => ({
  type: 'SET_SHELL_EXECUTION',
  payload: execution,
});

export const clearShellExecution = (): AppAction => ({
  type: 'CLEAR_SHELL_EXECUTION',
});
