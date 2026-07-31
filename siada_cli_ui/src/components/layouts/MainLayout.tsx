/**
 * MainLayout Component
 * Main application layout with static header and dynamic content
 * 
 * LAYOUT STRATEGY:
 * - Uses Ink's <Static> component to render header once
 * - Header is the first item in the static array, always at top
 * - Content area has constrained height to prevent input box being pushed off-screen
 * - Optimized for performance with separated static/dynamic rendering
 * 
 * HEIGHT MANAGEMENT:
 * - Total available: rows - 1 (safe height to prevent flickering)
 * - Header: ~12 rows (banner + info line)
 * - ThinkingIndicator: ~2 rows (when visible)
 * - InputPrompt: ~3 rows (input box with border)
 * - MessageList: Remaining space (constrained with overflow)
 */

import React, { useMemo, useState, useEffect } from 'react';
import { Box, Static, Text } from '@jrichman/ink';
import { AppHeader } from './AppHeader.js';
import { MessageList } from '../Chat/MessageList.js';
import { InputPromptWithWrapUseKPC } from '../Input/InputPromptWithWrapUseKPC.js';
import { ThinkingIndicator } from '../common/ThinkingIndicator.js';
import { ThinkingSpinner } from '../common/ThinkingSpinner.js';

import { SideQuestionPanel } from '../SideQuestion/index.js';
import type { SideQuestionItem } from '../SideQuestion/index.js';
import { PromptQueuePreview } from '../Queue/PromptQueuePreview.js';
import { TodoDetailView } from '../Todo/TodoDetailView.js';
import { GoalStatusBar } from '../Goal/GoalStatusBar.js';
import { Message, PromptQueueItem } from '../../types/index.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { getMaxSafeHeight } from '../../utils/terminalHeight.js';
import { InteractiveInputRequest } from '../../hooks/useACP.js';
import type { TodoItem, TodoMessageRange } from '../../hooks/useAcp/types.js';

export interface MainLayoutProps {
  // Header props
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  prePlanMode?: boolean;
  
  // Content props
  messages: Message[];
  loading?: boolean;
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

/**
 * MainLayout - Single-render header architecture
 * 
 * Layout hierarchy:
 * <Box> (root container)
 *   ├─ <Static> (fixed rendering zone - renders once)
 *   │    └─ AppHeader (Banner + version info) ← Always at top, never re-renders
 *   ├─ MessageList (dynamic message area)
 *   ├─ ThinkingIndicator (when loading)
 *   └─ InputPrompt (input area)
 */
export const MainLayout: React.FC<MainLayoutProps> = React.memo(({
  version = '0.0.0',
  workingDir,
  agent = 'coder',
  provider = 'default',
  model,
  prePlanMode = true,
  messages,
  loading = false,
  isReady = true,
  tokenUsage = null,
  onSendMessage,
  onAddMessage,
  onUpdateMessage,
  onStopExecution,
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
  goalState = null,
  goalNotice = null,
  cacheStatus = null,
}) => {
  const [todoDetailTodo, setTodoDetailTodo] = useState<string | null>(null);
  // Note: alt-screen entry/exit is handled inside TodoDetailView via
  // useInsertionEffect (must run before Ink's first onRender). Don't add
  // a redundant useEffect here — it would fire during layout phase and
  // re-clear the screen AFTER Ink already wrote the first frame, causing
  // a black screen.

  // Panel only mounts when there is history AND the user hasn't hidden it.
  // Hidden ≠ cleared: history is preserved in App state and re-shown on next /btw.
  const showSideQuestionPanel = sideQuestions.length > 0 && sideQuestionPanelVisible;

  // Use reactive terminal size hook that updates on resize events
  const { columns, rows } = useTerminalSize();

  // Memoize placeholder text to avoid recalculating
  const placeholder = useMemo(() => {
    if (!isReady) return 'Agent is initializing...';
    if (loading) return 'Type next message while thinking...';
    return 'Type a message, /command, or @path/to/file ...';
  }, [isReady, loading]);

  // Memoize the header props to prevent unnecessary re-renders
  const headerProps = useMemo(() => ({
    version,
    workingDir,
    agent,
    provider,
    model,
    prePlanMode,
    isCollapsed,
  }), [version, workingDir, agent, provider, model, prePlanMode, isCollapsed]);

  return (
    <Box flexDirection="column" width={columns}
    flexGrow={0}
    flexShrink={0}>
      <Box flexDirection="column"
          flexGrow={0}
    flexShrink={0}>
        {/* Second buffer: TodoDetailView replaces everything when a todo is selected */}
        {todoDetailTodo ? (
          <TodoDetailView
            todo={todoItems.find(t => t.content === todoDetailTodo) ?? { content: todoDetailTodo, status: 'pending' }}
            messages={messages}
            range={todoMessageRanges?.get(todoDetailTodo)}
            terminalWidth={columns}
            onClose={() => setTodoDetailTodo(null)}
          />
        ) : (
          <>
            {/* Message list area with header props passed in */}
            <MessageList
              key={sessionId || 'default'}
              messages={messages}
              headerProps={headerProps}
              terminalWidth={columns}
              isCollapsed={isCollapsed}
            />

            {/* Thinking indicator - shown while loading or while there are queued prompts */}
            {(loading || promptQueue.length > 0) && isReady && !interactiveInput && (
              <Box paddingLeft={1} paddingBottom={1}>
                <ThinkingIndicator active={loading || promptQueue.length > 0} showTime={true} />
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
            {!loading && promptQueue.length === 0 && goalState?.verifying && isReady && !interactiveInput && (
              <Box paddingLeft={1} paddingTop={1} paddingBottom={1} flexDirection="row" gap={1}>
                <ThinkingSpinner active />
                <Text color="yellow">Goal verifying...</Text>
              </Box>
            )}


            {/* Queued prompt preview — shown above input when messages are waiting */}
            <PromptQueuePreview queue={promptQueue} />

            {/* Interactive input prompt banner */}
            {interactiveInput && (
              <Box paddingLeft={1} paddingBottom={0} flexDirection="column">
                <Box>
                  <Text color="yellow" bold>Interactive Input Required</Text>
                </Box>
                <Box>
                  <Text color="white">{interactiveInput.prompt}</Text>
                </Box>
              </Box>
            )}

        {/* /btw side question panel — rendered ABOVE the input box.
            Mount condition: there is at least one /btw item in history AND
            the user hasn't pressed Esc to hide the panel. Pressing Esc just
            hides; the underlying `sideQuestions` history stays in App state
            and is restored the next time a new /btw is submitted. */}
        {showSideQuestionPanel && (
          <Box flexGrow={0} flexShrink={0}>
            <SideQuestionPanel
              items={sideQuestions}
              onHide={onHideSideQuestionPanel ?? (() => {})}
              onClearHistory={onClearSideQuestionsHistory}
              onRemove={onRemoveSideQuestion ?? (() => {})}
              onFork={onForkSideQuestion}
            />
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
        <GoalStatusBar goalState={goalState} width={columns} notice={goalNotice} isCollapsed={isCollapsed} />





            {/* Input box area */}
            <Box flexGrow={0} flexShrink={0}>
              <InputPromptWithWrapUseKPC
                onSubmit={interactiveInput && onSendInteractiveInput
                  ? (value: string) => { onSendInteractiveInput(value); }
                  : onSendMessage}
                onAddMessage={onAddMessage}
                onUpdateMessage={onUpdateMessage}
                onStopExecution={onStopExecution}
                onFlushQueueAndRun={onFlushQueueAndRun}
                onCancelPendingQueue={onCancelPendingQueue}
                disabled={!isReady || showSideQuestionPanel}
                disabledMessage={
                  showSideQuestionPanel
                    ? '/btw side panel is active · Esc to close'
                    : undefined
                }
                loading={loading && !interactiveInput}
                placeholder={interactiveInput
                  ? (interactiveInput.isPassword ? 'Enter password...' : 'Enter input...')
                  : placeholder}
                focus={!showSideQuestionPanel}
                width={columns}
                cwd={workingDir}
                tokenUsage={interactiveInput ? null : tokenUsage}
                model={model}
                quotaUsage={quotaUsage}
                cacheStatus={cacheStatus}
                workingDir={workingDir}
                todoItems={todoItems}
                onTodoSelect={(content) => setTodoDetailTodo(content)}
              />
            </Box>
          </>
        )}

      </Box>
    </Box>
  );
});

MainLayout.displayName = 'MainLayout';
