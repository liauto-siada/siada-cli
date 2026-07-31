import { useEffect, MutableRefObject, Dispatch, SetStateAction } from 'react';
import { SiadaACPClient } from '../../../acp/client.js';
import { ClientConfig, Message, ConnectionStatus } from '../../../types/index.js';
import { logger } from '../../../utils/logger.js';
import { TokenUsage, InteractiveInputRequest, LoginState, TodoItem, BannerInfo, TodoMessageRange, CacheStatusData, GoalState } from '../types.js';
import { promptQueueStore } from '../../../store/promptQueueStore.js';
import { setTerminalTitle } from '../../../utils/terminalTitle.js';

interface EventHandlers {
  setClient: Dispatch<SetStateAction<SiadaACPClient | null>>;
  setConnectionStatus: Dispatch<SetStateAction<ConnectionStatus>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setTokenUsage: Dispatch<SetStateAction<TokenUsage | null>>;
  setInteractiveInput: Dispatch<SetStateAction<InteractiveInputRequest | null>>;
  setLoginState: Dispatch<SetStateAction<LoginState>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setTodoItems: Dispatch<SetStateAction<TodoItem[]>>;
  setTodoMessageRanges: Dispatch<SetStateAction<Map<string, TodoMessageRange>>>;
  setGoalState: Dispatch<SetStateAction<GoalState | null>>;
  messagesRef: MutableRefObject<Message[]>;
  clientRef: MutableRefObject<SiadaACPClient | null>;
  currentSessionIdRef: MutableRefObject<string | null>;
  pendingHistoryRef: MutableRefObject<boolean>;
  historyBufferRef: MutableRefObject<Message[]>;
  pendingUserMessageIdRef: MutableRefObject<string | null>;
  pullHistoryTimeoutRef: MutableRefObject<NodeJS.Timeout | null>;
  setBannerInfo: Dispatch<SetStateAction<BannerInfo | null>>;
  setCacheStatus: Dispatch<SetStateAction<CacheStatusData | null>>;
  handleAgentMessage: (message: Message) => void;
  handleToolUse: (toolData: any) => void;
  flushStreamingNow: () => void;
  resetStreaming: () => void;
}

export function useClientEvents(config: ClientConfig, handlers: EventHandlers): void {
  const {
    setClient, setConnectionStatus, setLoading, setTokenUsage,
    setInteractiveInput, setLoginState, setMessages,
    setTodoItems, setTodoMessageRanges, setGoalState, messagesRef,
    clientRef, currentSessionIdRef,
    pendingHistoryRef, historyBufferRef, pendingUserMessageIdRef, pullHistoryTimeoutRef,
    setBannerInfo,
    setCacheStatus,
    handleAgentMessage, handleToolUse, flushStreamingNow, resetStreaming,
  } = handlers;

  useEffect(() => {
    let mounted = true;
    // De-dup guard: a given queue id should only ever land on screen once,
    // even if the backend emits queue_item_consumed more than once for it.
    const consumedIds = new Set<string>();

    const initClient = async () => {
      try {
        const _acpStart = Date.now();
        logger.info(`[PERF][acp] initClient start`);
        const acpClient = new SiadaACPClient(config);
        logger.info(`[PERF][acp] SiadaACPClient created | +${Date.now() - _acpStart}ms`);
        // Make acpClient available immediately so login-choice can be sent
        // during the startup window (before waitForReady / banner_info resolves).
        clientRef.current = acpClient;

        acpClient.on('connected', () => {
          if (mounted) {
            logger.info(`[PERF][acp] Client connected | +${Date.now() - _acpStart}ms`);
            setConnectionStatus(prev => ({ connected: true, connecting: false, ready: prev.ready }));
          }
        });

        acpClient.on('ready', () => {
          if (mounted) {
            logger.info(`[PERF][acp] Client ready | +${Date.now() - _acpStart}ms`);
            setConnectionStatus({ connected: true, connecting: false, ready: true });
          }
        });

        acpClient.on('agentMessage', (message: Message) => {
          if (mounted) {
            logger.debug('Received agent message', message);
            handleAgentMessage(message);
          }
        });

        acpClient.on('toolUse', (toolData: any) => {
          if (mounted) handleToolUse(toolData);
        });

        acpClient.on('fileEdit', (fileData: any) => {
          if (mounted) {
            flushStreamingNow();
            setMessages(prev => [...prev, {
              id: `file_${Date.now()}`,
              type: 'system',
              content: `File edited: ${fileData.path || 'unknown'}`,
              timestamp: new Date().toISOString(),
              author: 'Siada',
              fileEdits: [fileData],
            }]);
          }
        });

        acpClient.on('slashCommands:update', (commands: Array<{ name: string; description: string }>) => {
          if (mounted) {
            import('../../../services/slashCommandService.js').then(({ slashCommandService }) => {
              slashCommandService.updateCommandsFromBackend(commands);
            });
          }
        });

        acpClient.on('checkpoints:update', (checkpoints: Array<{ file_name: string; timestamp: string; tool: string; modified_files: string }>) => {
          if (mounted) {
            import('../../../services/checkpointService.js').then(({ checkpointService }) => {
              checkpointService.updateCheckpointsFromBackend(checkpoints);
            });
          }
        });

        acpClient.on('session:id', (sessionId: string) => {
          if (mounted) {
            const previousSessionId = currentSessionIdRef.current;
            const isSessionChange = previousSessionId !== null && previousSessionId !== sessionId;

            if (isSessionChange) {
              setMessages([]);
              setTokenUsage(null);
              resetStreaming();
              // Reset the queue de-dup table alongside the message history.
              // Otherwise it grows monotonically across a long-lived session
              // (it is only ever added to) since ids never repeat across turns.
              consumedIds.clear();

              // Reset deferred rendering state on session change
              pendingHistoryRef.current = false;
              historyBufferRef.current = [];
              pendingUserMessageIdRef.current = null;
              if (pullHistoryTimeoutRef.current) {
                clearTimeout(pullHistoryTimeoutRef.current);
                pullHistoryTimeoutRef.current = null;
              }
              logger.info('Session changed, cleared message history', { previousSessionId, sessionId });
            }

            currentSessionIdRef.current = sessionId;
            import('../../../services/checkpointService.js').then(({ checkpointService }) => {
              checkpointService.setSessionId(sessionId);
            });
          }
        });

        acpClient.on('session:title', (title: string) => {
          if (mounted) {
            setTerminalTitle(title);
          }
        });

        acpClient.on('project:hash', (projectHash: string) => {
          if (mounted) {
            import('../../../services/checkpointService.js').then(({ checkpointService }) => {
              checkpointService.setProjectHash(projectHash);
            });
          }
        });

        acpClient.on('tokenUsage', (data: any) => {
          if (mounted) {
            setTokenUsage({ contextSize: data.contextSize, contextMax: data.contextMax, message: data.message });
          }
        });

        acpClient.on('cacheStatus', (data: CacheStatusData) => {
          if (mounted) {
            logger.info('[CacheStatus] received', {
              component: 'useClientEvents',
              totalCost: data.accumulated_total_cost,
              timeSeconds: data.cost_time_seconds,
            });
            setCacheStatus(data);
          }
        });

        acpClient.on('animation:stop', () => { if (mounted) setLoading(false); });
        acpClient.on('animation:start', () => { if (mounted) setLoading(true); });

        // queue:itemConsumed — the backend has actually consumed a queued prompt
        // (mid-turn injection or end-of-turn flush). This is the moment the
        // prompt should appear in the main conversation: render it as a user
        // bubble now, then remove it from the preview overlay. Rendering here
        // (instead of at submit time) is what gives the "queue → consume"
        // behaviour: while the agent is busy the prompt only lives in the
        // preview list, and only "lands" on screen once the backend picks it up.
        acpClient.adapter.on('queue:itemConsumed', (data: { id: string; content?: string }) => {
          if (mounted && data?.id) {
            // Prefer the local preview entry, but fall back to the content
            // carried by the notification. This guarantees the prompt lands on
            // screen even when usePromptDrain already cleared the preview queue
            // before this consume event arrived (the turn-boundary race).
            const item = promptQueueStore.getById(data.id);
            const content = item ? item.content : data.content;
            if (content && !consumedIds.has(data.id)) {
              consumedIds.add(data.id);
              setMessages(prev => [...prev, {
                id: `user_${Date.now()}_${Math.floor(Math.random() * 1e6)}`,
                type: 'user',
                content,
                timestamp: new Date().toISOString(),
                author: 'You',
              }]);
            }
            promptQueueStore.removeById(data.id);
          }
        });

        acpClient.on('interactive:input', (data: { prompt: string; inputType: string; isPassword: boolean }) => {
          if (mounted) {
            setInteractiveInput({
              prompt: data.prompt,
              inputType: data.inputType as 'text' | 'password' | 'confirmation',
              isPassword: data.isPassword,
            });
            setLoading(false);
          }
        });

        acpClient.on('interactive:cancel', (data: { reason: string }) => {
          if (mounted) {
            setInteractiveInput(null);
            if (data.reason === 'timeout') {
              setMessages(prev => [...prev, {
                id: `system_${Date.now()}`,
                type: 'system',
                content: 'Command timed out',
                timestamp: new Date().toISOString(),
                author: 'System',
              }]);
            }
          }
        });

        acpClient.on('error', (error: Error) => {
          if (mounted) {
            logger.error('Client error', error);
            setConnectionStatus({ connected: false, connecting: false, ready: false, error: error.message });
            setMessages(prev => [...prev, {
              id: `error_${Date.now()}`,
              type: 'error',
              content: `Error: ${error.message}`,
              timestamp: new Date().toISOString(),
              author: 'System',
            }]);
            setLoading(false);
          }
        });

        acpClient.on('disconnected', () => {
          if (mounted) {
            setConnectionStatus({ connected: false, connecting: false, ready: false });
            setMessages(prev => [...prev, {
              id: `system_${Date.now()}`,
              type: 'system',
              content: 'Disconnected from siada-cli',
              timestamp: new Date().toISOString(),
              author: 'System',
            }]);
          }
        });

        acpClient.on('stderr', (message: string) => {
          if (mounted) logger.warn('stderr', { preview: message.substring(0, 200) });
        });

        // Fatal startup error from backend (e.g. invalid model name in config).
        // Backend sends `session/update` with reason=FAILED + _meta.type='startup_error',
        // then exits. Without handling here, the UI stays stuck on the
        // "Loading configuration…" spinner forever — the user can only force-kill.
        acpClient.adapter.on('startup:error', (params: { content: string; fatal?: boolean }) => {
          if (!mounted) return;
          const errMsg = params?.content || 'Unknown startup error';
          logger.error('Startup error from backend', new Error(errMsg));
          // 1) Stop the spinner / loading state
          setLoading(false);
          // 2) Mark connection as failed so App can render an error state
          setConnectionStatus({
            connected: false,
            connecting: false,
            ready: false,
            error: errMsg,
          });
          // 3) Surface a visible error message in the conversation pane
          setMessages(prev => [...prev, {
            id: `startup_error_${Date.now()}`,
            type: 'error',
            content: `Startup failed: ${errMsg}\n\nThe backend exited. Please fix the configuration (e.g. ~/.siada-cli/conf.yaml) and restart.`,
            timestamp: new Date().toISOString(),
            author: 'System',
          }]);
          // 4) Dismiss any login UI / interactive input so the error is visible
          setInteractiveInput(null);
          setLoginState(null);
        });

        // Login events must be registered before connect() — they fire during the startup window
        acpClient.adapter.on('ui:showLoginSelector', (params: any) => {
          if (mounted) {
            // Clear the terminal BEFORE the state update so Ink renders the login
            // view onto a clean screen (not appended below the main view content).
            process.stdout?.write('\x1b[2J\x1b[H');
            setLoginState({
              phase: 'selecting',
              providers: params?.providers,
              cancelable: params?.cancelable ?? false,
              liidDisabled: params?.liidDisabled ?? false,
            });
          }
        });
        acpClient.adapter.on('ui:loginDeviceUrl', (params: any) => {
          if (mounted) {
            process.stdout?.write('\x1b[2J\x1b[H');
            setLoginState({ phase: 'waiting', url: params?.url || '', openBrowser: !!params?.openBrowser });
          }
        });
        acpClient.adapter.on('ui:loginSuccess', () => {
          if (mounted) {
            // Clear login UI before switching back to main view
            process.stdout?.write('\x1b[2J\x1b[H');
            setLoginState(null);
          }
        });
        acpClient.adapter.on('ui:loginDismiss', () => {
          if (mounted) {
            process.stdout?.write('\x1b[2J\x1b[H');
            setLoginState(null);
          }
        });

        // Deferred rendering: handle session/pullHistoryDone from backend
        // Now receives history messages directly in params.messages (atomic, no separate appendHistory)
        acpClient.on('session:pullHistoryDone', (data?: { messages?: any[] }) => {
          if (mounted) {
            // Clear the timeout
            if (pullHistoryTimeoutRef.current) {
              clearTimeout(pullHistoryTimeoutRef.current);
              pullHistoryTimeoutRef.current = null;
            }
            
            const pendingUserMsgId = pendingUserMessageIdRef.current;
            pendingHistoryRef.current = false;
            pendingUserMessageIdRef.current = null;
            historyBufferRef.current = [];
            
            // Normalize and insert history messages from pullHistoryDone params
            const rawMessages = data?.messages || [];
            if (rawMessages.length > 0) {
              // Normalize backend format {role, content} → frontend format {id, type, content, ...}
              const normalizedMessages: Message[] = rawMessages.map((m: any, i: number) => ({
                id: `history_${Date.now()}_${i}`,
                type: (m.type || (m.role === 'user' ? 'user' : 'agent')) as Message['type'],
                content: m.content || '',
                timestamp: m.timestamp || new Date().toISOString(),
                author: m.author || (m.role === 'user' ? 'You' : 'Siada'),
                metadata: m.subtype ? { subtype: m.subtype } : undefined,
              }));

              logger.info('📥 pullHistoryDone: inserting history messages', {
                component: 'useACP',
                operation: 'pullHistoryDone',
                count: normalizedMessages.length,
                pendingUserMessageId: pendingUserMsgId,
              });

              setMessages(prev => {
                // Find the pending user message by its saved ID
                const userIdx = pendingUserMsgId
                  ? prev.findIndex(m => m.id === pendingUserMsgId)
                  : -1;
                if (userIdx >= 0) {
                  // Insert history before the user message, preserve everything after
                  const before = prev.slice(0, userIdx);
                  const after = prev.slice(userIdx);
                  return [...before, ...normalizedMessages, ...after];
                }
                // Fallback: append at end
                return [...prev, ...normalizedMessages];
              });
            } else {
              logger.info('📥 pullHistoryDone: no history messages', {
                component: 'useACP',
                operation: 'pullHistoryDone',
              });
            }
          }
        });

        // Todo state tracking: record message index ranges per todo step
        const todoItemsLocal: { current: TodoItem[] } = { current: [] };
        const todoRangesLocal: { current: Map<string, TodoMessageRange> } = { current: new Map() };

        const handleTodoState = (params: { todos: TodoItem[] }) => {
          if (!mounted) return;
          const newItems: TodoItem[] = params?.todos ?? [];
          const ranges = todoRangesLocal.current;

          const prevInProgressKeys = new Set(
            todoItemsLocal.current.filter(t => t.status === 'in_progress').map(t => t.content)
          );
          const newInProgressKeys = new Set(
            newItems.filter(t => t.status === 'in_progress').map(t => t.content)
          );

          // todos that left in_progress: close their range
          for (const key of prevInProgressKeys) {
            if (!newInProgressKeys.has(key)) {
              const range = ranges.get(key);
              if (range && range.endIdx === null) {
                ranges.set(key, { ...range, endIdx: messagesRef.current.length });
              }
            }
          }

          // todos newly entering in_progress: open their range
          for (const key of newInProgressKeys) {
            if (!prevInProgressKeys.has(key)) {
              ranges.set(key, { startIdx: messagesRef.current.length, endIdx: null });
            }
          }

          // all todos cleared (all_done rule): close any open ranges
          if (newItems.length === 0) {
            for (const [key, range] of ranges.entries()) {
              if (range.endIdx === null) {
                ranges.set(key, { ...range, endIdx: messagesRef.current.length });
              }
            }
          }

          todoItemsLocal.current = newItems;
          setTodoItems([...newItems]);
          // Merge into existing React state so we don't wipe ranges accumulated by the
          // streaming path (handleToolUse isFinal). Local `ranges` only contains transitions
          // seen via ACP notifications in this closure — other ranges survive.
          setTodoMessageRanges(prev => {
            const merged = new Map(prev);
            for (const [key, range] of ranges.entries()) {
              merged.set(key, range);
            }
            return merged;
          });
          logger.debug('[TodoState] updated', { count: newItems.length });
        };

        acpClient.adapter.on('context:todoState', handleTodoState);

        // Goal state tracking: mirror the backend's context/goalState push
        // directly into React state. Unlike todoState, there's no ranges/
        // transitions bookkeeping to do here — the backend already computed
        // the full { goal, verifying, notice? } shape.
        const handleGoalState = (params: { goal: { objective: string; status: string; createdAt?: string; turns?: number } | null; verifying: boolean; notice?: string }) => {

          if (!mounted) return;
          setGoalState(params as GoalState);
          logger.debug('[GoalState] updated', { status: params?.goal?.status, verifying: params?.verifying });
        };

        acpClient.adapter.on('context:goalState', handleGoalState);

        // Deferred rendering: handle ui/appendHistory from backend (legacy/fallback path)
        acpClient.adapter.on('ui:appendHistory', (data: { messages: any[] }) => {
          if (mounted && data?.messages?.length) {
            // Normalize backend format {role, content} → frontend format
            const normalizedMessages: Message[] = data.messages.map((m: any, i: number) => ({
              id: `history_${Date.now()}_${i}`,
              type: (m.type || (m.role === 'user' ? 'user' : 'agent')) as Message['type'],
              content: m.content || '',
              timestamp: m.timestamp || new Date().toISOString(),
              author: m.author || (m.role === 'user' ? 'You' : 'Siada'),
              metadata: m.subtype ? { subtype: m.subtype } : undefined,
            }));

            // Always render immediately (pullHistoryDone now handles buffered flow)
            setMessages(prev => [...prev, ...normalizedMessages]);
          }
        });

        // Handle runtime memory enable/disable notifications from backend (/memory enable|disable)
        acpClient.adapter.on('ui:memoryStatusChanged', (params: { enabled: boolean }) => {
          if (mounted) {
            logger.info('Memory status changed', { component: 'useClientEvents', enabled: params?.enabled });
            setBannerInfo(prev => prev ? { ...prev, memoryEnabled: params.enabled } : prev);
          }
        });

        await acpClient.connect();
        logger.info(`[PERF][acp] connect() resolved | +${Date.now() - _acpStart}ms`);

        if (mounted) {
          setClient(acpClient);
          clientRef.current = acpClient;
        }
      } catch (error) {
        if (mounted) {
          logger.error('Failed to initialize client', error);
          setConnectionStatus({
            connected: false,
            connecting: false,
            ready: false,
            error: error instanceof Error ? error.message : 'Unknown error',
          });
          setMessages(prev => [...prev, {
            id: `error_${Date.now()}`,
            type: 'error',
            content: `Failed to connect: ${error instanceof Error ? error.message : 'Unknown error'}`,
            timestamp: new Date().toISOString(),
            author: 'System',
          }]);
        }
      }
    };

    initClient();

    return () => {
      mounted = false;
      resetStreaming();
      if (clientRef.current) {
        clientRef.current.disconnect().catch(err => logger.error('Error during cleanup', err));
      }
    };
  }, [config]);
}
