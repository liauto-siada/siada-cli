/**
 * Message Component
 * Displays a single message in the chat
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { Message as MessageType } from '../../types/index.js';
import { MAX_TEXT_LENGTH } from '../../constants/limits.js';
import { getIcons } from '../../constants/icons.js';
import { truncateByLines, truncateByJSONLines } from '../../utils/contentTruncator.js';
import { MarkdownText } from '../common/MarkdownText.js';
import { ShellOutput } from '../Shell/ShellOutput.js';
import { parseToolCall } from '../../utils/toolCallParser.js';

export interface MessageProps {
  message: MessageType;
  isNewGroup?: boolean;        // Indicates whether this is a new group (group_key has changed)
  disableTruncation?: boolean; // When true, render full content without truncation (used for static history)
  isCollapsed?: boolean;       // When true, show compact summary for tool calls
}

const MessageInternal: React.FC<MessageProps> = ({ message, isNewGroup = true, disableTruncation = false, isCollapsed = false }) => {
  const icons = getIcons();

  const getColor = (): string => {
    switch (message.type) {
      case 'user':
        return 'gray';
      case 'agent':
        return 'blue';
      case 'system':
        return 'yellow';
      case 'error':
        return 'red';
      case 'tool':
        return 'magenta';
      default:
        return 'white';
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

  // Truncate content if too long
  // Use line-based truncation FIRST (more effective for Terminal.app)
  // Calculate dynamic max lines based on terminal height
  // Note: process is a global Node.js object, available in runtime but needs type declaration
  const terminalHeight = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.rows) || 24;
  const terminalWidth = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.columns) || 80;
  const dynamicMaxLines = Math.max(terminalHeight / 2, 5);

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
    const cleanContent = safeContent.replace(/[▶►]\s*\*{0,2}THINKING\*{0,2}\s*/i, '').trim();

    // 🔥 Compact mode: show only first line summary
    if (isCollapsed) {
      // Extract first line
      const lines = cleanContent.split('\n');
      let firstLine = lines[0] || cleanContent;
      
      // 🔥 Clean THINKING: prefix from first line only
      firstLine = firstLine.replace(/^THINKING:\s*/i, '').trim();
      
      // Limit length to avoid overflow
      const summary = firstLine.length > 100 ? firstLine.substring(0, 100) + '...' : firstLine;
      
      return (
        <Box marginBottom={1}>
          <Text color="gray">
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
        borderColor="gray"
      >
        {/* <Box paddingLeft={2} paddingRight={2} paddingTop={0} paddingBottom={0}>
          <Text color="gray" bold>Thinking:</Text>
        </Box> */}
        {hiddenLinesCount > 0 && (
          <Box paddingLeft={2} paddingRight={2}>
            <Text color="yellow" dimColor>
              ... {hiddenLinesCount} lines hidden ...
            </Text>
          </Box>
        )}
        <Box paddingLeft={2} paddingRight={2} paddingY={0}>
          <Text dimColor>{cleanContent}</Text>
        </Box>
      </Box>
    );
  }

  // For tool use messages, render in a highlighted box
  if (isToolUse) {
    // Remove the arrow markers if present
    const cleanContent = safeContent.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();

    // 🔥 Compact mode: show simplified summary
    if (isCollapsed) {
      const parsed = parseToolCall(cleanContent);
      
      if (parsed) {
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
          case 'update_file':
            compactDisplay = `Update(${parsed.path})`;
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
          case 'crawl':
            compactDisplay = `Crawl(${parsed.details})`;
            break;
          case 'browser':
            compactDisplay = `Browser(${parsed.details})`;
            break;
          default:
            compactDisplay = parsed.summary;
        }

        return (
          <Box marginBottom={1}>
            <Text color="gray" dimColor>
              {icons.tool} {compactDisplay}
            </Text>
          </Box>
        );
      }
    }

    // 🔥 Expanded mode: show full content (original behavior)
    return (
      <Box
        flexDirection="column"
        marginBottom={1}
        marginLeft={2}
        marginRight={2}
        borderStyle="round"
        borderColor="gray"
      >
        {hiddenLinesCount > 0 && (
          <Box paddingLeft={2} paddingRight={2}>
            <Text color="g" dimColor>
              ... {hiddenLinesCount} lines hidden ...
            </Text>
          </Box>
        )}
        <Box paddingLeft={2} paddingRight={2} paddingY={0}>
          <MarkdownText content={cleanContent} />
        </Box>
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
            <Text color="yellow" dimColor>
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
        <Text dimColor>{safeContent}</Text>
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
            <Text color="yellow" dimColor>
              ... {hiddenLinesCount} lines hidden ...
            </Text>
          </Box>
        )}
        <Box paddingLeft={1} paddingY={0}>
          <Text color="red" dimColor>
            {safeContent}
          </Text>
        </Box>
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
          <Text dimColor>
            {icons.tool} Tool calls: {message.toolCalls.length}
          </Text>
        </Box>
      )}

      {message.fileEdits && message.fileEdits.length > 0 && (
        <Box paddingLeft={4}>
          <Text dimColor>
            {icons.fileEdited} Files edited: {message.fileEdits.length}
          </Text>
        </Box>
      )}
    </Box>
  );
};

// Export memoized component to prevent unnecessary re-renders
export const Message = React.memo(MessageInternal);
