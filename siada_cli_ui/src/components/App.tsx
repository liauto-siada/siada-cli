import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Box, Text, useApp, useStdout } from '@jrichman/ink';
import Spinner from 'ink-spinner';
import { MainLayout } from './layouts/MainLayout.js';
import { SessionBrowser } from './SessionBrowser/index.js';
import { PluginManager } from './PluginManager/index.js';
import type { PluginManagerData } from './PluginManager/index.js';
import { LoginSelector, LoginWaiting } from './Login/index.js';
import type { LoginChoice } from './Login/index.js';
import { TaskSelector, TaskItem } from './TaskSelector/index.js';
import { ModelSelector } from './ModelSelector/ModelSelector.js';
import { useACP } from '../hooks/useACP.js';
import { ClientConfig, Message } from '../types/index.js';
import { getIcons } from '../constants/icons.js';
import { logger } from '../utils/logger.js';
import { useMemoryMonitor } from '../hooks/useMemoryMonitor.js';
import { useBackendExit } from '../hooks/useBackendExit.js';
import { useAdapterEvents } from '../hooks/useAdapterEvents.js';
import { useKeypress } from '../hooks/useKeypress.js';
import { AppProvider } from '../store/context.js';
import { Banner } from './Banner/Banner.js';

const LoadingView: React.FC<{ message: string; footer?: string }> = ({ message, footer }) => (
  <Box flexDirection="column" padding={1}>
    <Box marginBottom={1}><Text color="cyan" bold>Siada CLI</Text></Box>
    <Box>
      <Text color="yellow"><Spinner type="dots" /></Text>
      <Text> {message}</Text>
    </Box>
    {footer && <Box marginTop={1}><Text dimColor>{footer}</Text></Box>}
  </Box>
);

const ErrorView: React.FC<{ title: string; message: string; hint: string; exitHint: string; errorIcon: string }> = ({
  title, message, hint, exitHint, errorIcon,
}) => (
  <Box flexDirection="column" padding={1}>
    <Box marginBottom={1}><Text color="red" bold>{errorIcon} {title}</Text></Box>
    <Box marginBottom={1}><Text color="red">{message}</Text></Box>
    <Box><Text dimColor>{hint}</Text></Box>
    <Box marginTop={1}><Text dimColor>{exitHint}</Text></Box>
  </Box>
);

export interface AppProps {
  config: ClientConfig;
  onExit?: (sessionId: string | null) => void;
}

export const App: React.FC<AppProps> = ({ config, onExit }) => {
  const { exit } = useApp();
  const [isCollapsed, setIsCollapsed] = useState(true); // default compact mode
  const [isSubmittingLogin, setIsSubmittingLogin] = useState(false);
  const [showSessionBrowser, setShowSessionBrowser] = useState(false); // Session browser state
  const [modelSelectorData, setModelSelectorData] = useState<{ models: string[]; currentModel: string } | null>(null);
  const [pluginManagerData, setPluginManagerData] = useState<PluginManagerData | null>(null); // Plugin manager state
  const [installProgress, setInstallProgress] = useState<{ skillName: string; phase: string; percent: number } | null>(null);
  const [taskSelectorTasks, setTaskSelectorTasks] = useState<TaskItem[] | null>(null); // Task selector state
  const icons = getIcons();
  const {
    messages,
    connectionStatus,
    loading,
    bannerInfo,
    tokenUsage,
    interactiveInput,
    loginState,
    sendMessage,
    sendInteractiveInput,
    stopExecution,
    addMessage,
    updateMessage,
    clearMessages,
    client,
    sessionId,
  } = useACP(config);

  useBackendExit(client, exit);

  useAdapterEvents(client, {
    setShowSessionBrowser,
    clearMessages,
    addMessage,
    setModelSelectorData,
    setTaskSelectorTasks,
    setInstallProgress,
    setPluginManagerData,
  });

  const stableSendMessage = useCallback((message: string) => {
    sendMessage(message);
  }, [sendMessage]);

  const stableStopExecution = useCallback(() => {
    stopExecution();
  }, [stopExecution]);

  const stableAddMessage = useCallback((message: Message) => {
    addMessage(message);
  }, [addMessage]);

  const stableUpdateMessage = useCallback((id: string, updates: Partial<Message>) => {
    updateMessage(id, updates);
  }, [updateMessage]);

  const handleSelectModel = useCallback(async (modelName: string) => {
    setModelSelectorData(null);
    logger.info('Selecting model', { component: 'App', operation: 'select_model', modelName });
    try {
      if (client) await client.sendMessage(`/model ${modelName}`);
    } catch (error) {
      logger.error('Failed to switch model', { component: 'App', operation: 'select_model_error', error });
    }
  }, [client]);

  const handleSelectTask = useCallback(async (task: TaskItem) => {
    logger.info('Selecting task', { component: 'App', operation: 'select_task', taskId: task.id, title: task.title });
    setTaskSelectorTasks(null);
    const actions = task.suggested_actions?.length
      ? '\n\nSuggested actions:\n' + task.suggested_actions.map(a => `- ${a}`).join('\n')
      : '';
    const message = `Please work on the following task:\n\n**${task.title}**\n\n${task.description}${actions}`;
    await sendMessage(message);
  }, [sendMessage]);

  const handleCloseTaskSelector = useCallback(() => {
    setTaskSelectorTasks(null);
  }, []);

  const handlePluginAction = useCallback(
    async (message: string) => {
      logger.info('Plugin manager action', {
        component: 'App',
        operation: 'plugin_action',
        message,
      });
      if (client) {
        await client.sendMessage(message).catch(() => {});
      }
    },
    [client]
  );

  const handleClosePluginManager = useCallback(() => {
    setPluginManagerData(null);
  }, []);

  useEffect(() => {
    if (loginState?.phase === 'waiting' && loginState.openBrowser && loginState.url) {
      import('child_process').then(({ exec }) => {
        const platform = process.platform;
        const cmd = platform === 'win32'
          ? `start "" "${loginState.url}"`
          : platform === 'darwin'
          ? `open "${loginState.url}"`
          : `xdg-open "${loginState.url}"`;
        exec(cmd);
      }).catch(() => {});
    }
  }, [loginState]);

  useEffect(() => {
    if (loginState?.phase !== 'selecting') {
      setIsSubmittingLogin(false);
    }
  }, [loginState?.phase]);

  const handleLoginSelect = useCallback(async (choice: LoginChoice, apiKey?: string) => {
    if (!client || isSubmittingLogin) {
      return;
    }

    setIsSubmittingLogin(true);
    try {
      await client.sendLoginChoice(choice, choice === '3' ? apiKey : undefined);
    } catch {
      setIsSubmittingLogin(false);
    }
  }, [client, isSubmittingLogin]);

  const handleResumeSession = useCallback(async (sessionId: string) => {
    try {
      if (client) {
        await client.sendMessage(`/resume ${sessionId}`);
      }
      setShowSessionBrowser(false);
    } catch (error) {
      logger.error('Failed to resume session', { error });
    }
  }, [client]);

  const handleCloseSessionBrowser = useCallback(() => {
    setShowSessionBrowser(false);
  }, []);

  useMemoryMonitor(messages, config.workingDir, config.model);

  const ctrlCCountRef = useRef(0);
  const ctrlCTimerRef = useRef<NodeJS.Timeout | null>(null);

  const handleKeypress = useCallback((key: any) => {
    if (key.ctrl && key.name === 'c') {
      ctrlCCountRef.current += 1;
      if (ctrlCTimerRef.current) clearTimeout(ctrlCTimerRef.current);
      if (ctrlCCountRef.current === 1) {
        stableStopExecution();
        ctrlCTimerRef.current = setTimeout(() => { ctrlCCountRef.current = 0; }, 2000);
      } else {
        onExit?.(sessionId);
        exit();
      }
      return;
    }

    if (key.ctrl && key.name === 'o') {
      setIsCollapsed(prev => {
        process.stdout?.write('\x1b[2J\x1b[H');
        return !prev;
      });
    }
  }, [stableStopExecution, onExit, sessionId, exit]);

  useKeypress(handleKeypress);

  const startupError = messages.find(m =>
    m.type === 'error' || m.metadata?.type === 'startup_error'
  );

  type ViewState =
    | 'connecting' | 'initializing' | 'connection_error' | 'startup_error'
    | 'login_selecting' | 'login_waiting' | 'loading_config'
    | 'plugin_manager' | 'task_selector' | 'model_selector' | 'session_browser' | 'main';

  const viewState: ViewState = (() => {
    if (connectionStatus.connecting)                          return 'connecting';
    if (connectionStatus.error && !connectionStatus.connected) return 'connection_error';
    if (startupError)                                         return 'startup_error';
    // Login checks come before 'initializing': the backend now sends
    // ui/showLoginSelector BEFORE sending the `ready` signal, so we must
    // render the login view even while connectionStatus.ready is still false.
    if (loginState?.phase === 'selecting')                    return 'login_selecting';
    if (loginState?.phase === 'waiting')                      return 'login_waiting';
    if (connectionStatus.connected && !connectionStatus.ready) return 'initializing';
    if (connectionStatus.ready && !bannerInfo)                return 'loading_config';
    if (pluginManagerData)                                    return 'plugin_manager';
    if (taskSelectorTasks !== null)                           return 'task_selector';
    if (modelSelectorData !== null)                           return 'model_selector';
    if (showSessionBrowser)                                   return 'session_browser';
    return 'main';
  })();

  switch (viewState) {
    case 'connecting':
      return <LoadingView message="Connecting to siada-cli..." footer={`Working directory: ${config.workingDir}`} />;

    case 'initializing':
      return <LoadingView message="Initializing agent..." footer="Please wait while the agent starts up" />;

    case 'connection_error':
      return (
        <ErrorView
          errorIcon={icons.error}
          title="Connection Failed"
          message={connectionStatus.error ?? ''}
          hint="Make sure siada-cli is installed and accessible in your PATH."
          exitHint="Press ESC to exit"
        />
      );

    case 'startup_error':
      return (
        <ErrorView
          errorIcon={icons.error}
          title="Startup Error"
          message={startupError?.content || 'Unknown error during startup'}
          hint="Please check your configuration and try again."
          exitHint="Press Ctrl+C to exit"
        />
      );

    case 'login_selecting': {
      const s = loginState as Extract<typeof loginState, { phase: 'selecting' }>;
      return (
        <Box flexDirection="column">
          <Banner
            version={bannerInfo?.version}
            workingDir={bannerInfo?.workingDir || config.workingDir}
            agent={bannerInfo?.agent || 'coder'}
            provider={bannerInfo?.provider || 'li'}
            model={bannerInfo?.model || config.model}
            prePlanMode={bannerInfo?.prePlanMode || false}
            isCollapsed={isCollapsed}
            showAgentInfo={false}
          />
          <Box marginTop={1}>
            <LoginSelector
              onSelect={handleLoginSelect}
              providers={s.providers as any}
              cancelable={s.cancelable}
              liidDisabled={s.liidDisabled}
              submitting={isSubmittingLogin}
            />
          </Box>
        </Box>
      );
    }

    case 'login_waiting': {
      const s = loginState as Extract<typeof loginState, { phase: 'waiting' }>;
      return (
        <Box flexDirection="column">
          <Banner
            version={bannerInfo?.version}
            workingDir={bannerInfo?.workingDir || config.workingDir}
            agent={bannerInfo?.agent || 'coder'}
            provider={bannerInfo?.provider || 'li'}
            model={bannerInfo?.model || config.model}
            prePlanMode={bannerInfo?.prePlanMode || false}
            isCollapsed={isCollapsed}
            showAgentInfo={false}
          />
          <Box marginTop={1}>
            <LoginWaiting url={s.url} openBrowser={s.openBrowser} />
          </Box>
        </Box>
      );
    }

    case 'loading_config':
      return <LoadingView message="Loading configuration..." />;

    case 'plugin_manager':
      return (
        <PluginManager
          data={pluginManagerData!}
          installProgress={installProgress}
          onAction={handlePluginAction}
          onExit={handleClosePluginManager}
        />
      );

    case 'task_selector':
      return (
        <TaskSelector
          tasks={taskSelectorTasks!}
          onSelect={handleSelectTask}
          onExit={handleCloseTaskSelector}
        />
      );

    case 'model_selector':
      return (
        <ModelSelector
          models={modelSelectorData!.models}
          currentModel={modelSelectorData!.currentModel}
          onSelect={handleSelectModel}
          onExit={() => setModelSelectorData(null)}
        />
      );

    case 'session_browser':
      return (
        <SessionBrowser
          projectRoot={config.workingDir}
          onResume={handleResumeSession}
          onExit={handleCloseSessionBrowser}
          currentSessionId={undefined}
        />
      );

    default:
      return (
        <AppProvider>
          <Box flexDirection="column" height="95%" flexShrink={0} flexGrow={0} overflow="hidden">
            <MainLayout
              version={bannerInfo?.version || "0.0.0"}
              workingDir={bannerInfo?.workingDir || config.workingDir}
              agent={bannerInfo?.agent || "coder"}
              provider={bannerInfo?.provider || "li"}
              model={bannerInfo?.model || config.model}
              prePlanMode={bannerInfo?.prePlanMode || false}
              messages={messages}
              loading={loading}
              isReady={connectionStatus.ready}
              tokenUsage={tokenUsage}
              onSendMessage={stableSendMessage}
              onAddMessage={stableAddMessage}
              onUpdateMessage={stableUpdateMessage}
              onStopExecution={stableStopExecution}
              isCollapsed={isCollapsed}
              interactiveInput={interactiveInput}
              onSendInteractiveInput={sendInteractiveInput}
              sessionId={sessionId}
            />
          </Box>
        </AppProvider>
      );
  }
};
