import { useEffect, MutableRefObject, Dispatch, SetStateAction } from 'react';
import { SiadaACPClient } from '../../../acp/client.js';
import { ClientConfig, Message, ConnectionStatus } from '../../../types/index.js';
import { logger } from '../../../utils/logger.js';
import { TokenUsage, InteractiveInputRequest, LoginState } from '../types.js';

interface EventHandlers {
  setClient: Dispatch<SetStateAction<SiadaACPClient | null>>;
  setConnectionStatus: Dispatch<SetStateAction<ConnectionStatus>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setTokenUsage: Dispatch<SetStateAction<TokenUsage | null>>;
  setInteractiveInput: Dispatch<SetStateAction<InteractiveInputRequest | null>>;
  setLoginState: Dispatch<SetStateAction<LoginState>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  clientRef: MutableRefObject<SiadaACPClient | null>;
  currentSessionIdRef: MutableRefObject<string | null>;
  handleAgentMessage: (message: Message) => void;
  handleToolUse: (toolData: any) => void;
  flushStreamingNow: () => void;
  resetStreaming: () => void;
}

export function useClientEvents(config: ClientConfig, handlers: EventHandlers): void {
  const {
    setClient, setConnectionStatus, setLoading, setTokenUsage,
    setInteractiveInput, setLoginState, setMessages,
    clientRef, currentSessionIdRef,
    handleAgentMessage, handleToolUse, flushStreamingNow, resetStreaming,
  } = handlers;

  useEffect(() => {
    let mounted = true;

    const initClient = async () => {
      try {
        const _acpStart = Date.now();
        logger.info(`[PERF][acp] initClient start`);
        const acpClient = new SiadaACPClient(config);

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
              logger.info('Session changed, cleared message history', { previousSessionId, sessionId });
            }

            currentSessionIdRef.current = sessionId;
            import('../../../services/checkpointService.js').then(({ checkpointService }) => {
              checkpointService.setSessionId(sessionId);
            });
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

        acpClient.on('animation:stop', () => { if (mounted) setLoading(false); });
        acpClient.on('animation:start', () => { if (mounted) setLoading(true); });

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
                content: 'Interactive input cancelled: command timed out',
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

        await acpClient.connect();

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
