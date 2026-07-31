/**
 * Message List Component
 * Displays a scrollable list of messages
 * Groups agent process messages (thinking, tool_use) and shows answer separately
 * 
 * OPTIMIZED: Uses Ink's Static component to separate history from pending messages
 * This prevents re-rendering of completed messages during streaming
 */

import React, { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import { Box, Text, Static, useStdout } from '@jrichman/ink';
import ansiEscapes from 'ansi-escapes';
import { Message } from './Message.js';
import { ProcessBox } from './ProcessBox.js';
import { AgentMessage } from './AgentMessage.js';
import { Message as MessageType } from '../../types/index.js';
import { getIcons } from '../../constants/icons.js';
import { logger } from '../../utils/logger.js';
import { AppHeader } from '../layouts/AppHeader.js';
import { MarkdownText } from '../common/MarkdownText.js';
import { 
  findLastSafeSplitPoint, 
  shouldSplitContent,
  countLines 
} from '../../utils/markdownUtilities.js';
import { 
  MESSAGE_SPLIT_THRESHOLD,
  MIN_PENDING_CONTENT_LINES,
} from '../../constants/limits.js';
import { Banner } from '../Banner/Banner.js';
import { parseToolCall, type ParsedToolCall } from '../../utils/toolCallParser.js';
import { recordFlicker } from '../../utils/flickerMonitor.js';

// Virtual Scrolling: Only render recent messages to prevent Terminal.app crashes
// Terminal.app's NSMutableAttributedString has severe memory corruption issues
const MAX_VISIBLE_MESSAGES = 50; // Only render last 50 messages

export interface MessageListProps {
  messages: MessageType[];
  headerProps?: {
    version?: string;
    workingDir: string;
    agent?: string;
    provider?: string;
    model?: string;
    prePlanMode?: boolean;
  };
  terminalWidth?: number;  // For triggering remount on resize
  maxHeight?: number;      // Maximum height in rows for the message list
  isCollapsed?: boolean;   // Collapse mode - hide tool use messages
  noStatic?: boolean;      // When true, render all messages as regular flex children
                           // (skip Ink <Static>). Required by alt-screen views like
                           // TodoDetailView where Static items would scroll past the
                           // alt buffer top, leaving most messages invisible.
}

interface MessageGroup {
  type: 'user' | 'agent' | 'system' | 'error' | 'tool';
  message: MessageType; // Unified message field; no longer distinguishes simpleMessage/answerMessage etc.
  // Split-related fields
  isSplitGroup?: boolean;  // Marks this as a split group
  splitIndex?: number;     // Split index
  isLastSplit?: boolean;   // Whether this is the last split fragment
  // Tool call aggregation fields
  isAggregated?: boolean;  // Marks this as an aggregated tool call group
  aggregatedTools?: ParsedToolCall[];  // List of aggregated tool calls
}

/**
 * Extract clean content from agent message
 * Removes box-drawing characters, headers, token counters, and ANSI codes
 */
function extractCleanContent(content: string): string {
  // Remove ANSI escape sequences (colors, formatting, etc.)
  // This regex matches ANSI escape codes like \x1b[39m, \x1b[1m, etc.
  let cleaned = content.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
  
  // Also remove alternative ANSI format [39m, [1m, etc.
  cleaned = cleaned.replace(/\[[0-9;]*m/g, '');
  
  // Remove box-drawing characters (╭, ╮, ╰, ╯, │, ─)
  cleaned = cleaned.replace(/[╭╮╰╯│─]/g, '');
  
  // Remove arrow and **TYPE** headers
  cleaned = cleaned.replace(/[▶►]\s*\*\*[A-Z\s]+\*\*/g, '');
  
  // Remove token counter lines - split into lines first to handle each line
  const lines = cleaned.split('\n');
  const filteredLines = lines.filter(line => {
    // Remove lines that are ONLY whitespace and token counts
    // Pattern: any amount of whitespace + "X,XXX / XXX,XXX tokens"
    const tokenPattern = /^\s*[\d,]+\s*\/\s*[\d,]+\s+tokens?\s*$/i;
    if (tokenPattern.test(line)) {
      return false; // Remove this line
    }
    
    // Remove lines that are only separators
    const separatorPattern = /^[\s─\-]+$/;
    if (separatorPattern.test(line)) {
      return false;
    }
    
    // Keep all lines including empty ones to preserve newline structure
    return true;
  });
  
  // Join lines back together
  let result = filteredLines.join('\n');
  
  // Collapse 3+ consecutive newlines into 2 (one blank line) throughout the content
  // This handles cases where removing markers (like ▶ **ANSWER**) leaves extra blank lines
  result = result.replace(/\n{3,}/g, '\n\n');
  
  // Strip leading newlines
  result = result.replace(/^\n+/, '');
  
  // Strip trailing newlines (keep at most 1)
  result = result.replace(/\n{2,}$/, '\n');
  
  return result;
}

  // 🔥 Use React.memo to prevent unnecessary re-renders when messages haven't changed
export const MessageList: React.FC<MessageListProps> = React.memo(({ messages, headerProps, terminalWidth, isCollapsed = false, noStatic = false }) => {
  const scrollRef = useRef<any>(null);
  const icons = getIcons();
  const [historyRemountKey, setHistoryRemountKey] = useState(0);
  const isInitialMount = useRef(true);
  const resizeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const prevModelRef = useRef<string | undefined>(undefined);
  const { stdout } = useStdout();

  // Track group signatures to detect when existing groups change (need remount)
  const lastStaticGroupSignaturesRef = useRef<string[]>([]);
  
  // Track current group_key to detect group boundaries
  const currentGroupKeyRef = useRef<string | undefined>(undefined);
  const currentKeyRef = useRef<string | undefined>(undefined);

  const { staticMessages, pendingMessages } = useMemo(() => {
    return {
      staticMessages: messages,
      pendingMessages: [],
    };
  }, [messages]);

  const refreshStatic = useCallback(() => {
    // Detect if we're in alternate buffer mode
    // Ink typically runs in normal mode (not alternate buffer)
    // Alternate buffer is used by full-screen apps like vim, less, etc.
    const isAlternateBuffer = false; // Ink doesn't use alternate buffer by default
    
    // Only clear terminal in normal mode to avoid disrupting alternate buffer apps
    if (!isAlternateBuffer && stdout) {
      logger.info('Clearing terminal before redraw', {
        component: 'MessageList',
        operation: 'clear_terminal',
        reason: 'terminal_resize',
      });
      recordFlicker('refreshStatic', 'clearTerminal + Static remount', {
        messageCount: staticMessages.length,
        remountKey: historyRemountKey,
      });
      stdout.write(ansiEscapes.clearTerminal);
    }
    
    // Remount Static component to force re-layout with new terminal dimensions
    setHistoryRemountKey((prev) => {
      logger.info('Remounting static content after terminal resize', {
        component: 'MessageList',
        operation: 'resize_remount',
        oldKey: prev,
        newKey: prev + 1,
      });
      return prev + 1;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stdout]);

  // When model changes in headerProps, remount Static to update the banner
  useEffect(() => {
    const currentModel = headerProps?.model;
    if (prevModelRef.current !== undefined && prevModelRef.current !== currentModel) {
      recordFlicker('model_change', `Model changed: ${prevModelRef.current} → ${currentModel}`, {
        messageCount: staticMessages.length,
        remountKey: historyRemountKey,
      });
      refreshStatic();
    }
    prevModelRef.current = currentModel;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headerProps?.model, refreshStatic]);

  // When terminal width or isCollapsed changes, clear screen and remount Static component
  useEffect(() => {
    // Skip on initial mount
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }

    // Skip if no terminal width provided
    if (!terminalWidth) {
      return;
    }

    // Clear existing timeout
    if (resizeTimeoutRef.current) {
      clearTimeout(resizeTimeoutRef.current);
    }

    // Debounce: wait 300ms before clearing and remounting to avoid excessive re-renders
    resizeTimeoutRef.current = setTimeout(() => {
      logger.info('Terminal resized or collapse mode changed, initiating clear and redraw', {
        component: 'MessageList',
        operation: 'resize_or_collapse_detected',
        terminalWidth,
        isCollapsed,
        historyRemountKey,
      });
      
      recordFlicker('resize_debounced', `Terminal resize or collapse toggle (width=${terminalWidth}, collapsed=${isCollapsed})`, {
        messageCount: staticMessages.length,
        remountKey: historyRemountKey,
      });
      
      // Execute clear screen and remount strategy
      refreshStatic();
    }, 300);

    return () => {
      if (resizeTimeoutRef.current) {
        clearTimeout(resizeTimeoutRef.current);
      }
    };
  }, [terminalWidth, isCollapsed, refreshStatic]);

  useEffect(() => {
    if (scrollRef.current && scrollRef.current.scrollToBottom) {
      scrollRef.current.scrollToBottom();
    }
  }, [messages]);

  const keepThinkingIdsRef = useRef<Set<string> | null>(null);
  const lastCollapsedForThinkingRef = useRef<boolean | null>(null);

  const groupMessages = useCallback((messages: MessageType[], collapsed: boolean): MessageGroup[] => {
    const groups: MessageGroup[] = [];

    // Only render the latest few thinking messages, in both compact and expanded
    // mode. The set of "kept" ids is frozen in a ref and only recomputed when
    // `collapsed` actually flips (i.e. when the user presses ctrl+o) — that action
    // already forces a re-render/remount, so it's the right (and only) moment to
    // recompute. Recomputing on every message update instead would keep flipping
    // older thinking groups in/out of the render set as new ones stream in,
    // shifting group indices and constantly triggering signature-mismatch remounts.
    //
    // Before the first ctrl+o press, there's no toggle to piggyback the
    // recompute on, so no limit is applied yet (render all thinking messages).
    const MAX_THINKING_MESSAGES = 2;
    if (lastCollapsedForThinkingRef.current === null) {
      // First call ever: just record the baseline, don't filter yet.
      lastCollapsedForThinkingRef.current = collapsed;
    } else if (lastCollapsedForThinkingRef.current !== collapsed) {
      // `collapsed` flipped, i.e. ctrl+o was pressed: recompute the limit.
      const thinkingIds: string[] = [];
      for (const msg of messages) {
        if (msg.metadata?.subtype === 'thinking') {
          thinkingIds.push(msg.id);
        }
      }
      keepThinkingIdsRef.current = new Set(thinkingIds.slice(-MAX_THINKING_MESSAGES));
      lastCollapsedForThinkingRef.current = collapsed;
    }
    const keepThinkingIds = keepThinkingIdsRef.current;

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      
      // Filter empty messages from stream end
      const isStreamEnd = msg.metadata?.isStreaming === false && msg.metadata?.streamEnd === true;
      const isEmpty = !msg.content || msg.content.trim() === '';
      
      if (isStreamEnd && isEmpty) {
        continue;
      }

      // Only render the latest MAX_THINKING_MESSAGES thinking messages (collapsed mode only)
      if (keepThinkingIds && msg.metadata?.subtype === 'thinking' && !keepThinkingIds.has(msg.id)) {
        continue;
      }

      // In compact mode, aggregate consecutive tool_use messages
      const isToolUse = msg.metadata?.subtype === 'tool_use';
      
      if (collapsed && isToolUse) {
        const cleanContent = (msg.content || '').replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();
        const parsed = parseToolCall(cleanContent);
        
        if (parsed) {
          // Check if previous group is also an aggregated tool call group
          const lastGroup = groups[groups.length - 1];
          
          // Calculate total lines used by current aggregated group
          const groupLines = (lastGroup?.aggregatedTools ?? []).reduce(
            (sum, t) => sum + ((t.path || t.details || t.summary).split('\n').length),
            0
          );
          const maxGroupLines = Math.max((process.stdout.rows || 13) - 12, 1);

          if (lastGroup && lastGroup.isAggregated && lastGroup.aggregatedTools &&
              groupLines < maxGroupLines) {
            // Append to existing aggregated group (within height limit)
            lastGroup.aggregatedTools.push(parsed);
            continue;
          } else {
            // Start a new aggregated group (old group is full)
            groups.push({
              type: msg.type,
              message: msg,
              isAggregated: true,
              aggregatedTools: [parsed],
            });
            continue;
          }
        }
      }
      
      // Non-tool or expanded mode: add normally
      groups.push({
        type: msg.type,
        message: msg,
      });
    }

    return groups;
  }, []);

  // Split groups into static (completed) and pending (last group if small enough)
  const { staticGroups, pendingGroups } = useMemo(() => {
    const startTime = Date.now();
    const allGroups = groupMessages(staticMessages, isCollapsed);
    
    if (allGroups.length === 0) {
      return { staticGroups: [], pendingGroups: [] };
    }

    // Calculate signatures for all groups.
    // IMPORTANT: signature uses `streamEnd` instead of `content.length`.
    // Using content.length caused a flicker loop: during streaming, flushStreamingNow
    // updates the answer message's content every 80ms, and if that message is in
    // Static (not the last group), the len change triggers needsRemount → clear screen
    // → useMemo re-run → next flush changes len again → infinite loop.
    // With streamEnd, content changes are ignored; only stream completion (false→true)
    // triggers one remount to show the final content.
    const currentSignatures = allGroups.map((group, idx) => {
      const done = !!group.message?.metadata?.streamEnd;
      return `type:${group.type}|id:${group.message?.id ?? `g${idx}`}|done:${done}`;
    });

    // Check if any existing group changed
    let needsRemount = false;
    const lastSignatures = lastStaticGroupSignaturesRef.current;
    
    if (lastSignatures.length > 0) {
      // Compare signatures of existing groups (not the last one, as it may be pending)
      const compareLength = Math.min(lastSignatures.length, currentSignatures.length - 1);
      for (let i = 0; i < compareLength; i++) {
        if (lastSignatures[i] !== currentSignatures[i]) {
          needsRemount = true;
          logger.info('Detected change in existing group, triggering remount', {
            component: 'MessageList',
            groupIndex: i,
            oldSignature: lastSignatures[i],
            newSignature: currentSignatures[i],
          });
          break;
        }
      }
    }

    const lastGroup = allGroups[allGroups.length - 1];
    
    // Get terminal dimensions
    const terminalHeight = stdout?.rows || 24;
    const terminalWidth = stdout?.columns || 80;
    const halfHeight = Math.floor(terminalHeight / 2);
    
    // Helper function to estimate rendered lines considering terminal width
    const estimateRenderedLines = (content: string): number => {
      if (!content) return 1;
      
      const lines = content.split('\n');
      let totalRenderedLines = 0;
      
      for (const line of lines) {
        // Account for line wrapping based on terminal width
        // Subtract 4 for padding/margins
        const effectiveWidth = Math.max(terminalWidth - 4, 40);
        const wrappedLines = Math.ceil(Math.max(line.length, 1) / effectiveWidth);
        totalRenderedLines += wrappedLines;
      }
      
      return totalRenderedLines;
    };
    
    // Determine whether to keep as pending based on content length
    const estimatedLines = estimateRenderedLines(lastGroup.message.content || '') + 2;

    const duration = Date.now() - startTime;
    if (duration > 50) {
      logger.debug('Messages grouped and split', {
        component: 'MessageList',
        count: staticMessages.length,
        totalGroups: allGroups.length,
        lastGroupLines: estimatedLines,
        terminalHeight,
        halfHeight,
        needsRemount,
        duration,
      });
    }

    // If existing group changed, trigger remount
    if (needsRemount) {
      recordFlicker('group_signature_remount', 'Group signature changed — existing group content modified', {
        messageCount: staticMessages.length,
        metadata: {
          changedGroupIndex: lastSignatures.findIndex((s, i) => i < currentSignatures.length && s !== currentSignatures[i]),
        },
      });
      setTimeout(() => refreshStatic(), 0);

      // BUGFIX: an EARLIER group finishing (e.g. a "thinking" block reaching
      // streamEnd right as the next "answer" block starts streaming) must not
      // force the CURRENT last group into Static too. The last group may still
      // be actively streaming — freezing it into Static here permanently pins
      // it above any still-dynamic UI below (ThinkingIndicator, the /btw
      // SideQuestionPanel, the input box), even though it hasn't finished and
      // should keep rendering in the dynamic (pending) area until it is done.
      // Only fold the last group into Static on this remount if it is itself
      // already done, or too tall to stay pending — exactly the same rule
      // used in the non-remount path below.
      const lastGroupDone = !!lastGroup.message?.metadata?.streamEnd;
      if (!lastGroupDone && estimatedLines <= halfHeight) {
        lastStaticGroupSignaturesRef.current = currentSignatures.slice(0, -1);
        return {
          staticGroups: allGroups.slice(0, -1),
          pendingGroups: [lastGroup],
        };
      }

      lastStaticGroupSignaturesRef.current = currentSignatures;
      return {
        staticGroups: allGroups,
        pendingGroups: [],
      };
    }


    // If last group is small enough, keep it as pending (dynamic render)
    if (estimatedLines <= halfHeight) {
      lastStaticGroupSignaturesRef.current = currentSignatures.slice(0, -1);
      return {
        staticGroups: allGroups.slice(0, -1),
        pendingGroups: [lastGroup],
      };
    }

    // Otherwise, put everything in static
    lastStaticGroupSignaturesRef.current = currentSignatures;
    return {
      staticGroups: allGroups,
      pendingGroups: [],
    };
  }, [staticMessages, groupMessages, stdout, refreshStatic, isCollapsed]);


  const renderGroup = useCallback(
    (group: MessageGroup, idx: number, isStatic: boolean) => {
      // Guard: skip groups with no message (should not happen, but be defensive)
      if (!group.message) return null;

      // Aggregated tool call group: render as count summary
      if (group.isAggregated && group.aggregatedTools && group.aggregatedTools.length > 0) {
        const icons = getIcons();
        const tools = group.aggregatedTools;
        
        // Count by tool type
        const counts = new Map<string, number>();
        tools.forEach(tool => {
          const count = counts.get(tool.type) || 0;
          counts.set(tool.type, count + 1);
        });
        
        // Build summary text
        const parts: string[] = [];
        for (const [type, count] of counts.entries()) {
          switch (type) {
            case 'read_file':
              parts.push(count === 1 ? 'Read 1 file' : `Read ${count} files`);
              break;
            case 'view_dir':
              parts.push(count === 1 ? 'View 1 dir' : `View ${count} dirs`);
              break;
            case 'create_file':
              parts.push(count === 1 ? 'Create 1 file' : `Create ${count} files`);
              break;
            case 'update_file':
              parts.push(count === 1 ? 'Update 1 file' : `Update ${count} files`);
              break;
            case 'undo_edit':
              parts.push(count === 1 ? 'Undo 1 edit' : `Undo ${count} edits`);
              break;
            case 'run_command':
              parts.push(count === 1 ? 'Run 1 command' : `Run ${count} commands`);
              break;
            case 'run_powershell':
              parts.push(count === 1 ? 'Run 1 PowerShell command' : `Run ${count} PowerShell commands`);
              break;
            case 'search':
              parts.push(count === 1 ? '1 search' : `${count} searches`);
              break;
            case 'analyze':
              parts.push(count === 1 ? 'Analyze 1 file' : `Analyze ${count} files`);
              break;
            case 'web':
              parts.push(count === 1 ? '1 web request' : `${count} web requests`);
              break;
            case 'browser':
              parts.push(count === 1 ? '1 browser action' : `${count} browser actions`);
              break;
            case 'memory_search':
              parts.push(count === 1 ? 'Search memory' : `${count} memory searches`);
              break;
            case 'memory_write':
              parts.push(count === 1 ? 'Save to memory' : `${count} memory saves`);
              break;
            case 'fact_store':
              parts.push(count === 1 ? 'Fact memory' : `${count} fact memory ops`);
              break;
            case 'fact_feedback':
              parts.push(count === 1 ? 'Fact feedback' : `${count} fact feedbacks`);
              break;
            case 'sub_agent':

              parts.push(count === 1 ? '1 sub-agent task' : `${count} sub-agent tasks`);
              break;
            case 'lark':
              parts.push(count === 1 ? '1 Lark notification' : `${count} Lark notifications`);
              break;
            case 'todo_write':
              parts.push('Todo List');
              break;
          }
        }
        
        const summary = parts.join(', ');
        
        // Group by type and build tree preview
        const MAX_PREVIEW_PER_TYPE = 20;
        const groupedByType = new Map<string, string[]>();
        
        tools.forEach(tool => {
          let items = groupedByType.get(tool.type) || [];

          // Special case: todo_write - split into individual windowed lines
          if (tool.type === 'todo_write' && tool.details) {
            const allLines = tool.details.split('\n')
              .map((l: string) => l.trimEnd())
              .filter((l: string) => l.trim() && !l.match(/^\[\d+\/\d+ completed\]$/));

            // Find center: last in_progress (◐), else first pending (○), else last item
            let centerIdx = -1;
            for (let i = allLines.length - 1; i >= 0; i--) {
              if (allLines[i].startsWith('◐')) { centerIdx = i; break; }
            }
            if (centerIdx === -1) centerIdx = allLines.findIndex((l: string) => l.startsWith('○'));
            if (centerIdx === -1) centerIdx = allLines.length - 1;

            const start = Math.max(0, centerIdx - 2);
            const end = Math.min(allLines.length - 1, centerIdx + 2);
            const windowLines: string[] = [];
            if (start > 0) windowLines.push('…');
            for (let i = start; i <= end; i++) windowLines.push(allLines[i]);
            if (end < allLines.length - 1) windowLines.push('…');

            for (const line of windowLines) items.push(line);
            groupedByType.set(tool.type, items);
            return; // skip generic logic
          }

          // Extract display text
          let displayItem = '';
          if (tool.path) {
            // Use only the last path segment (filename or dirname)
            const pathParts = tool.path.split('/');
            const filename = pathParts[pathParts.length - 1] || tool.path;
            // Append line range for read_file calls
            if (tool.type === 'read_file' && tool.lineStart !== undefined && tool.lineEnd !== undefined) {
              displayItem = `${filename}:${tool.lineStart}-${tool.lineEnd}`;
            } else {
              displayItem = filename;
            }
          } else if (tool.details) {
            const detailLines = tool.details.split('\n');
            if (detailLines.length > 5) {
              displayItem = detailLines.slice(0, 5).join('\n') + '\n…';
            } else {
              displayItem = tool.details;
            }
          }
          
          if (displayItem) {
            items.push(displayItem);
            groupedByType.set(tool.type, items);
          }
        });
        
        return (
          <Box key={`aggregated-${idx}`} flexDirection="column" marginBottom={1}>
            <Text>
              <Text color="cyan">●</Text> <Text>{summary}</Text> <Text color="gray"> (ctrl+o to expand)</Text>
            </Text>

            <Box flexDirection="column" paddingLeft={2}>
              {Array.from(groupedByType.entries()).map(([type, items], typeIndex) => {
                const previewItems = items.slice(0, MAX_PREVIEW_PER_TYPE);
                const hiddenCount = items.length - previewItems.length;
                const isLastType = typeIndex === groupedByType.size - 1;
                const totalItemsInGroup = previewItems.length + (hiddenCount > 0 ? 1 : 0);
                
                return (
                  <Box key={type} flexDirection="column">
                    {previewItems.map((item, itemIndex) => {
                      // todo_write: no tree prefix, just indent
                      if (type === 'todo_write') {
                        return (
                          <Box key={itemIndex}>
                            <Text color="gray">{item}</Text>
                          </Box>
                        );
                      }
                      const isLastInGroup = itemIndex === previewItems.length - 1 && hiddenCount === 0;
                      const prefix = isLastInGroup && isLastType ? '└─ ' : '├─ ';
                      return (
                        <Box key={itemIndex}>
                          <Text color="gray">
                            {prefix}{item}
                          </Text>
                        </Box>
                      );
                    })}

                    {hiddenCount > 0 && type !== 'todo_write' && (
                      <Box>
                        <Text color="gray">
                          {isLastType ? '└─ ' : '└─ '}… +{hiddenCount} more
                        </Text>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>
          </Box>
        );
      }

      const key = group.message.id ?? `group-${idx}`

      // Detect group boundary
      let isNewGroup = true;

      // For split messages, check splitIndex
      if (key?.includes('_split_')) {
        // Extract splitIndex from key: "msg-123_split_2" -> 2
        const match = key.match(/_split_(\d+)$/);
        if (match) {
          const splitIndex = parseInt(match[1], 10);
          // splitIndex !== 1 means not the first split fragment, not a new group
          if (splitIndex !== 1) {
            isNewGroup = false;
          }
        }
      }

      return (
        <Message
          key={group.message.id}
          message={group.message}
          isNewGroup={isNewGroup}
          disableTruncation={isStatic}
          isCollapsed={isCollapsed}
        />
      );
    },
    [isCollapsed]
  );


  // noStatic mode: render every group inline (no Ink <Static>) so messages
  // participate in flex layout. Used by TodoDetailView (alt-screen) where Static
  // items would scroll past the alt buffer top.
  if (noStatic) {
    return (
      <Box ref={scrollRef} flexDirection="column" padding={0}>
        {headerProps && <Banner {...headerProps} />}
        {staticGroups.map((group, idx) => renderGroup(group, idx, false))}
        {pendingGroups.map((group, idx) =>
          renderGroup(group, staticGroups.length + idx, false)
        )}
      </Box>
    );
  }

  return (
    <Box ref={scrollRef} flexDirection="column" padding={0}>

      {/* <Static items={['header']}>
        {(item, index) => (
          <AppHeader key="message_header" {...headerProps} />
        )}
      </Static> */}

      {/* OPTIMIZATION: Static component for header + completed messages - won't re-render */}
      <Static key={historyRemountKey} items={[{ type: 'header' as const }, ...staticGroups]}>
        {(item, index) => {
          // First item is always the header sentinel — render banner if headerProps present, else skip
          if (index === 0 && 'type' in item && item.type === 'header') {
            if (headerProps) return <Banner key="header" {...headerProps} />;
            return <React.Fragment key="no-header" />;
          }
          // Other items are message groups
          return renderGroup(item as MessageGroup, index - 1, true);
        }}
      </Static>
      
      {/* OPTIMIZATION: Dynamic rendering for pending (last) group if small enough */}
      {pendingGroups.map((group, idx) =>
        renderGroup(group, staticGroups.length + idx, false)
      )}
    </Box>
  );
}); // Close React.memo
