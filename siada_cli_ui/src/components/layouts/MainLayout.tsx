/** Bounded conversation history above a measured composer and existing task panels. */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Box, Text, type DOMElement } from '@jrichman/ink';
import { ConversationViewport, conversationBlocks, estimateBlockRows, useMeasuredHeight } from '../Chat/ConversationViewport.js';
import { NativeHistoryOutput } from '../Chat/NativeHistoryOutput.js';
import { useNativeHistory } from '../../hooks/useNativeHistory.js';
import { useNoAltScreen } from '../../contexts/TerminalModeContext.js';
import { InputPromptWithWrapUseKPC } from '../Input/InputPromptWithWrapUseKPC.js';
import { ThinkingIndicator } from '../common/ThinkingIndicator.js';
import { ThinkingSpinner } from '../common/ThinkingSpinner.js';

import { SideQuestionPanel } from '../SideQuestion/index.js';
import type { SideQuestionItem } from '../SideQuestion/index.js';
import { PromptQueuePreview } from '../Queue/PromptQueuePreview.js';
import { TodoDetailView } from '../Todo/TodoDetailView.js';
import { MAX_VISIBLE_TODOS } from '../../utils/todoDisplay.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { SubAgentDetailView } from '../SubAgent/SubAgentDetailView.js';
import { GoalStatusBar } from '../Goal/GoalStatusBar.js';
import { DemoWorkStatus } from './DemoWorkStatus.js';
import { DemoRecordDetail } from './DemoRecordDetail.js';
import { DemoPickerCard } from './DemoPickerCard.js';
import { DemoGoalDetail } from './DemoGoalDetail.js';
import { colors } from '../../utils/colors.js';
import { entriesToMessages } from '../SubAgent/SubAgentDetailView.js';
import { Message, PromptQueueItem } from '../../types/index.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import type { CtrlCContext } from '../../hooks/useQuitShortcut.js';
import type { SelectionSurface } from '../../utils/conversationSelection.js';
import { InteractiveInputRequest } from '../../hooks/useACP.js';
import type { TodoItem, TodoMessageRange, SubAgentItem, SubAgentMessageEntry } from '../../hooks/useAcp/types.js';
import type { ThinkingStep } from '../../constants/phrases.js';
import { PANEL_TIPS } from '../../constants/tips.js';
import { exportConversation, type ExportBannerInfo } from '../../utils/conversationExport.js';
import { BottomPaneContext } from '../../contexts/BottomPaneContext.js';

export interface MainLayoutProps {
  demoOverlay?: React.ReactNode;
  demoOverlayHeight?: number;
  fullStatusBar?: boolean;
  bannerInHistory?: boolean;
  demoPresentation?: boolean;
  // Header props
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  /** Current reasoning effort level (e.g. "low"); rendered next to the model in the status bar. */
  reasoningEffort?: string;
  /** Whether thinking is explicitly disabled via /thinking off; rendered as "model(thinking off)". */
  thinkingEnabled?: boolean | null;

  // Content props
  messages: Message[];
  loading?: boolean;
  /** Current agent activity step while loading — labels the thinking indicator */
  activeStep?: ThinkingStep | null;
  isReady?: boolean;
  tokenUsage?: {
    contextSize: number;
    contextMax: number;
    message: string;
  } | null;
  onSendMessage: (message: string, imagePaths?: string[]) => void;
  onAddMessage?: (message: Message) => void;
  onUpdateMessage?: (id: string, updates: Partial<Message>) => void;
  onStopExecution?: () => void;
  onCtrlC?: (context?: CtrlCContext) => void;
  interruptNotice?: string | null;
  // Esc while busy: interrupt the current run but keep the queue so the backend
  // flushes and runs the queued prompts one-by-one.
  onFlushQueueAndRun?: () => void;
  // Up (with empty input): after popping the queue back into the input box,
  // tell the backend to drop the pending injections so they are not re-run.
  onCancelPendingQueue?: () => void;
  
  // Interactive input (for commands that need user input like passwords)

  interactiveInput?: InteractiveInputRequest | null;
  onSendInteractiveInput?: (input: string) => Promise<void>;
  
  // Collapse mode
  isCollapsed?: boolean;
  
  // Session ID for tracking session changes
  sessionId?: string | null;

  // Quota usage percentage (0-100), null if not available
  quotaUsage?: string | null;
  // /btw side question panel
  sideQuestions?: SideQuestionItem[];
  /**
   * Transient one-line hint shown above the input box (e.g. blank /btw usage).
   * Not part of `sideQuestions` history; rendered ephemerally and auto-cleared
   * by the parent. When null/empty nothing is rendered.
   */
  sideQuestionNotice?: string | null;

  /**
   * Whether the /btw side-question panel is currently rendered. Visibility
   * is decoupled from history: when false the panel is hidden, but the
   * `sideQuestions` array (history) is preserved so a later /btw can
   * reopen the panel and show everything again.
   */
  sideQuestionPanelVisible?: boolean;
  /**
   * Esc handler for the side-question panel — hides the panel without
   * clearing the existing /btw history. The next /btw will reopen it.
   */
  onHideSideQuestionPanel?: () => void;
  onClearSideQuestionsHistory?: () => void;
  onRemoveSideQuestion?: (id: string) => void;
  onForkSideQuestion?: (item: SideQuestionItem) => void;

  // Prompt queue for preview display
  promptQueue?: PromptQueueItem[];
  // Todo tracking
  todoItems?: TodoItem[];
  todoMessageRanges?: Map<string, TodoMessageRange>;
  subAgentItems?: SubAgentItem[];
  subAgentMessages?: Map<string, SubAgentMessageEntry[]>;
  // Cache status data
  cacheStatus?: import('../../hooks/useAcp/types.js').CacheStatusData | null;
  // /goal standing goal + live verification state
  goalState?: import('../../hooks/useAcp/types.js').GoalState | null;
  /**
   * Transient one-line flash for /goal set / pass-fail results. Same
   * ephemeral-and-auto-cleared contract as sideQuestionNotice.
   */
  goalNotice?: string | null;
}

export const MainLayout: React.FC<MainLayoutProps> = React.memo(({
  version = '0.0.0',
  workingDir,
  agent = 'coder',
  provider = 'default',
  model,
  reasoningEffort,
  thinkingEnabled,
  messages,
  loading = false,
  activeStep = null,
  isReady = true,
  tokenUsage = null,
  onSendMessage,
  onAddMessage,
  onUpdateMessage,
  onStopExecution,
  onCtrlC,
  interruptNotice,
  onFlushQueueAndRun,
  onCancelPendingQueue,
  isCollapsed = false,

  interactiveInput,
  onSendInteractiveInput,
  sessionId,
  sideQuestions = [],
  sideQuestionNotice = null,
  sideQuestionPanelVisible = false,

  onHideSideQuestionPanel,
  onClearSideQuestionsHistory,
  onRemoveSideQuestion,
  onForkSideQuestion,
  quotaUsage = null,
  promptQueue = [],
  todoItems = [],
  todoMessageRanges,
  subAgentItems = [],
  subAgentMessages,
  goalState = null,
  goalNotice = null,
  cacheStatus = null,
  demoPresentation = false,
  demoOverlay,
  demoOverlayHeight,
  fullStatusBar,
  bannerInHistory = false,
}) => {
  const uiLanguage = useUiLanguage();
  const [todoDetailTodo, setTodoDetailTodo] = useState<string | null>(null);
  const [subAgentDetailId, setSubAgentDetailId] = useState<string | null>(null);
  const [historyDirectoryOpen, setHistoryDirectoryOpen] = useState(false);
  const [demoWorkSection, setDemoWorkSection] = useState<string | null>(null);
  const [demoStatusFocus, setDemoStatusFocus] = useState<string | null>(null);
  const [demoCompletion, setDemoCompletion] = useState<React.ReactNode | null>(null);
  const [completionDialog, setCompletionDialog] = useState(false);
  const [completionDialogHeight, setCompletionDialogHeight] = useState<number | undefined>(undefined);
  const [inputTip, setInputTip] = useState<string | null>(null);
  const [aboveHoverTip, setAboveHoverTip] = useState<string | null>(null);
  const [belowHoverTip, setBelowHoverTip] = useState<string | null>(null);
  const handleAboveHoverTip = useCallback((tip: string | null) => setAboveHoverTip(tip), []);
  const handleBelowHoverTip = useCallback((tip: string | null) => setBelowHoverTip(tip), []);
  const handleInputTip = useCallback((tip: string | null) => setInputTip(tip), []);
  const handleCompletion = useCallback((content: React.ReactNode | null, dialog = false, dialogHeight?: number) => {
    setDemoCompletion(content);
    setCompletionDialog(dialog);
    setCompletionDialogHeight(dialogHeight);
  }, []);
  const demoWorkOpen = demoWorkSection !== null;
  useKeypress(key => {
    if (!onCtrlC || !key.ctrl || key.name !== 'c' || (!todoDetailTodo && !subAgentDetailId)) return;
    setTodoDetailTodo(null);
    setSubAgentDetailId(null);
    onCtrlC('modal');
  });

  // Panel only mounts when there is history AND the user hasn't hidden it.
  // Hidden ≠ cleared: history is preserved in App state and re-shown on next /btw.
  const showSideQuestionPanel = sideQuestions.length > 0 && sideQuestionPanelVisible;

  // Use reactive terminal size hook that updates on resize events
  const { columns, rows } = useTerminalSize();
  const [composerRef, composerHeight] = useMeasuredHeight();
  const noAltScreen = useNoAltScreen();
  const [demoInputRef, demoInputHeight] = useMeasuredHeight();
  const [demoPreludeRef, demoPreludeHeight] = useMeasuredHeight(0);
  const [sidePanelRef, sidePanelHeight] = useMeasuredHeight(0);
  const composerSelection = useRef<SelectionSurface>({ root: null });
  const completionOverlayRef = useRef<DOMElement | null>(null);
  const demoTodos = todoItems.some(item => item.status !== 'completed') ? todoItems : [];
  const demoGoal = goalState;
  const todoPreviewHeight = Number(demoTodos.length > 0) + Math.min(MAX_VISIBLE_TODOS, demoTodos.length);
  const demoTreeHeight = Number(Boolean(demoGoal?.goal || goalNotice)) + todoPreviewHeight +
    2 * Number(subAgentItems.length > 0);
  const demoAboveHeight = Number(Boolean(demoGoal?.goal || goalNotice)) + todoPreviewHeight;
  // A clipped composer cannot measure its intrinsic height; reserve its known
  // input and panel chrome independently so shrinking never clips the prompt.
  const nativeComposerRows = Math.max(composerHeight,
    Math.max(6, demoInputHeight + 2) + demoTreeHeight + demoPreludeHeight + sidePanelHeight);
  const nativeHistory = useNativeHistory(noAltScreen, messages, sessionId || workingDir,
    loading, columns, Math.max(4, rows - 2 - nativeComposerRows - 3), isReady);
  const visibleMessages = nativeHistory.pending;
  const nativeRows = noAltScreen ? conversationBlocks(visibleMessages, demoPresentation)
    .reduce((total, block) => total + estimateBlockRows(block, columns, isCollapsed), 0) : 0;
  const nativeOverlay = demoOverlay || demoWorkOpen || subAgentDetailId || todoDetailTodo ||
    demoCompletion || showSideQuestionPanel;
  // The trailing newline counts toward Ink's clear-screen threshold in main-screen mode.
  const safeHeight = noAltScreen
    ? Math.max(1, Math.min(rows - 2, nativeOverlay ? rows - 2
      : Math.max(7, nativeRows + nativeComposerRows + 3)))
    : Math.max(1, rows - 1);
  const demoPanelHeight = Math.max(6, Math.min(10, Math.floor(rows / 2)));
  // Keep room for the input chrome, status bar, and conversation in short terminals.
  const inputMaxLines = Math.max(1, Math.min(10, Math.floor(rows / 2),
    safeHeight - demoTreeHeight - demoPreludeHeight - sidePanelHeight - 8));
  const maximumComposerHeight = Math.max(4, safeHeight - 3);
  // The footer hint must track the actual position of the bottom-anchored input.
  const viewportComposerHeight = Math.min(maximumComposerHeight, Math.max(4, composerHeight));
  const preludeHeightLimit = demoPresentation
    ? Math.max(0, Math.min(Math.floor(rows / 3),
        maximumComposerHeight - Math.max(4, demoInputHeight) - demoTreeHeight - sidePanelHeight - 1))
    : Math.max(2, Math.floor(rows / 3));
  const sideQuestionHeight = Math.max(3, Math.min(17, Math.floor(rows / 2),
    safeHeight - Math.max(5, demoInputHeight) - demoTreeHeight - demoPreludeHeight - 4));
  const coveredHeight = demoOverlay ? demoOverlayHeight ?? demoPanelHeight
    : demoWorkOpen || subAgentDetailId || todoDetailTodo ? demoPanelHeight
    : demoCompletion ? completionDialog ? Math.min(16, rows - 5)
      : Math.max(5, demoInputHeight) + 2 * Number(subAgentItems.length > 0) + demoAboveHeight +
        Math.min(8, Math.max(3, safeHeight - viewportComposerHeight))
    : 0;

  // /export handler: reads the LATEST messages/workingDir/onAddMessage through
  // refs so the callback identity stays stable and the memoized InputPrompt
  // does not re-render on every message update.
  const exportCollapsedRef = useRef<ReadonlyMap<string, boolean>>(new Map());
  const exportStateRef = useRef<{
    messages: Message[];
    workingDir: string;
    onAddMessage?: (message: Message) => void;
    banner?: ExportBannerInfo;
    columns: number;
    presentation: boolean;
    isCollapsed: boolean;
  }>({ messages, workingDir, onAddMessage, banner: { workingDir }, columns: 80, presentation: false, isCollapsed });
  exportStateRef.current = {
    messages,
    workingDir,
    onAddMessage,
    banner: demoPresentation && !bannerInHistory ? undefined
      : { version, workingDir, agent, provider, model, isCollapsed, quotaUsage },
    columns,
    presentation: demoPresentation,
    isCollapsed,
  };

  const handleExport = useCallback(async (filename: string) => {
    const { messages: currentMessages, workingDir: currentWorkingDir, onAddMessage: addMessage, banner, columns, presentation, isCollapsed } =
      exportStateRef.current;
    const result = await exportConversation(currentMessages, currentWorkingDir, filename, banner, columns, {
      presentation, isCollapsed, collapsedOverrides: new Map(exportCollapsedRef.current),
    });
    addMessage?.({
      id: `export-${Date.now()}`,
      type: result.success ? 'system' : 'error',
      content: result.message,
      timestamp: new Date().toISOString(),
      author: 'System',
    });
  }, []);

  // Memoize placeholder text to avoid recalculating
  const placeholder = useMemo(() => {
    if (!isReady) return t('正在初始化智能体…', 'Agent is initializing…');
    if (demoPresentation && columns < 60) return loading
      ? t('输入下一条消息…', 'Type next message…') : t('输入消息…', 'Type a message…');
    if (loading) return t('思考中，可输入下一条消息…', 'Type next message while thinking…');
    return t('输入消息、/命令或 @文件路径…', 'Type a message, /command, or @path/to/file…');
  }, [isReady, loading, demoPresentation, columns, uiLanguage]);

  return (
    <>
    {noAltScreen && <NativeHistoryOutput chunks={nativeHistory.chunks} width={columns}
      isCollapsed={isCollapsed} presentation={demoPresentation} ready={isReady}
      banner={{ version, workingDir, agent, provider, model, isCollapsed, quotaUsage }} />}
    <Box flexDirection="column" width={columns}
    flexGrow={0}
    flexShrink={0} height={safeHeight} overflow="hidden">
      <Box flexDirection="column"
          flexGrow={0}
    flexShrink={0} height={safeHeight}>
        {/* Second buffer: SubAgentDetailView / TodoDetailView replaces everything when selected */}
        {!demoPresentation && subAgentDetailId ? (
          <SubAgentDetailView
            item={subAgentItems.find(i => i.id === subAgentDetailId) ?? { id: subAgentDetailId, title: subAgentDetailId, status: 'running' }}
            entries={subAgentMessages?.get(subAgentDetailId) ?? []}
            terminalWidth={columns}
            onClose={() => setSubAgentDetailId(null)}
          />
        ) : !demoPresentation && todoDetailTodo ? (
          <TodoDetailView
            todo={todoItems.find(t => t.content === todoDetailTodo) ?? { content: todoDetailTodo, status: 'pending' }}
            messages={messages}
            range={todoMessageRanges?.get(todoDetailTodo)}
            terminalWidth={columns}
            onClose={() => setTodoDetailTodo(null)}
            embedded
          />
        ) : (
          <>
            <Box height={Math.max(3, safeHeight - viewportComposerHeight)} flexDirection="column" flexShrink={0}>
            <ConversationViewport
              key={sessionId || 'default'}
              messages={visibleMessages}
              collapsedStateRef={exportCollapsedRef}
              width={columns}
              height={Math.max(3, safeHeight - Math.max(viewportComposerHeight, coveredHeight))}
              bannerProps={noAltScreen || demoPresentation && !bannerInHistory ? undefined : { version, workingDir, agent, provider, model, isCollapsed, quotaUsage }}
              presentation={demoPresentation}
              footerOffset={demoPresentation && !coveredHeight ? demoAboveHeight + demoPreludeHeight + sidePanelHeight + 1 : 0}
              keepMouseTracking
              mouseScrollBottom={coveredHeight ? safeHeight - coveredHeight : undefined}
              activityLabel={demoPresentation && (loading || promptQueue.length > 0) && !interactiveInput
                ? activeStep === 'tool_execution' ? t('正在执行工具…', 'Executing tools…')
                  : activeStep === 'compaction' ? t('正在压缩上下文…', 'Compacting context…') : t('正在思考…', 'Thinking…')
                : undefined}
              isCollapsed={isCollapsed}
              active={!showSideQuestionPanel && !interactiveInput && !demoOverlay && !demoWorkOpen && !subAgentDetailId && !todoDetailTodo && !demoCompletion}
              mouseActive={!showSideQuestionPanel && !demoOverlay && !demoWorkOpen && !subAgentDetailId && !todoDetailTodo && !(demoCompletion && completionDialog)}
              mouseOverlayRef={completionOverlayRef}
              composerActive={isReady && !showSideQuestionPanel && !historyDirectoryOpen && !demoOverlay && !demoWorkOpen && !subAgentDetailId && !todoDetailTodo}
              onDirectoryChange={setHistoryDirectoryOpen}
              onCtrlC={onCtrlC}
              interruptNotice={interruptNotice}
              inputTip={inputTip}
              externalHoverTip={aboveHoverTip || belowHoverTip}
              composerSelection={composerSelection}
            />
            </Box>
            {/* Anchor input independently of history, including measurement-transition frames. */}
            <Box position="absolute" width={columns} height={safeHeight}
              flexDirection="column" justifyContent="flex-end">
            <Box ref={composerRef} width={columns} flexDirection="column" flexShrink={0}
              maxHeight={maximumComposerHeight} justifyContent="flex-end" overflow="hidden">
            <Box ref={demoPresentation ? demoPreludeRef : undefined} flexDirection="column"
              maxHeight={preludeHeightLimit} opaque overflowY="scroll"
              scrollbarStyle="thin" scrollbarThumbColor={colors.gray[500]} flexShrink={0}>
            {/* Thinking indicator - shown while loading or while there are queued prompts.
                activeStep (Model Reasoning / Tool Execution / System Processing /
                Context Compaction) tells the user which phase the agent is in. */}
            {!demoPresentation && (loading || promptQueue.length > 0) && isReady && !interactiveInput && (
              <Box paddingLeft={1} paddingBottom={1}>
                <ThinkingIndicator active={loading || promptQueue.length > 0} showTime={true} step={loading ? activeStep : null} />
              </Box>
            )}

            {/* Goal verification indicator — lives in the EXACT SAME slot as
                the ThinkingIndicator above (same position, same left
                padding), just driven by an independent goalState.verifying
                flag instead of `loading`. Goal verification runs AFTER the
                main turn's response has already landed (loading has gone
                back to false by then), so it needs its own animation here
                rather than piggybacking on the block above. Mutually
                exclusive with it — only one of the two ever shows at once,
                so the spinner never jumps between two different rows. */}
            {!demoPresentation && !loading && promptQueue.length === 0 && goalState?.verifying && isReady && !interactiveInput && (
              <Box paddingLeft={1} paddingTop={1} paddingBottom={1} flexDirection="row" gap={1}>
                <ThinkingSpinner active />
                <Text color="yellow">{t('正在验证目标…', 'Goal verifying…')}</Text>
              </Box>
            )}


            {/* Queued prompt preview — shown above input when messages are waiting */}
            <PromptQueuePreview queue={promptQueue} />

            {/* Interactive input prompt banner */}
            {interactiveInput && (
              <Box paddingLeft={1} paddingBottom={0} flexDirection="column">
                <Box>
                  <Text color="yellow" bold>{t('需要你输入', 'Interactive Input Required')}</Text>
                </Box>
                <Box>
                  {/* The prompt is body text: leave the color to the terminal's
                      own foreground so any palette keeps it readable. */}
                  <Text>{interactiveInput.prompt}</Text>
                </Box>
              </Box>
            )}

        {/* Transient /btw notice (e.g. blank /btw usage hint). Rendered above
            the input box and auto-cleared by the parent; never part of the
            side-question history list and does not take over the keyboard. */}
        {sideQuestionNotice && !showSideQuestionPanel && (
          <Box paddingLeft={1}>
            <Text color="gray">{sideQuestionNotice}</Text>
          </Box>
        )}

        {/* Persistent /goal status bar. The transient /goal notice (set
            confirmation, pass/fail flash — same ephemeral, auto-cleared
            contract as sideQuestionNotice above) is rendered by
            GoalStatusBar itself, on the SAME row as the status label
            (left-aligned purple "●" bullet + gray text vs. the right-
            aligned status label), instead of stacking as a separate line
            below it. */}
        {!demoPresentation && <GoalStatusBar goalState={goalState} width={columns} notice={goalNotice} isCollapsed={isCollapsed} />}
            </Box>
            {/* Keep /btw outside the prelude clip and include it in the footer budget. */}
            <Box ref={sidePanelRef} flexDirection="column" flexShrink={0}>
              {showSideQuestionPanel && <SideQuestionPanel
                height={sideQuestionHeight}
                items={sideQuestions}
                onHide={onHideSideQuestionPanel ?? (() => {})}
                onClearHistory={onClearSideQuestionsHistory}
                onRemove={onRemoveSideQuestion ?? (() => {})}
                onFork={onForkSideQuestion}
              />}
            </Box>
            {demoPresentation && <Box height={demoAboveHeight} flexShrink={0} opaque overflow="hidden">
              {!demoCompletion && !demoWorkOpen && !demoOverlay && !subAgentDetailId && !todoDetailTodo &&
              <DemoWorkStatus goalState={demoGoal} goalNotice={goalNotice} tasks={demoTodos} agents={subAgentItems}
              placement="above"
              width={columns} rows={rows} onTask={setTodoDetailTodo} onAgent={setSubAgentDetailId}
              expanded={demoWorkSection} onExpandedChange={setDemoWorkSection}
              focusedSection={demoStatusFocus} onFocusChange={setDemoStatusFocus}
              onHoverTipChange={handleAboveHoverTip}
              active={!demoWorkSection && !subAgentDetailId && !todoDetailTodo && !demoOverlay} />}
            </Box>}
            {demoPresentation && <Box height={1} flexShrink={0} />}
            {/* Input box area */}
            <Box ref={demoPresentation ? demoInputRef : undefined} flexGrow={0} flexShrink={0}>
              <InputPromptWithWrapUseKPC
                onSubmit={interactiveInput && onSendInteractiveInput
                  ? (value: string) => { onSendInteractiveInput(value); }
                  : onSendMessage}
                onExport={handleExport}
                onAddMessage={onAddMessage}
                onUpdateMessage={onUpdateMessage}
                onStopExecution={onStopExecution}
                onCtrlC={onCtrlC}
                onFlushQueueAndRun={onFlushQueueAndRun}
                onCancelPendingQueue={onCancelPendingQueue}
                disabled={!isReady || showSideQuestionPanel}
                disabledMessage={
                  showSideQuestionPanel
                    ? PANEL_TIPS.sideQuestionActive
                    : undefined
                }
                loading={loading && !interactiveInput}
                placeholder={interactiveInput
                  ? (interactiveInput.isPassword ? t('请输入密码…', 'Enter password…') : t('请输入内容…', 'Enter input…'))
                  : placeholder}
                focus={!showSideQuestionPanel && !historyDirectoryOpen &&
                  (demoPresentation || !demoOverlay && !demoWorkOpen)}
                interactionActive={!demoOverlay && !demoWorkOpen && !subAgentDetailId && !todoDetailTodo && !demoStatusFocus}
                onDemoFocusStatus={demoPresentation ? () => setDemoStatusFocus(demoGoal?.goal ? 'goal'
                  : demoTodos.length ? 'tasks' : subAgentItems.length ? 'agents' : null) : undefined}
                maxLines={inputMaxLines}
                conversationNavigation={!noAltScreen}
                demoPresentation={demoPresentation}
                fullStatusBar={fullStatusBar}
                onDemoCompletion={demoPresentation ? handleCompletion : undefined}
                onTipChange={handleInputTip}
                selectionSurface={composerSelection}
                selectionRootOverride={demoPresentation ? composerRef : undefined}
                width={columns}
                cwd={workingDir}
                tokenUsage={interactiveInput ? null : tokenUsage}
                model={model}
                agent={agent}
                sessionId={sessionId}
                reasoningEffort={reasoningEffort}
                thinkingEnabled={thinkingEnabled}
                quotaUsage={quotaUsage}
                cacheStatus={cacheStatus}
                workingDir={workingDir}
                todoItems={todoItems}
                onTodoSelect={(content) => setTodoDetailTodo(content)}
                subAgentItems={subAgentItems}
                onSubAgentSelect={(id) => setSubAgentDetailId(id)}
              />
            </Box>
            {demoPresentation && <Box height={2 * Number(subAgentItems.length > 0)} flexShrink={0} opaque overflow="hidden">
              {!demoWorkOpen && !demoOverlay && !subAgentDetailId && !todoDetailTodo &&
                <DemoWorkStatus goalState={demoGoal} goalNotice={goalNotice} tasks={demoTodos} agents={subAgentItems} placement="below"
                  width={columns} rows={rows} onTask={setTodoDetailTodo} onAgent={setSubAgentDetailId}
                  expanded={demoWorkSection} onExpandedChange={setDemoWorkSection}
                  onHoverTipChange={handleBelowHoverTip}
                  focusedSection={demoStatusFocus} onFocusChange={setDemoStatusFocus} />}
            </Box>}
            </Box>
            </Box>
          </>
        )}

      </Box>
      {demoCompletion && completionDialog && !demoOverlay && <Box position="absolute" width={columns}
        height={safeHeight} flexDirection="column" justifyContent="flex-end">
        <Box width={columns} height={Math.min(completionDialogHeight ?? 16, rows - 5)} backgroundColor={colors.content.surface}>
          <BottomPaneContext.Provider value={{ columns, rows: Math.min(completionDialogHeight ?? 16, rows - 5) }}>
            {demoCompletion}
          </BottomPaneContext.Provider>
        </Box>
      </Box>}
      {demoCompletion && !completionDialog && !demoOverlay && !demoWorkOpen && <Box position="absolute" width={columns}
        height={safeHeight} flexDirection="column" justifyContent="flex-end"
        paddingBottom={Math.max(5, demoInputHeight) + 2 * Number(subAgentItems.length > 0)}>
        <Box ref={completionOverlayRef} width={columns} backgroundColor={colors.content.surface} flexDirection="column">
          <DemoWorkStatus goalState={demoGoal} goalNotice={goalNotice} tasks={demoTodos} agents={subAgentItems}
            placement="above"
            width={columns} rows={rows} onTask={setTodoDetailTodo} onAgent={setSubAgentDetailId}
            expanded={demoWorkSection} onExpandedChange={setDemoWorkSection}
            focusedSection={demoStatusFocus} onFocusChange={setDemoStatusFocus} active={false} />
        <Box width={columns} maxHeight={Math.min(8, Math.max(3, safeHeight - viewportComposerHeight))}
          flexDirection="column" justifyContent="flex-end" backgroundColor={colors.content.surface} overflowY="hidden">
          {demoCompletion}
        </Box>
        </Box>
      </Box>}
      {demoPresentation && (demoWorkSection || subAgentDetailId || todoDetailTodo) && <Box position="absolute"
        width={columns} height={safeHeight} flexDirection="column" justifyContent="flex-end">
        <Box height={demoPanelHeight} width={columns} flexDirection="column" backgroundColor={colors.content.surface}>
        {subAgentDetailId || todoDetailTodo ? <DemoRecordDetail width={columns} rows={demoPanelHeight + 1}
          title={subAgentDetailId ? `Agent · ${subAgentItems.find(item => item.id === subAgentDetailId)?.title ?? subAgentDetailId}`
            : `Task · ${todoDetailTodo}`}
          summary={subAgentDetailId ? subAgentItems.find(item => item.id === subAgentDetailId)?.summary : t('任务执行记录', 'Task execution record')}
          messages={subAgentDetailId ? entriesToMessages(subAgentDetailId, subAgentMessages?.get(subAgentDetailId) ?? [])
            : messages.slice(todoMessageRanges?.get(todoDetailTodo!)?.startIdx ?? 0,
              todoMessageRanges?.get(todoDetailTodo!)?.endIdx ?? messages.length)}
          onClose={() => { setTodoDetailTodo(null); setSubAgentDetailId(null); }} />
          : demoWorkSection === 'goal' ? <DemoGoalDetail state={goalState} width={columns} height={demoPanelHeight}
            onClose={() => { setDemoWorkSection(null); setDemoStatusFocus(null); }} />
          : <DemoPickerCard title={demoWorkSection === 'tasks' ? t('Todo · 待办清单', 'Todo · Task list') : t('Agents · 子智能体', 'Agents · Sub agents')}
            pageHeight={demoPanelHeight}
            items={demoWorkSection === 'tasks' ? todoItems.map(item => `${item.content} · ${item.status}`)
                : subAgentItems.map(item => `${item.title} · ${item.status}${item.summary ? ` · ${item.summary}` : ''}`)}
            onSelect={(_value, index) => {
              if (demoWorkSection === 'agents') setSubAgentDetailId(subAgentItems[index]?.id ?? null);
            }}
            inspectOnly={demoWorkSection === 'tasks'}
            onClose={() => { setDemoWorkSection(null); setDemoStatusFocus(null); }} />}
        </Box>
      </Box>}
      {demoOverlay && <Box position="absolute" width={columns} height={safeHeight}
        flexDirection="column" justifyContent="flex-end">
        <Box height={demoOverlayHeight ?? demoPanelHeight} width={columns} flexDirection="column" backgroundColor={colors.content.surface}
          overflowY="hidden">{demoOverlay}</Box>
      </Box>}
    </Box>
    </>
  );
});

MainLayout.displayName = 'MainLayout';
