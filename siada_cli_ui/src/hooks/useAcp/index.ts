import { useCallback, useEffect } from 'react';
import { useStdout } from 'ink';
import { ClientConfig, Message } from '../../types/index.js';
import { logger } from '../../utils/logger.js';
import { recordFlicker } from '../../utils/flickerMonitor.js';
import { UseACPResult } from './types.js';
import { useACPState } from './state/index.js';
import { useStreamingMessages } from './streaming/index.js';
import { useClientEvents } from './events/index.js';

export * from './types.js';

export function useACP(config: ClientConfig): UseACPResult {
  const state = useACPState();
  const { stdout } = useStdout();

  // Keep messagesRef in sync with messages state for todo range tracking
  useEffect(() => {
    state.messagesRef.current = state.messages;
  }, [state.messages]);

  const { flushStreamingNow, resetStreaming, handleAgentMessage, handleToolUse } = useStreamingMessages({
    setMessages: state.setMessages,
    setBannerInfo: state.setBannerInfo,
    stdout,
    workingDir: config.workingDir,
    model: config.model,
    pullHistoryTimeoutRef: state.pullHistoryTimeoutRef,
    messagesRef: state.messagesRef,
    setTodoItems: state.setTodoItems,
    setTodoMessageRanges: state.setTodoMessageRanges,
  });

  useClientEvents(config, {
    setClient: state.setClient,
    setConnectionStatus: state.setConnectionStatus,
    setLoading: state.setLoading,
    setTokenUsage: state.setTokenUsage,
    setInteractiveInput: state.setInteractiveInput,
    setLoginState: state.setLoginState,
    setMessages: state.setMessages,
    setTodoItems: state.setTodoItems,
    setTodoMessageRanges: state.setTodoMessageRanges,
    setGoalState: state.setGoalState,
    messagesRef: state.messagesRef,
    clientRef: state.clientRef,
    currentSessionIdRef: state.currentSessionIdRef,
    pendingHistoryRef: state.pendingHistoryRef,
    historyBufferRef: state.historyBufferRef,
    pendingUserMessageIdRef: state.pendingUserMessageIdRef,
    pullHistoryTimeoutRef: state.pullHistoryTimeoutRef,
    setBannerInfo: state.setBannerInfo,
    setCacheStatus: state.setCacheStatus,
    handleAgentMessage,
    handleToolUse,
    flushStreamingNow,
    resetStreaming,
  });

  const sendMessage = useCallback(async (content: string, imagePaths?: string[], options?: { queueId?: string }) => {
    if (!state.client) {
      state.setMessages(prev => [...prev, {
        id: `warning_${Date.now()}`,
        type: 'system',
        content: 'Agent is not initialized yet. Please wait...',
        timestamp: new Date().toISOString(),
        author: 'System',
      }]);
      return;
    }
    if (!state.client.isConnected()) {
      state.setMessages(prev => [...prev, {
        id: `warning_${Date.now()}`,
        type: 'system',
        content: 'Not connected to siada-cli. Please reconnect.',
        timestamp: new Date().toISOString(),
        author: 'System',
      }]);
      return;
    }

    // Queued send (agent is busy): the prompt is held in the preview queue and
    // is only rendered into the main conversation when the backend actually
    // consumes it (queue_item_consumed — either a mid-turn injection or an
    // end-of-turn flush). Skip the optimistic user bubble AND the pullHistory
    // sync here: rendering now would put the prompt on screen prematurely, and
    // a mid-turn pullHistory could later re-render the already-injected item
    // (signature divergence), causing duplicates.
    if (options?.queueId) {
      try {
        await state.client.sendMessage(content, imagePaths, options);
      } catch (error) {
        state.setMessages(prev => [...prev, {
          id: `error_${Date.now()}`,
          type: 'error',
          content: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`,
          timestamp: new Date().toISOString(),
          author: 'System',
        }]);
      }
      return;
    }


    // /btw side-question commands are rendered in the SideQuestionPanel only;
    // they must NOT appear as a user bubble in the main conversation.
    const trimmedContent = content.trim();
    const isBtwCommand =
      trimmedContent === '/btw' || trimmedContent.startsWith('/btw ');

    // Deferred rendering: send pullHistory notification before user message
    // This triggers cross-channel session sync (IM → TUI)
    const userMsgId = `user_${Date.now()}`;
    state.pendingHistoryRef.current = true;
    state.historyBufferRef.current = [];
    // Only track the pending user message id when we will actually render it.
    state.pendingUserMessageIdRef.current = isBtwCommand ? null : userMsgId;
    state.client.sendNotification('session/pullHistory', {});
    
    // Set a timeout to auto-reset the pending flag in case pullHistoryDone never arrives
    if (state.pullHistoryTimeoutRef.current) {
      clearTimeout(state.pullHistoryTimeoutRef.current);
    }
    state.pullHistoryTimeoutRef.current = setTimeout(() => {
      if (state.pendingHistoryRef.current) {
        logger.warn('pullHistory timeout, flushing buffer before user message', {
          component: 'useACP',
          operation: 'pullHistory_timeout',
        });
        // Flush any buffered messages, inserting before the user message by ID
        const buffered = state.historyBufferRef.current;
        const pendingId = state.pendingUserMessageIdRef.current;
        state.historyBufferRef.current = [];
        state.pendingHistoryRef.current = false;
        state.pendingUserMessageIdRef.current = null;
        if (buffered.length > 0) {
          state.setMessages(prev => {
            const userIdx = pendingId ? prev.findIndex(m => m.id === pendingId) : -1;
            if (userIdx >= 0) {
              const before = prev.slice(0, userIdx);
              const after = prev.slice(userIdx);
              return [...before, ...buffered, ...after];
            }
            return [...prev, ...buffered];
          });
        }
      }
      state.pullHistoryTimeoutRef.current = null;
    }, 3000);

    if (!isBtwCommand) {
      state.setMessages(prev => [...prev, {
        id: userMsgId,
        type: 'user',
        content,
        timestamp: new Date().toISOString(),
        author: 'You',
      }]);
    }

    try {
      await state.client.sendMessage(content, imagePaths, options);
    } catch (error) {
      state.setMessages(prev => [...prev, {
        id: `error_${Date.now()}`,
        type: 'error',
        content: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date().toISOString(),
        author: 'System',
      }]);
      state.setLoading(false);
    }
  }, [state.client]);

  const cancelPendingQueue = useCallback(() => {
    state.client?.cancelPendingQueue();
  }, [state.client]);

  // showInterruptMessage controls whether the "Execution interrupted" system
  // hint is rendered. Ctrl+C shows it; Esc (flush queue and run) suppresses it
  // because the queued prompt will be rendered on screen instead.
  const stopExecution = useCallback(async (showInterruptMessage: boolean = true) => {
    if (!state.client || !state.client.isConnected()) return;
    try {
      await state.client.interrupt();
      state.setInteractiveInput(null);
      if (showInterruptMessage) {
        state.setMessages(prev => [...prev, {
          id: `system_${Date.now()}`,
          type: 'system',
          content: 'Execution interrupted, Ctrl+C again to exit',
          timestamp: new Date().toISOString(),
          author: 'System',
        }]);
      }
    } catch (error) {
      logger.error('Failed to interrupt execution', error);
      state.setInteractiveInput(null);
    }
  }, [state.client]);


  const addMessage = useCallback((message: Message) => {
    state.setMessages(prev => [...prev, message]);
  }, []);

  const updateMessage = useCallback((id: string, updates: Partial<Message>) => {
    state.setMessages(prev => prev.map(msg => msg.id === id ? { ...msg, ...updates } : msg));
  }, []);

  const sendInteractiveInput = useCallback(async (input: string) => {
    if (!state.client || !state.client.isConnected()) return;
    try {
      await state.client.sendMessage(input);
      state.setInteractiveInput(null);
      state.setLoading(true);
    } catch (error) {
      logger.error('Failed to send interactive input', error);
      state.setInteractiveInput(null);
    }
  }, [state.client]);

  const clearMessages = useCallback(() => {
    recordFlicker('clearMessages', `useACP.clearMessages — clearing ${state.messagesRef.current?.length ?? 0} messages`);
    state.setMessages([]);
  }, []);

  return {
    client: state.client,
    clientRef: state.clientRef,
    messages: state.messages,
    connectionStatus: state.connectionStatus,
    loading: state.loading,
    bannerInfo: state.bannerInfo,
    tokenUsage: state.tokenUsage,
    interactiveInput: state.interactiveInput,
    loginState: state.loginState,
    sendMessage,
    sendInteractiveInput,
    stopExecution,
    cancelPendingQueue,
    addMessage,
    updateMessage,
    clearMessages,
    sessionId: state.currentSessionIdRef.current,
    cacheStatus: state.cacheStatus,
    todoItems: state.todoItems,
    todoMessageRanges: state.todoMessageRanges,
    goalState: state.goalState,
  };
}
