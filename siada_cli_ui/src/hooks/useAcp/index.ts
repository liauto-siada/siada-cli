import { useCallback } from 'react';
import { useStdout } from 'ink';
import { ClientConfig, Message } from '../../types/index.js';
import { logger } from '../../utils/logger.js';
import { UseACPResult } from './types.js';
import { useACPState } from './state/index.js';
import { useStreamingMessages } from './streaming/index.js';
import { useClientEvents } from './events/index.js';

export * from './types.js';

export function useACP(config: ClientConfig): UseACPResult {
  const state = useACPState();
  const { stdout } = useStdout();

  const { flushStreamingNow, resetStreaming, handleAgentMessage, handleToolUse } = useStreamingMessages({
    setMessages: state.setMessages,
    setBannerInfo: state.setBannerInfo,
    stdout,
    workingDir: config.workingDir,
    model: config.model,
  });

  useClientEvents(config, {
    setClient: state.setClient,
    setConnectionStatus: state.setConnectionStatus,
    setLoading: state.setLoading,
    setTokenUsage: state.setTokenUsage,
    setInteractiveInput: state.setInteractiveInput,
    setLoginState: state.setLoginState,
    setMessages: state.setMessages,
    clientRef: state.clientRef,
    currentSessionIdRef: state.currentSessionIdRef,
    handleAgentMessage,
    handleToolUse,
    flushStreamingNow,
    resetStreaming,
  });

  const sendMessage = useCallback(async (content: string) => {
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

    state.setMessages(prev => [...prev, {
      id: `user_${Date.now()}`,
      type: 'user',
      content,
      timestamp: new Date().toISOString(),
      author: 'You',
    }]);

    try {
      await state.client.sendMessage(content);
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

  const stopExecution = useCallback(async () => {
    if (!state.client || !state.client.isConnected()) return;
    try {
      await state.client.interrupt();
      state.setInteractiveInput(null);
      state.setMessages(prev => [...prev, {
        id: `system_${Date.now()}`,
        type: 'system',
        content: 'Execution interrupted, Ctrl+C again to exit',
        timestamp: new Date().toISOString(),
        author: 'System',
      }]);
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
    state.setMessages([]);
  }, []);

  return {
    client: state.client,
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
    addMessage,
    updateMessage,
    clearMessages,
    sessionId: state.currentSessionIdRef.current,
  };
}
