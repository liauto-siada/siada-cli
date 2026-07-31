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
import type { SideQuestionItem } from './SideQuestion/index.js';
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
import { promptQueueStore } from '../store/promptQueueStore.js';
import { usePromptDrain } from '../hooks/usePromptDrain.js';
import { usePromptQueueSnapshot } from '../hooks/usePromptQueueSnapshot.js';
import { recordFlicker } from '../utils/flickerMonitor.js';

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
  const [sideQuestions, setSideQuestions] = useState<SideQuestionItem[]>([]); // /btw side-question list
  // Whether the /btw side-question panel is currently rendered.
  // - Auto set to true whenever a new /btw is appended → all preserved
  //   history reappears together with the new question.
  // - Esc inside the panel sets it to false: the panel hides and the input
  //   box becomes typable again, but `sideQuestions` (history) is kept
  //   intact in state, so the next /btw will redisplay everything.
  const [sideQuestionPanelVisible, setSideQuestionPanelVisible] = useState(false);
  // Transient one-line hint shown above the input box (e.g. for blank /btw).
  // It is intentionally NOT part of `sideQuestions` history and auto-clears.
  const [sideQuestionNotice, setSideQuestionNotice] = useState<string | null>(null);

  // /btw: add a pending item immediately on submit (answer=null shows "Answering...")

  const appendPendingSideQuestion = useCallback((question: string) => {
    setSideQuestions(prev => [
      ...prev,
      { question, answer: null, id: `btw-${Date.now()}-${Math.random()}` },
    ]);
    // A new /btw always (re)opens the panel, even if it was hidden via Esc,
    // so all preserved history is shown together with the new query.
    setSideQuestionPanelVisible(true);
  }, []);

  // /btw with no question: show a transient usage hint above the input box.
  // Intercepted entirely on the frontend so it never round-trips to the
  // backend. The hint is deliberately NOT pushed into `sideQuestions`, so it
  // never pollutes the side-question history list and never opens the panel.
  const showSideQuestionUsage = useCallback(() => {
    setSideQuestionNotice('Usage: /btw <your question>');
  }, []);

  // Auto-clear the transient /btw usage notice a few seconds after it shows.
  useEffect(() => {
    if (!sideQuestionNotice) return;
    const timer = setTimeout(() => setSideQuestionNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [sideQuestionNotice]);

  // Transient one-line flash for /goal set / verification pass-fail results.
  // Same shape as sideQuestionNotice: not part of any persistent goal state,
  // just a fire-and-auto-clear banner triggered by the backend's `notice`
  // field on a context/goalState push. The effect that watches
  // `goalState.notice` lives below, after `goalState` is destructured from
  // useACP().
  const [goalNotice, setGoalNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!goalNotice) return;
    const timer = setTimeout(() => setGoalNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [goalNotice]);

  // Esc inside the panel hides it without touching the history list.
  // The next /btw will reopen the panel and reveal everything that was kept.
  const hideSideQuestionPanel = useCallback(() => {
    setSideQuestionPanelVisible(false);
  }, []);



  // When the list becomes empty (e.g. fork sends the question elsewhere),
  // collapse the visibility flag so the input box is fully enabled.
  useEffect(() => {
    if (sideQuestions.length === 0 && sideQuestionPanelVisible) {
      setSideQuestionPanelVisible(false);
    }
  }, [sideQuestions.length, sideQuestionPanelVisible]);



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
    cancelPendingQueue,
    addMessage,
    updateMessage,
    clearMessages,
    client,
    clientRef,
    sessionId,
    todoItems,
    todoMessageRanges,
    cacheStatus,
    goalState,
  } = useACP(config);

  // Backend pushed a one-shot notice (goal set / verification pass-fail) on
  // this context/goalState update — surface it as the transient flash.
  useEffect(() => {
    if (goalState?.notice) {
      setGoalNotice(goalState.notice);
    }
  }, [goalState?.notice]);

  // Backend pushed a structured achieved/not-yet-achieved result — turn this
  // into a persistent collapsible chat message (frontend-only; NOT written
  // to backend session history, so resumed sessions won't replay it — an
  // accepted limitation per explicit product decision for this iteration).
  useEffect(() => {
    if (goalState?.result) {
      const r = goalState.result;
      addMessage({
        id: `goal_result_${Date.now()}`,
        type: 'system',
        content: '',
        timestamp: new Date().toISOString(),
        author: 'System',
        metadata: {
          subtype: 'goal_result',
          goalResult: r,
        },
      });
    }
  }, [goalState?.result]);

  // /btw: called when backend sends ui/showSideQuestion — update matching pending item
  const appendSideQuestion = useCallback(
    (item: { question: string; answer: string }) => {
      setSideQuestions(prev => {
        // Find the last pending item with a matching question
        let idx = -1;
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].question === item.question && prev[i].answer === null) {
            idx = i;
            break;
          }
        }
        if (idx !== -1) {
          // Update the pending item in-place
          return prev.map((q, i) => i === idx ? { ...q, answer: item.answer } : q);
        }
        // No pending match — append as a new item (fallback)
        return [...prev, { ...item, id: `btw-${Date.now()}-${Math.random()}` }];
      });
    },
    []
  );

  // /btw 侧边问答：删除单条
  const removeSideQuestion = useCallback((id: string) => {
    setSideQuestions(prev => prev.filter(q => q.id !== id));
  }, []);

  // /btw clear history: keep only the currently focused (newest) item and
  // drop everything older. The panel itself stays visible — pressing 'x'
  // is a "tidy up" action, not a close action.
  const clearSideQuestionsHistory = useCallback(() => {
    setSideQuestions(prev => (prev.length > 0 ? [prev[prev.length - 1]] : prev));
  }, []);


  // /btw fork: 关闭面板并把问题以普通消息送进主对话
  const forkSideQuestion = useCallback((item: SideQuestionItem) => {
    setSideQuestions([]);
    if (item.question) {
      // 用 setTimeout 让面板先卸载，避免输入框 focus 切换抖动
      setTimeout(() => sendMessage(item.question), 0);
    }
  }, [sendMessage]);

  useBackendExit(client, exit);

  useAdapterEvents(client, {
    setShowSessionBrowser,
    clearMessages,
    addMessage,
    setModelSelectorData,
    setTaskSelectorTasks,
    setInstallProgress,
    setPluginManagerData,
    appendSideQuestion,
  });

  const stableSendMessage = useCallback((message: string, imagePaths?: string[]) => {
    const trimmed = message.trim();
    // /btw always bypasses the queue and runs concurrently
    if (trimmed.startsWith('/btw ') || trimmed === '/btw') {
      const question = trimmed.startsWith('/btw ') ? trimmed.slice(5).trim() : '';
      if (!question) {
        // Blank /btw — show the usage hint in the side panel right here and do
        // NOT send anything to the backend. This avoids leaving a pending
        // "Answering..." item that would never resolve.
        showSideQuestionUsage();
        return;
      }
      appendPendingSideQuestion(question);
      setTimeout(() => sendMessage(message, imagePaths), 0);
      return;
    }

    // When agent is busy: enqueue in UI store first (to get the id), then send
    // to backend with the same queue_id so the backend can echo a consumed notification.
    if (loading) {
      const item = promptQueueStore.enqueue(message, imagePaths);
      sendMessage(message, imagePaths, { queueId: item.id });
      return;
    }
    sendMessage(message, imagePaths);
  }, [sendMessage, appendPendingSideQuestion, showSideQuestionUsage, loading]);


  usePromptDrain(loading);
  const promptQueue = usePromptQueueSnapshot();

  const stableStopExecution = useCallback(() => {
    cancelPendingQueue();      // tell backend to drop pending injections
    promptQueueStore.clear();  // clear UI preview
    stopExecution();
  }, [cancelPendingQueue, stopExecution]);

  // Esc while busy: interrupt the current run but KEEP the queue. The backend
  // ends the turn, flushes _pending_injections into a fresh turn and runs the
  // queued prompts one-by-one; each emits queue_item_consumed so the frontend
  // renders it into the conversation and drops it from the preview. (Ctrl+C, by
  // contrast, calls stableStopExecution above and discards the queue.)
  const stableFlushQueueAndRun = useCallback(() => {
    // Suppress the "Execution interrupted" hint: the queued prompt will be
    // rendered on screen and run as a fresh turn instead.
    stopExecution(false);
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

  // Auto-close plugin manager when installation completes (percent === 100).
  // Controlled here (not inside PluginManager) so setPluginManagerData is
  // called by the owner, avoiding yoga WASM issues from self-unmounting.
  useEffect(() => {
    if (installProgress?.percent === 100 && pluginManagerData) {
      const t = setTimeout(() => setPluginManagerData(null), 1200);
      return () => clearTimeout(t);
    }
  }, [installProgress?.percent, pluginManagerData]);

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
    // During the startup login window, connect() hasn't resolved yet so `client`
    // state is still null.  Use clientRef.current as fallback — it is set
    // immediately after SiadaACPClient is constructed, before waitForReady.
    const activeClient = client ?? clientRef.current;
    if (!activeClient || isSubmittingLogin) {
      logger.warn('[handleLoginSelect] no active client yet, ignoring login choice', {
        choice,
        clientNull: !client,
        clientRefNull: !clientRef.current,
      });
      return;
    }

    setIsSubmittingLogin(true);
    try {
      await activeClient.sendLoginChoice(choice, choice === '3' ? apiKey : undefined);
    } catch {
      setIsSubmittingLogin(false);
    }
  }, [client, clientRef, isSubmittingLogin]);

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
        recordFlicker('ctrl_c_interrupt', 'Ctrl+C: stopExecution + system message + queue clear', {
          messageCount: messages.length,
        });
        stableStopExecution();
        ctrlCTimerRef.current = setTimeout(() => { ctrlCCountRef.current = 0; }, 2000);
      } else {
        recordFlicker('ctrl_c_interrupt', 'Ctrl+C (double): exit app — clearing overlays before exit', {
          messageCount: messages.length,
        });
        // Clear overlay views before exit so they are removed from the React
        // tree before process.exit fires, preventing yoga WASM crashes during
        // Ink's final render pass.
        setPluginManagerData(null);
        setModelSelectorData(null);
        setTaskSelectorTasks(null);
        setShowSessionBrowser(false);
        onExit?.(sessionId);
        exit();
      }
      return;
    }

    if (key.ctrl && key.name === 'o') {
      setIsCollapsed(prev => {
        recordFlicker('ctrl_o_collapse', `Ctrl+O: toggle collapse mode ${prev} → ${!prev}`, {
          messageCount: messages.length,
        });
        // NOTE: screen clearing is handled by MessageList's refreshStatic(),
        // which reacts to the isCollapsed change via useEffect. Clearing here
        // as well caused a double flicker.
        return !prev;
      });
    }
  }, [stableStopExecution, onExit, sessionId, exit, messages.length]);

  useKeypress(handleKeypress);

  const startupError = messages.find(m =>
    m.type === 'error' || m.metadata?.type === 'startup_error'
  );

  type ViewState =
    | 'connecting' | 'initializing' | 'connection_error' | 'startup_error'
    | 'login_selecting' | 'login_waiting' | 'loading_config'
    | 'plugin_manager' | 'task_selector' | 'model_selector' | 'session_browser' | 'main';

  const viewState: ViewState = (() => {
    // Login checks come first: the backend sends ui/showLoginSelector before
    // the `ready` signal (and possibly before the connection handshake fully
    // resolves), so loginState must take priority over any spinner state to
    // avoid the login selector being hidden behind "Connecting to siada-cli...".
    if (loginState?.phase === 'selecting')                    return 'login_selecting';
    if (loginState?.phase === 'waiting')                      return 'login_waiting';
    if (connectionStatus.connecting)                          return 'connecting';
    if (connectionStatus.error && !connectionStatus.connected) return 'connection_error';
    if (startupError)                                         return 'startup_error';
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
            provider={bannerInfo?.provider || 'default'}
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
            provider={bannerInfo?.provider || 'default'}
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
              provider={bannerInfo?.provider || "default"}
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
              onFlushQueueAndRun={stableFlushQueueAndRun}
              onCancelPendingQueue={cancelPendingQueue}
              isCollapsed={isCollapsed}

              interactiveInput={interactiveInput}
              onSendInteractiveInput={sendInteractiveInput}
              sessionId={sessionId}
              sideQuestions={sideQuestions}
              sideQuestionNotice={sideQuestionNotice}
              sideQuestionPanelVisible={sideQuestionPanelVisible}
              onHideSideQuestionPanel={hideSideQuestionPanel}

              goalState={goalState}
              goalNotice={goalNotice}

              onClearSideQuestionsHistory={clearSideQuestionsHistory}

              onRemoveSideQuestion={removeSideQuestion}
              onForkSideQuestion={forkSideQuestion}
              quotaUsage={bannerInfo?.quotaUsage ?? null}
              promptQueue={promptQueue}
              todoItems={todoItems}
              todoMessageRanges={todoMessageRanges}
              cacheStatus={cacheStatus}
            />
          </Box>
        </AppProvider>
      );
  }
};
