/**
 * Message Component
 * Displays a single message in the chat
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import stringWidth from 'string-width';
import { Message as MessageType } from '../../types/index.js';
import { MAX_TEXT_LENGTH } from '../../constants/limits.js';
import { getIcons } from '../../constants/icons.js';
import { truncateByLines, truncateByJSONLines } from '../../utils/contentTruncator.js';
import { MarkdownText } from '../common/MarkdownText.js';
import { ShellOutput } from '../Shell/ShellOutput.js';
import { parseToolCall } from '../../utils/toolCallParser.js';
import { FileChangeSetView } from '../diff/FileChangeSetView.js';
import { ToolHeading } from './ToolHeading.js';
import { CommandView, parseCommandContent } from './CommandView.js';
import { ToolPromptView } from './ToolPromptView.js';
import { TodoPlanView } from './TodoPlanView.js';
import { parseTodoWriteContent } from '../../utils/todoWrite.js';
import { parseApplyPatchContent, parseFileEditContent, getSimplePatch } from '../../utils/diff.js';
import { formatElapsedShort } from '../../utils/formatter.js';
import { getActiveTheme, useThemeVersion } from '../../themes/index.js';
import { colors } from '../../utils/colors.js';



export interface MessageProps {
  message: MessageType;
  isNewGroup?: boolean;        // Indicates whether this is a new group (group_key has changed)
  disableTruncation?: boolean; // When true, render full content without truncation (used for static history)
  isCollapsed?: boolean;       // When true, compact non-edit tool calls
}

const MessageInternal: React.FC<MessageProps> = ({ message, isNewGroup = true, disableTruncation = false, isCollapsed = false }) => {
  useThemeVersion(); // repaint on theme change (React.memo blocks prop-driven re-renders)
  const icons = getIcons();

  const getColor = (): string | undefined => {
    switch (message.type) {
      case 'user':
        return 'gray';
      case 'agent':
        return colors.agent;
      case 'system':
        return colors.warning;
      case 'error':
        return colors.error;
      case 'tool':
        return colors.tool;
      default:
        // Unknown types fall back to the terminal's own foreground, which is
        // guaranteed to contrast with whatever palette the user runs.
        return undefined;
    }
  };

  const getIcon = (): string => {
    switch (message.type) {
      case 'user':
        return '>';
      case 'agent':
        return icons.agent;
      case 'system':
        return icons.system;
      case 'error':
        return icons.error;
      case 'tool':
        return icons.tool;
      default:
        return icons.bullet;
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  // Check if this is a block message (multi-line formatted output from siada-cli)
  const isBlockMessage = message.metadata?.blockType !== undefined;
  const blockType = message.metadata?.blockType as string | undefined;
  const subtype = message.metadata?.subtype as string | undefined;

  // Check message subtypes
  const isThinking = subtype === 'thinking';
  const isToolUse = subtype === 'tool_use';
  const isProcess = subtype === 'process';
  const isAnswer = subtype === 'answer';
  const isErrorBox = subtype === 'error_box';  // 🔴 New error box subtype
  const isShell = subtype === 'shell';         // 🔵 Shell execution subtype
  const isGoalResult = subtype === 'goal_result'; // 🎯 /goal verifier pass/fail summary


  // Truncate content if too long
  // Use line-based truncation FIRST (more effective for Terminal.app)
  // Calculate dynamic max lines based on terminal height
  // Note: process is a global Node.js object, available in runtime but needs type declaration
  const terminalHeight = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.rows) || 24;
  const terminalWidth = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.columns) || 80;
  // Keep the pending (dynamic) message strictly shorter than the terminal so
  // the whole dynamic area (message + spinner/queue/panels ~14 rows + input
  // box) stays below stdout.rows. Once Ink's dynamic output height reaches
  // the terminal row count, the kernel rewrites the ENTIRE screen
  // (clearTerminal + full static history) on every frame — the worst flicker
  // path, and not fixable by DEC 2026 on terminals that lack it (Terminal.app).
  const dynamicMaxLines = Math.max(Math.min(Math.floor(terminalHeight / 2), terminalHeight - 14), 5);

  const originalContent = message.content ?? '';
  let safeContent = originalContent;
  let hiddenLinesCount = 0;

  if (!disableTruncation) {
    // Use 'both' mode to keep first 4 lines + last lines
    let lineResult = truncateByLines(originalContent, dynamicMaxLines, 'both');

    // 🔥 Smart JSON truncation: Check if content is likely JSON and would exceed terminal width
    // If estimated lines (content.length / terminalWidth) > dynamicMaxLines + 2, use JSON truncation
    const estimatedLines = Math.ceil(lineResult.content.length / terminalWidth);
    if (estimatedLines > dynamicMaxLines + 2) {
      // Try JSON truncation for better formatting
      try {
        JSON.parse(originalContent); // Test if it's valid JSON
        lineResult = truncateByJSONLines(originalContent, dynamicMaxLines, 'both');
      } catch {
        // Not JSON, keep the regular truncation result
      }
    }

    // Then apply byte-based truncation as backup
    safeContent = lineResult.content.length > MAX_TEXT_LENGTH
      ? lineResult.content.substring(0, MAX_TEXT_LENGTH) + '\n... [Content truncated due to length]'
      : lineResult.content;

    hiddenLinesCount = lineResult.hiddenLines;
  }

  // For shell execution messages, render using ShellOutput
  if (isShell) {
    const shellExecution = message.metadata?.shellExecution;

    if (!shellExecution) {
      return null;
    }

    return (
      <Box marginBottom={1}>
        <ShellOutput
          command={shellExecution.command}
          executing={shellExecution.executing}
          stdout={shellExecution.stdout}
          stderr={shellExecution.stderr}
          exitCode={shellExecution.exitCode}
          duration={shellExecution.duration}
          isBinary={shellExecution.isBinary}
          error={shellExecution.error}
          // disableTruncation=true in staticGroups: truncation handled at outer level
          disableTruncation={disableTruncation}
        />
      </Box>
    );
  }

  // For thinking messages, render in a box matching tool_use style
  if (isThinking) {
    // Strip markers and leading whitespace (some models like GLM send "\n" as reasoning content,
    // and the backend prepends "\nTHINKING: \n" to the first delta)
    const cleanContent = safeContent
      .replace(/^[\s▶►]*\*{0,2}THINKING\*{0,2}:\s*/i, '')
      .replace(/^[\s▶►]*\*{0,2}THINKING\*{0,2}\s*/i, '')
      .replace(/^\s+/, '')
      .trim();

    if (cleanContent.length === 0) return null;

    // 🔥 Compact mode: show only first line summary
    if (isCollapsed) {
      // Extract first non-empty line
      const lines = cleanContent.split('\n');
      const firstLine = lines.find(l => l.trim().length > 0) || cleanContent;
      
      // Limit length to avoid overflow
      const summary = firstLine.length > 100 ? firstLine.substring(0, 100) + '...' : firstLine;
      
      return (
        <Box marginBottom={1}>
          <Text color={colors.content.secondary}>
            ● {summary}... (ctrl+o to expand thinking)
          </Text>
        </Box>
      );
    }

    // 🔥 Expanded mode: show full content in box
    return (
      <Box
        flexDirection="column"
        marginBottom={1}
        marginLeft={2}
        marginRight={2}
        borderStyle="round"
        borderColor={colors.content.border}
      >
        {hiddenLinesCount > 0 && (
          <Box paddingLeft={2} paddingRight={2}>
            <Text color={colors.warning}>
              ... {hiddenLinesCount} lines hidden ...
            </Text>
          </Box>
        )}
        <Box paddingLeft={2} paddingRight={2} paddingY={0}>
          {/* Reasoning steps back one level in tone instead of using
              `dimColor`: dimming the terminal foreground on a Solarized-style
              palette pushes it back into the background. */}
          <Text color={colors.content.secondary}>{cleanContent}</Text>
        </Box>
      </Box>
    );
  }

  // For tool use messages, render in a highlighted box
  if (isToolUse) {
    // Remove the arrow markers if present
    const cleanContent = safeContent.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();
    const fullContent = originalContent.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();
    const patchInfo = (!isCollapsed || fullContent.startsWith('Apply patch:'))
      ? parseApplyPatchContent(fullContent)
      : null;
    const editInfo = (!isCollapsed || fullContent.startsWith('In the file '))
      ? parseFileEditContent(fullContent)
      : null;
    const editHunks = editInfo?.isComplete
      ? getSimplePatch(editInfo.filePath, editInfo.oldString, editInfo.newString)
      : [];
    // The broad todo_write prefix also matches ordinary "✓ ..." tool notices.
    // Only a formatter snapshot with its progress footer (or an explicit
    // clear) should become a plan cell; streaming partials use the old path.
    const hasTodoSnapshot = fullContent === 'Clearing todo list' || /\[\d+\/\d+ completed\]\s*$/.test(fullContent);
    const todoItems = hasTodoSnapshot && parseToolCall(fullContent)?.type === 'todo_write'
      ? parseTodoWriteContent(fullContent) : null;

    if (todoItems !== null) {
      return (
        <Box flexDirection="column" marginBottom={1}>
          <TodoPlanView
            items={todoItems}
            collapsed={isCollapsed}
            maxRows={disableTruncation || message.metadata?.streamEnd ? undefined : dynamicMaxLines}
          />
        </Box>
      );
    }

    // 🔥 Compact mode: show simplified summary
    if (isCollapsed && !patchInfo && !editInfo?.isComplete) {
      const parsed = parseToolCall(cleanContent);
      
      if (parsed && parsed.type !== 'apply_patch' && parsed.type !== 'update_file') {
        // Format compact display based on tool type
        let compactDisplay = '';
        
        switch (parsed.type) {
          case 'read_file':
            if (parsed.lineStart !== undefined && parsed.lineEnd !== undefined) {
              compactDisplay = `Read(${parsed.path}:${parsed.lineStart}-${parsed.lineEnd})`;
            } else {
              compactDisplay = `Read(${parsed.path})`;
            }
            break;
          case 'view_dir':
            compactDisplay = `View(${parsed.path})`;
            break;
          case 'create_file':
            compactDisplay = `Create(${parsed.path})`;
            break;
          case 'undo_edit':
            compactDisplay = `Undo(${parsed.path})`;
            break;
          case 'run_command':
            // Show first line of command
            const cmd = parsed.details || '';
            const firstLine = cmd.split('\n')[0];
            const displayCmd = firstLine.length > 40 ? firstLine.substring(0, 40) + '...' : firstLine;
            compactDisplay = `Bash(${displayCmd})`;
            break;
          case 'search':
            compactDisplay = `Search(${parsed.details})`;
            break;
          case 'analyze':
            compactDisplay = `Analyze(${parsed.path})`;
            break;
          case 'web':
            compactDisplay = `Web(${parsed.details})`;
            break;
          case 'browser':
            compactDisplay = `Browser(${parsed.details})`;
            break;
          case 'fact_store':
            compactDisplay = parsed.details ? `Fact(${parsed.details})` : 'Fact memory';
            break;
          case 'fact_feedback':
            compactDisplay = parsed.details ? `FactFeedback(${parsed.details})` : 'Fact feedback';
            break;
          default:
            compactDisplay = parsed.summary;

        }

        return (
          <Box marginBottom={1}>
            <Text color={colors.content.secondary}>
              {icons.tool} {compactDisplay}
            </Text>
          </Box>
        );
      }
    }

    if (patchInfo) {
      return (
        <Box flexDirection="column" marginBottom={1}>
          <FileChangeSetView
            changes={patchInfo.changes}
            fileCount={patchInfo.fileCount}
            width={Math.max(terminalWidth - 2, 8)}
          />
        </Box>
      );
    }

    if (editInfo?.isComplete && editHunks.length > 0) {
      return (
        <Box flexDirection="column" marginBottom={1}>
          <FileChangeSetView
            changes={[{ action: 'update', path: editInfo.filePath, hunks: editHunks }]}
            fileCount={1}
            width={Math.max(terminalWidth - 2, 8)}
          />
        </Box>
      );
    }

    const parsed = parseToolCall(cleanContent);
    const isCommand = !isCollapsed && (parsed?.type === 'run_command' || parsed?.type === 'run_powershell');
    const commandDisplay = isCommand ? parseCommandContent(cleanContent) : null;
    const isPromptTool = !isCollapsed && parsed && (
      parsed.type === 'read_file' || parsed.type === 'search' ||
      (parsed.type === 'web' && /^(?:Fetch URL:|Crawl the url:|Web search:)/.test(cleanContent))
    );
    if (isPromptTool) {
      return (
        <Box flexDirection="column" marginBottom={1}>
          <ToolPromptView tool={parsed} content={cleanContent} maxRows={disableTruncation ? undefined : dynamicMaxLines} />
        </Box>
      );
    }
    return (
      <Box flexDirection="column" marginBottom={1}>
        {parsed && <ToolHeading parts={[parsed.summary]} hint={commandDisplay?.timeout ? `timeout:${commandDisplay.timeout}` : undefined} />}
        {commandDisplay ? (
          <CommandView content={commandDisplay.body} hiddenLinesCount={hiddenLinesCount} />
        ) : (
          <Box marginLeft={2} marginRight={2} flexDirection="column" borderStyle="round" borderColor={colors.content.border}>
            {hiddenLinesCount > 0 && (
              <Box paddingLeft={2} paddingRight={2}>
                <Text color={colors.warning}>
                  ... {hiddenLinesCount} lines hidden ...
                </Text>
              </Box>
            )}
            <Box paddingLeft={2} paddingRight={2} paddingY={0}>
              <MarkdownText content={cleanContent} />
            </Box>
          </Box>
        )}
      </Box>
    );
  }

  // For answer messages, render with markdown support
  if (isAnswer) {
    // Remove the arrow markers if present - handle both with and without spaces/asterisks
    const cleanContent = safeContent.replace('▶ **ANSWER**', '').trimStart();

    return (
      <Box flexDirection="column" marginTop={isNewGroup ? 0 : 0}>
        {/* Only show agent icon when it's a new group */}
        {isNewGroup && (
          <Box marginBottom={-1}>
            <Text color="blue" bold>
              {icons.agent}
            </Text>
          </Box>
        )}
        {hiddenLinesCount > 0 && (
          <Box paddingLeft={2}>
            <Text color={colors.warning}>
              ... {hiddenLinesCount} lines hidden ...
            </Text>
          </Box>
        )}
        {cleanContent.length > 0 && (
          <Box paddingLeft={2}>
            <MarkdownText content={cleanContent} />
          </Box>
        )}
      </Box>
    );
  }

  // For process messages (status updates), render in a subtle box
  if (isProcess) {
    return (
      <Box flexDirection="column" marginBottom={0} paddingLeft={2}>
        <Text color={colors.content.secondary}>{safeContent}</Text>
      </Box>
    );
  }

  // 🎯 For /goal verifier pass/fail summaries, render as a single collapsed
  // line ("✓ Goal achieved (2h · 1 turn · 134.1k tokens) (ctrl+o to expand)"),
  // expanding to the full objective/reason/nextAction under global Ctrl+O
  // (isCollapsed), same convention as the thinking/tool_use summaries above.
  if (isGoalResult) {
    const goalResult = message.metadata?.goalResult as
      | {
          achieved: boolean;
          elapsedSeconds: number;
          turns: number;
          tokensUsed: number;
          objective: string;
          reason: string;
          nextAction?: string;
        }
      | undefined;

    if (!goalResult) return null;

    const achieved = goalResult.achieved;
    const icon = achieved ? '✓' : '○';
    const iconColor = achieved ? 'green' : 'yellow';
    const label = achieved ? 'achieved' : 'not yet achieved';
    const elapsedStr = formatElapsedShort(goalResult.elapsedSeconds);
    const turnsStr = `${goalResult.turns} turn${goalResult.turns === 1 ? '' : 's'}`;
    // NOTE: tokensUsed is intentionally not displayed here — the current
    // backend calculation is not accurate yet, so we omit it from the
    // summary line for now rather than show a misleading number.

    const summaryLine = (
      <Text>
        <Text color={iconColor} bold>{icon}</Text>
        <Text> </Text>
        <Text color="cyan" bold> Goal </Text>
        <Text> {label} ({elapsedStr} · {turnsStr})</Text>
      </Text>
    );



    if (isCollapsed) {
      return (
        <Box marginTop={1} marginBottom={1}>
          <Text>
            {summaryLine}
            <Text color={colors.content.secondary}> (ctrl+o to expand)</Text>
          </Text>
        </Box>
      );
    }

    return (
      <Box flexDirection="column" marginTop={1} marginBottom={1}>
        {summaryLine}

        <Box flexDirection="column" paddingLeft={2}>
          <Text color={colors.content.secondary}>Objective: {goalResult.objective}</Text>
          <Text color={colors.content.secondary}>Reason: {goalResult.reason}</Text>
          {goalResult.nextAction && (
            <Text color={colors.content.secondary}>Next action: {goalResult.nextAction}</Text>
          )}
        </Box>
      </Box>
    );
  }

  // 🔴 For error box messages, render in a red bordered box (similar to tool_use style)
  if (isErrorBox) {
    return (
      <Box
        flexDirection="column"
        marginBottom={1}
        marginLeft={2}
        borderStyle="round"
        borderColor="red"
        paddingX={1}
      >
        {hiddenLinesCount > 0 && (
          <Box paddingLeft={2}>
            <Text color={colors.warning}>
              ... {hiddenLinesCount} lines hidden ...
            </Text>
          </Box>
        )}
        <Box paddingLeft={1} paddingY={0}>
          <Text color={colors.error}>
            {safeContent}
          </Text>
        </Box>
      </Box>
    );
  }

  // For user messages, render with a full-width background highlight
  if (message.type === 'user') {
    // Theme-aware colors: the dark bar needs an explicit light foreground —
    // on the light theme the terminal's default foreground is dark and would
    // be invisible on #333333.
    const isLight = getActiveTheme() === 'light';
    const USER_INPUT_BG = isLight ? '#e9edf2' : '#333333';
    const USER_INPUT_FG = isLight ? '#1f2328' : '#e6e6e6';
    const lines = (message.content ?? '').split('\n');
    const width = Math.max(terminalWidth, 1);

    return (
      <Box flexDirection="column" marginTop={0.5} marginBottom={1}>
        {lines.map((line, i) => {
          const text = i === 0 ? `${getIcon()} ${line}` : `  ${line}`;
          // Pad short lines so the background spans the full terminal width.
          // Use display width (CJK chars occupy 2 columns), not string length.
          const padCount = Math.max(width - stringWidth(text), 0);
          const padded = text + ' '.repeat(padCount);
          return (
            <Text key={i} backgroundColor={USER_INPUT_BG} color={USER_INPUT_FG}>
              {padded}
            </Text>
          );
        })}
      </Box>
    );
  }

  // Regular message rendering with header
  return (
    <Box flexDirection="column" marginBottom={0.5} marginTop={0.5}>
      <Box marginBottom={-1}>
        <Text color={getColor()} bold>
          {getIcon()}
        </Text>
        {/* <Text dimColor> [{formatTimestamp(message.timestamp)}]</Text> */}
      </Box>

      <Box paddingLeft={2} marginBottom={1}>
        {message.type === 'agent' ? (
          <MarkdownText content={message.content} />
        ) : (
          <Text>{message.content}</Text>
        )}
      </Box>

      {message.toolCalls && message.toolCalls.length > 0 && (
        <Box paddingLeft={4} marginTop={1}>
          <Text color={colors.content.secondary}>
            {icons.tool} Tool calls: {message.toolCalls.length}
          </Text>
        </Box>
      )}

      {message.fileEdits && message.fileEdits.length > 0 && (
        <Box paddingLeft={4}>
          <Text color={colors.content.secondary}>
            {icons.fileEdited} Files edited: {message.fileEdits.length}
          </Text>
        </Box>
      )}
    </Box>
  );
};

// Export memoized component to prevent unnecessary re-renders
export const Message = React.memo(MessageInternal);
