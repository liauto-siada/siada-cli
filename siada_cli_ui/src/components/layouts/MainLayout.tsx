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

import React, { useMemo } from 'react';
import { Box, Static, Text } from '@jrichman/ink';
import { AppHeader } from './AppHeader.js';
import { MessageList } from '../Chat/MessageList.js';
import { InputPromptWithWrapUseKPC } from '../Input/InputPromptWithWrapUseKPC.js';
import { ThinkingIndicator } from '../common/ThinkingIndicator.js';
import { Message } from '../../types/index.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { getMaxSafeHeight } from '../../utils/terminalHeight.js';
import { InteractiveInputRequest } from '../../hooks/useACP.js';

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
  onSendMessage: (message: string) => void;
  onAddMessage?: (message: Message) => void;
  onUpdateMessage?: (id: string, updates: Partial<Message>) => void;
  onStopExecution?: () => void;
  
  // Interactive input (for commands that need user input like passwords)
  interactiveInput?: InteractiveInputRequest | null;
  onSendInteractiveInput?: (input: string) => Promise<void>;
  
  // Collapse mode
  isCollapsed?: boolean;
  
  // Session ID for tracking session changes
  sessionId?: string | null;

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
  provider = 'li',
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
  isCollapsed = false,
  interactiveInput,
  onSendInteractiveInput,
  sessionId,
}) => {
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
        {/* Message list area with header props passed in */}
        <MessageList 
          key={sessionId || 'default'}  // Force remount when session changes
          messages={messages}
          headerProps={headerProps}
          terminalWidth={columns}  // Pass terminal width for resize handling
          isCollapsed={isCollapsed}  // Pass collapse mode
        />

        {/* Thinking indicator - shown above input when loading (hide when interactive input is active) */}
        {loading && isReady && !interactiveInput && (
          <Box paddingLeft={1} paddingBottom={1}>
            <ThinkingIndicator active={loading} showTime={true} />
          </Box>
        )}

        {/* Interactive input prompt banner - shown when a command needs user input */}
        {interactiveInput && (
          <Box paddingLeft={1} paddingBottom={0} flexDirection="column">
            <Box>
              <Text color="yellow" bold>Interactive Input Required</Text>
            </Box>
            <Box>
              <Text color="white">{interactiveInput.prompt}</Text>
            </Box>
            {/* {interactiveInput.isPassword && (
              <Box>
                <Text dimColor>(input will be sent as password - not displayed)</Text>
              </Box>
            )} */}
          </Box>
        )}

        {/* Input box area - always visible and enabled for async input */}
        <Box flexGrow={0} flexShrink={0}>
          <InputPromptWithWrapUseKPC
            onSubmit={interactiveInput && onSendInteractiveInput 
              ? (value: string) => { onSendInteractiveInput(value); }
              : onSendMessage}
            onAddMessage={onAddMessage}
            onUpdateMessage={onUpdateMessage}
            onStopExecution={onStopExecution}
            disabled={!isReady}
            loading={loading && !interactiveInput}
            placeholder={interactiveInput 
              ? (interactiveInput.isPassword ? 'Enter password...' : 'Enter input...')
              : placeholder}
            focus={true}
            width={columns}
            cwd={workingDir}
            tokenUsage={interactiveInput ? null : tokenUsage}
          />
        </Box>
      </Box>
    </Box>
  );
});

MainLayout.displayName = 'MainLayout';
