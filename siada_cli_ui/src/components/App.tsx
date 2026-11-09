import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Box, Text, useApp, useStdout } from '@jrichman/ink';
import Spinner from 'ink-spinner';
import { MainLayout } from './layouts/MainLayout.js';
import { Scrollable } from './common/Scrollable.js';
import { BottomPaneContext } from '../contexts/BottomPaneContext.js';
import { useTerminalSize } from '../hooks/useTerminalSize.js';
import { SessionBrowser } from './SessionBrowser/index.js';
import { PluginManager } from './PluginManager/index.js';
import type { PluginManagerData } from './PluginManager/index.js';
import { LoginSelector, LoginWaiting } from './Login/index.js';
import type { LoginChoice } from './Login/index.js';
import { TaskSelector, TaskItem } from './TaskSelector/index.js';
import { ModelSelector } from './ModelSelector/ModelSelector.js';
import { EffortSelector } from './EffortSelector/EffortSelector.js';
import { ThemeSelector } from './ThemeSelector/index.js';
import type { SideQuestionItem } from './SideQuestion/index.js';
import { useACP } from '../hooks/useACP.js';
import { useThemeVersion } from '../themes/index.js';
import { t, useUiLanguage } from '../i18n/index.js';
import { ClientConfig, Message } from '../types/index.js';
import { getIcons } from '../constants/icons.js';
import { logger } from '../utils/logger.js';
import { useMemoryMonitor } from '../hooks/useMemoryMonitor.js';
import { useBackendExit } from '../hooks/useBackendExit.js';
import { useAdapterEvents } from '../hooks/useAdapterEvents.js';
import { useKeypress } from '../hooks/useKeypress.js';
import { useQuitShortcut } from '../hooks/useQuitShortcut.js';
import { AppProvider } from '../store/context.js';
import { Banner } from './Banner/Banner.js';
import { promptQueueStore } from '../store/promptQueueStore.js';
import { inputRestoreStore } from '../store/inputRestoreStore.js';
import { usePromptDrain } from '../hooks/usePromptDrain.js';
import { usePromptQueueSnapshot } from '../hooks/usePromptQueueSnapshot.js';
import { recordFlicker } from '../utils/flickerMonitor.js';
import { slashCommandService } from '../services/slashCommandService.js';

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
  initialPrompt?: string;
  onExit?: (sessionId: string | null) => void;
}

/**
 * How long the login view waits for a backend reply (ui/loginSuccess,
 * ui/loginError or banner_info) before it gives up: clears the submitting
 * state, shows a retry hint and re-enables input. Without this the view could
 * sit on "Submitting login..." forever when the backend never answers.
 */
const LOGIN_SUBMIT_TIMEOUT_MS = 60_000;

export const App: React.FC<AppProps> = ({ config, initialPrompt, onExit }) => {
  const { exit } = useApp();
  useThemeVersion(); // repaint the whole tree when the theme changes
  useUiLanguage();
  const [isCollapsed, setIsCollapsed] = useState(true); // default compact mode
  const initialPromptSubmittedRef = useRef(false);
  const [isSubmittingLogin, setIsSubmittingLogin] = useState(false);
  const [loginSubmitError, setLoginSubmitError] = useState<string | null>(null);
  const loginSubmitTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [showSessionBrowser, setShowSessionBrowser] = useState(false); // Session browser state
  const [modelSelectorData, setModelSelectorData] = useState<{ models: string[]; currentModel: string; modelNotes?: Record<string, string> } | null>(null);
  const [effortSelectorData, setEffortSelectorData] = useState<import('../hooks/useAdapterEvents.js').EffortSelectorData | null>(null);
  const [themeSelectorData, setThemeSelectorData] = useState<import('../hooks/useAdapterEvents.js').ThemeSelectorData | null>(null);
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
    setSideQuestionNotice(t('用法：/btw <你的问题>', 'Usage: /btw <your question>'));
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
    startupComplete,
    activeStep,
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
    removeMessage,
    client,
    clientRef,
    sessionId,
    todoItems,
    todoMessageRanges,
    cacheStatus,
    goalState,
    subAgentItems,
    subAgentMessages,
  } = useACP(config);

  // Backend pushed a one-shot notice (goal set / verification pass-fail) on
  // this context/goalState update — surface it as the transient flash.
  useEffect(() => {
    if (goalState?.notice) {
      setGoalNotice(goalState.notice);
    } else if (goalState?.goal === null) {
      setGoalNotice(null);
    }
  }, [goalState?.notice, goalState?.goal]);

  // Result identity survives reconnects. Check the current messages rather
  // than a process-local seen set, since restoring history replaces them.
  useEffect(() => {
    const results = [...(goalState?.results ?? []), ...(goalState?.result ? [goalState.result] : [])];
    const existing = new Set(messages.filter(message => message.metadata?.subtype === 'goal_result')
      .map(message => message.id));
    for (const r of results) {
      const identity = r.id ?? JSON.stringify({ createdAt: goalState?.goal?.createdAt, result: r });
      const id = `goal_result_${identity}`;
      if (existing.has(id)) continue;
      existing.add(id);
      addMessage({
        id,
        type: 'system',
        content: '',
        timestamp: r.timestamp ?? new Date().toISOString(),
        author: 'System',
        metadata: {
          subtype: 'goal_result',
          goalResult: r,
        },
      });
    }
  }, [goalState, messages, addMessage]);

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
    setModelSelectorData,
    setEffortSelectorData,
    setThemeSelectorData,
    setTaskSelectorTasks,
    setInstallProgress,
    setPluginManagerData,
    appendSideQuestion,
  });

  const stableSendMessage = useCallback((message: string, imagePaths?: string[]) => {
    const trimmed = message.trim();
    if (/^\/effort(?:\s|$)/.test(trimmed)) {
      sendMessage(message);
      return;
    }
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

    if (slashCommandService.isImmediateCommand(message)) {
      sendMessage(message, imagePaths);
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

  const handleSelectEffort = useCallback(async (level: string) => {
    setEffortSelectorData(null);
    logger.info('Selecting effort', { component: 'App', operation: 'select_effort', level });
    try {
      if (client) await client.sendMessage(`/effort ${level}`);
    } catch (error) {
      logger.error('Failed to set effort', { component: 'App', operation: 'select_effort_error', error });
    }
  }, [client]);

  const handleSelectTheme = useCallback(async (themeName: string) => {
    setThemeSelectorData(null);
    logger.info('Selecting theme', { component: 'App', operation: 'select_theme', themeName });
    try {
      if (client) await client.sendMessage(`/theme ${themeName}`);
    } catch (error) {
      logger.error('Failed to set theme', { component: 'App', operation: 'select_theme_error', error });
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

  const clearLoginSubmitTimer = useCallback(() => {
    if (loginSubmitTimerRef.current) {
      clearTimeout(loginSubmitTimerRef.current);
      loginSubmitTimerRef.current = null;
    }
  }, []);

  const loginRequestId = loginState?.phase === 'selecting' ? loginState.requestId : undefined;

  useEffect(() => {
    if (loginState?.phase !== 'selecting' || loginRequestId) {
      // The login view is going away (success / error / banner): drop the
      // submitting state, watchdog and retry hint. A new selector request
      // must also reset them when notifications share a React render batch.
      setIsSubmittingLogin(false);
      setLoginSubmitError(null);
      clearLoginSubmitTimer();
    }
  }, [loginState?.phase, loginRequestId, clearLoginSubmitTimer]);

  // Never leave a watchdog timer behind on unmount.
  useEffect(() => clearLoginSubmitTimer, [clearLoginSubmitTimer]);

  const handleLoginSelect = useCallback(async (choice: LoginChoice, apiKey?: string) => {
    // During the startup login window, connect() hasn't resolved yet so `client`
    // state is still null.  Use clientRef.current as fallback — it is set
    // immediately after SiadaACPClient is constructed, before waitForReady.
    const activeClient = client ?? clientRef.current;
    const isCancelChoice = choice === 'cancel' || choice === 'skip';
    if (!activeClient || (isSubmittingLogin && !isCancelChoice)) {
      logger.warn('[handleLoginSelect] no active client yet, ignoring login choice', {
        choice,
        clientNull: !client,
        clientRefNull: !clientRef.current,
      });
      return;
    }

    setIsSubmittingLogin(true);
    setLoginSubmitError(null);
    clearLoginSubmitTimer();
    // Watchdog: the backend must answer (ui/loginSuccess, ui/loginError or
    // banner_info) or the login view would stay on "Submitting login..."
    // forever. On timeout, free the UI and let the user retry.
    loginSubmitTimerRef.current = setTimeout(() => {
      loginSubmitTimerRef.current = null;
      setIsSubmittingLogin(false);
      setLoginSubmitError(
        t('登录超时，后端未响应。请重试，或按 Esc 取消。',
          'Login timed out — the backend did not respond. Please retry, or press Esc to cancel.')
      );
      logger.warn('[handleLoginSelect] login submit watchdog fired', {
        choice,
        timeoutMs: LOGIN_SUBMIT_TIMEOUT_MS,
      });
    }, LOGIN_SUBMIT_TIMEOUT_MS);
    try {
      const payload = choice === '3' || choice === '4' ? apiKey : undefined;
      if (loginRequestId) {
        await activeClient.sendLoginChoice(choice, payload, loginRequestId);
      } else {
        await activeClient.sendLoginChoice(choice, payload);
      }
    } catch {
      clearLoginSubmitTimer();
      setIsSubmittingLogin(false);
    }
  }, [client, clientRef, isSubmittingLogin, clearLoginSubmitTimer, loginRequestId]);

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

  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : undefined;
  const modalActive = Boolean(pluginManagerData || modelSelectorData || effortSelectorData ||
    themeSelectorData || taskSelectorTasks !== null || showSessionBrowser || sideQuestionPanelVisible ||
    loginState?.phase === 'selecting' || loginState?.phase === 'waiting');

  const interruptCurrentRun = useCallback(() => {
    const restoreUnansweredInput = lastMessage?.type === 'user';
    if (restoreUnansweredInput) {
      removeMessage(lastMessage.id);
      inputRestoreStore.request(lastMessage.content);
    }
    recordFlicker('ctrl_c_interrupt', 'Ctrl+C: stopExecution + queue clear', {
      messageCount: messages.length, metadata: { restoreUnansweredInput },
    });
    stableStopExecution();
  }, [lastMessage, messages.length, removeMessage, stableStopExecution]);

  const exitApplication = useCallback(() => {
    recordFlicker('ctrl_c_interrupt', 'Ctrl+C (double): exit app', { messageCount: messages.length });
    setPluginManagerData(null);
    setModelSelectorData(null);
    setEffortSelectorData(null);
    setThemeSelectorData(null);
    setTaskSelectorTasks(null);
    setShowSessionBrowser(false);
    onExit?.(sessionId);
    exit();
  }, [exit, messages.length, onExit, sessionId]);

  const quitShortcut = useQuitShortcut({
    running: loading || Boolean(goalState?.verifying) || Boolean(interactiveInput) || promptQueue.length > 0,
    onStop: interruptCurrentRun, onExit: exitApplication, active: !modalActive,
  });

  const handleKeypress = useCallback((key: any) => {
    // MainLayout routes Ctrl+C after local input and detail-view cancellation.
    if (key.ctrl && key.name === 'c' && !modalActive && (!connectionStatus.ready || !bannerInfo)) {
      quitShortcut.onCtrlC();
    }
    if (key.ctrl && key.name === 'o' && !modalActive) {
      setIsCollapsed(prev => {
        recordFlicker('ctrl_o_collapse', `Ctrl+O: toggle collapse mode ${prev} → ${!prev}`, {
          messageCount: messages.length,
        });
        return !prev;
      });
    }
  }, [bannerInfo, connectionStatus.ready, messages.length, modalActive, quitShortcut.onCtrlC]);

  useKeypress(handleKeypress);

  const startupError = messages.find(m =>
    m.metadata?.type === 'startup_error' || (!bannerInfo && m.type === 'error')
  );

  type ViewState =
    | 'connecting' | 'initializing' | 'connection_error' | 'startup_error'
    | 'login_selecting' | 'login_waiting' | 'loading_config'
    | 'plugin_manager' | 'task_selector' | 'model_selector' | 'effort_selector' | 'theme_selector' | 'session_browser' | 'main';

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
    if (effortSelectorData !== null)                          return 'effort_selector';
    if (themeSelectorData !== null)                           return 'theme_selector';
    if (showSessionBrowser)                                   return 'session_browser';
    return 'main';
  })();

  useEffect(() => {
    if (
      initialPromptSubmittedRef.current || !initialPrompt?.trim()
      || viewState !== 'main' || !client || !connectionStatus.connected
      || !connectionStatus.ready || !startupComplete || loading
    ) return;

    // Use the normal submit path, including slash commands, only once per launch.
    initialPromptSubmittedRef.current = true;
    stableSendMessage(initialPrompt);
  }, [
    initialPrompt, viewState, client, connectionStatus.connected,
    connectionStatus.ready, startupComplete, loading, stableSendMessage,
  ]);

  const paneSize = useTerminalSize();
  const paneHeight = Math.max(8, Math.min(viewState === 'effort_selector' ? 12 : 16, paneSize.rows - 5));
  let bottomView: React.ReactNode = null;
  switch (viewState) {
    case 'connecting':
      return <LoadingView message={t('正在连接 siada-cli…', 'Connecting to siada-cli…')}
        footer={t(`工作目录：${config.workingDir}`, `Working directory: ${config.workingDir}`)} />;

    case 'initializing':
      return <LoadingView message={t('正在初始化智能体…', 'Initializing agent…')}
        footer={t('请稍候，智能体正在启动', 'Please wait while the agent starts up')} />;

    case 'connection_error':
      return (
        <ErrorView
          errorIcon={icons.error}
          title={t('连接失败', 'Connection Failed')}
          message={connectionStatus.error ?? ''}
          hint={t('请确认已安装 siada-cli，且 PATH 中包含其所在目录。', 'Make sure siada-cli is installed and accessible in your PATH.')}
          exitHint={t('按 Esc 退出', 'Press ESC to exit')}
        />
      );

    case 'startup_error':
      return (
        <ErrorView
          errorIcon={icons.error}
          title={t('启动失败', 'Startup Error')}
          message={startupError?.content || t('启动时发生未知错误', 'Unknown error during startup')}
          hint={t('请检查配置后重试。', 'Please check your configuration and try again.')}
          exitHint={t('按 Ctrl+C 退出', 'Press Ctrl+C to exit')}
        />
      );

    case 'login_selecting': {
      const s = loginState as Extract<typeof loginState, { phase: 'selecting' }>;
      if (s.cancelable) {
        bottomView = <LoginSelector onSelect={handleLoginSelect} providers={s.providers as any}
          freeTrialModels={s.freeTrialModels}
          cancelable liidDisabled={s.liidDisabled} submitting={isSubmittingLogin} submitError={loginSubmitError} />;
        break;
      }
      return (
        <Box flexDirection="column">
          <Banner
            version={bannerInfo?.version}
            workingDir={bannerInfo?.workingDir || config.workingDir}
            agent={bannerInfo?.agent || 'coder'}
            provider={bannerInfo?.provider || 'default'}
            model={bannerInfo?.model || config.model}
            isCollapsed={isCollapsed}
            showAgentInfo={false}
            interactive
          />
          <Box marginTop={1}>
            <LoginSelector
              onSelect={handleLoginSelect}
              providers={s.providers as any}
              freeTrialModels={s.freeTrialModels}
              cancelable={s.cancelable}
              liidDisabled={s.liidDisabled}
              submitting={isSubmittingLogin}
              submitError={loginSubmitError}
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
            isCollapsed={isCollapsed}
            showAgentInfo={false}
            interactive
          />
          <Box marginTop={1}>
            <LoginWaiting url={s.url} openBrowser={s.openBrowser} />
          </Box>
        </Box>
      );
    }

    case 'loading_config':
      return <LoadingView message={t('正在加载配置…', 'Loading configuration…')} />;

    case 'plugin_manager':
      bottomView = (
        <PluginManager
          data={pluginManagerData!}
          installProgress={installProgress}
          onAction={handlePluginAction}
          onExit={handleClosePluginManager}
        />
      );
      break;

    case 'task_selector':
      bottomView = (
        <TaskSelector
          tasks={taskSelectorTasks!}
          availableRows={paneHeight}
          onSelect={handleSelectTask}
          onExit={handleCloseTaskSelector}
        />
      );
      break;

    case 'model_selector':
      bottomView = (
        <ModelSelector
          models={modelSelectorData!.models}
          currentModel={modelSelectorData!.currentModel}
          modelNotes={modelSelectorData!.modelNotes}
          embedded availableRows={paneHeight}
          onSelect={handleSelectModel}
          onExit={() => setModelSelectorData(null)}
        />
      );
      break;

    case 'effort_selector':
      bottomView = (
        <EffortSelector
          model={effortSelectorData!.model}
          efforts={effortSelectorData!.efforts}
          current={effortSelectorData!.current}
          embedded
          onSelect={handleSelectEffort}
          onExit={() => setEffortSelectorData(null)}
        />
      );
      break;

    case 'theme_selector':
      bottomView = (
        <ThemeSelector
          themes={themeSelectorData!.themes}
          current={themeSelectorData!.current}
          embedded
          onSelect={handleSelectTheme}
          onExit={() => setThemeSelectorData(null)}
        />
      );
      break;

    case 'session_browser':
      bottomView = (
        <SessionBrowser
          projectRoot={config.workingDir}
          onResume={handleResumeSession}
          onExit={handleCloseSessionBrowser}
          currentSessionId={undefined}
        />
      );
      break;

    default:
      break;
  }
  return (
        <AppProvider>
          <Box flexDirection="column" flexShrink={0} flexGrow={0}>
            <MainLayout
              demoPresentation
              fullStatusBar
              bannerInHistory
              demoOverlayHeight={paneHeight}
              demoOverlay={bottomView ? <BottomPaneContext.Provider value={{ ...paneSize, rows: paneHeight }}>
                <Scrollable height={paneHeight} width={paneSize.columns} hasFocus mouseOnly scrollToBottom={false}>
                  {bottomView}
                </Scrollable>
              </BottomPaneContext.Provider> : null}
              version={bannerInfo?.version || "0.0.0"}
              workingDir={bannerInfo?.workingDir || config.workingDir}
              agent={bannerInfo?.agent || "coder"}
              provider={bannerInfo?.provider || "li"}
              model={bannerInfo?.model || config.model}
              reasoningEffort={bannerInfo?.reasoningEffort}
              thinkingEnabled={bannerInfo?.thinkingEnabled}
              messages={messages}
              loading={loading}
              activeStep={activeStep}
              isReady={connectionStatus.ready}
              tokenUsage={tokenUsage}
              onSendMessage={stableSendMessage}
              onAddMessage={stableAddMessage}
              onUpdateMessage={stableUpdateMessage}
              onStopExecution={stableStopExecution}
              onCtrlC={quitShortcut.onCtrlC}
              interruptNotice={quitShortcut.notice}
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
              subAgentItems={subAgentItems}
              subAgentMessages={subAgentMessages}
              cacheStatus={cacheStatus}
            />
          </Box>
        </AppProvider>
      );
};
