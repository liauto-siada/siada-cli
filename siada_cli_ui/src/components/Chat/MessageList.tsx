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
import { Message } from './Message.js';
import { ProcessBox } from './ProcessBox.js';
import { AgentMessage } from './AgentMessage.js';
import { Message as MessageType } from '../../types/index.js';
import { ToolHeading } from './ToolHeading.js';
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
import { parseToolCall, isTodoWriteAllCompleted, type ParsedToolCall } from '../../utils/toolCallParser.js';
import { recordFlicker } from '../../utils/flickerMonitor.js';
import { beginSyncOutput, endSyncOutput } from '../../utils/stdio.js';
import { extractCleanContent } from '../../utils/contentCleaner.js';
import { isRenderableToolDiff } from '../../utils/diff.js';
import { colors } from '../../utils/colors.js';
import { useThemeVersion } from '../../themes/index.js';

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

// 🔥 Use React.memo to prevent unnecessary re-renders when messages haven't changed
export const MessageList: React.FC<MessageListProps> = React.memo(({ messages, headerProps, terminalWidth, isCollapsed = false, noStatic = false }) => {
  const scrollRef = useRef<any>(null);
  const [historyRemountKey, setHistoryRemountKey] = useState(0);
  const themeVersion = useThemeVersion();
  const previousThemeVersionRef = useRef(themeVersion);
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
    // Keep synchronized output active while Ink replaces the Static node and
    // atomically clears and redraws the old history. The 150ms window covers
    // React scheduling and Ink's render throttle.
    beginSyncOutput();

    // Ink owns the physical clear when the Static node is replaced. Clearing
    // here as well would clear the terminal twice on every resize/toggle.
    if (stdout) {
      logger.info('Scheduling static history replacement', {
        component: 'MessageList',
        operation: 'replace_static_history',
        reason: 'terminal_resize',
      });
      recordFlicker('refreshStatic', 'Static remount and Ink-managed redraw', {
        messageCount: staticMessages.length,
        remountKey: historyRemountKey,
      });
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

    setTimeout(endSyncOutput, 150);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stdout]);

  useEffect(() => {
    if (previousThemeVersionRef.current !== themeVersion) {
      previousThemeVersionRef.current = themeVersion;
      refreshStatic();
    }
  }, [themeVersion, refreshStatic]);

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

        if (parsed?.type === 'todo_write') {
          // TodoStatusBar already mirrors intermediate states. Keep the final
          // snapshot (or explicit clear) as a single independent history cell,
          // rather than merging it into subsequent tool aggregation.
          if (isTodoWriteAllCompleted(cleanContent) || cleanContent === 'Clearing todo list') {
            groups.push({ type: msg.type, message: msg });
          }
          continue;
        }

        if (parsed?.type === 'apply_patch' || parsed?.type === 'update_file') {
          groups.push({ type: msg.type, message: msg });
          continue;
        }

        if (parsed) {
          // Check if previous group is also an aggregated tool call group
          const lastGroup = groups[groups.length - 1];
          
          // Calculate total lines used by current aggregated group
          const groupLines = (lastGroup?.aggregatedTools ?? []).reduce(
            (sum, t) => sum + ((t.path || t.details || t.summary).split('\n').length),
            0
          );
          const maxGroupLines = Math.max((process.stdout.rows || 23) - 22, 1);

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

    // A last group that is still streaming (answer/thinking/tool_use without
    // streamEnd) must NEVER be committed to <Static>, no matter how tall it
    // gets: Static items are append-only and never re-render, so a still-
    // growing group would freeze at whatever content it had when committed —
    // and since remount detection below intentionally ignores the last
    // group's signature, the frozen tail (including the final content
    // arriving at streamEnd) would never render at all. Keep it in the
    // dynamic pending area instead (Message truncates the view to a bounded
    // tail); when the stream ends, the group enters Static as a brand-new
    // item and renders in full — no remount/clear needed.
    const lastGroupDone = !!lastGroup.message?.metadata?.streamEnd;
    const lastGroupSubtype = lastGroup.message?.metadata?.subtype;
    const lastGroupStreaming =
      !lastGroupDone &&
      (lastGroupSubtype === 'answer' ||
        lastGroupSubtype === 'thinking' ||
        lastGroupSubtype === 'tool_use');

    // One-shot diffs and completed plan summaries can leave the dynamic area
    // immediately, without flickering as pending tool boxes. Other tool boxes
    // retain their existing height-based placement.
    const lastToolContent = (lastGroup.message.content || '').replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();
    const lastGroupIsCompletedTool = !lastGroup.isAggregated && lastGroupDone && lastGroupSubtype === 'tool_use' &&
      (isRenderableToolDiff(lastToolContent) ||
        (parseToolCall(lastToolContent)?.type === 'todo_write' &&
          (isTodoWriteAllCompleted(lastToolContent) || lastToolContent === 'Clearing todo list')));

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
      // already done — exactly the same rule used in the non-remount path
      // below (a still-streaming group stays pending even when too tall).
      if (!lastGroupIsCompletedTool &&
          (lastGroupStreaming || (!lastGroupDone && estimatedLines <= halfHeight))) {
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


    // If last group is small enough — or still streaming (see above) — keep
    // it as pending (dynamic render). While pending, Message truncates the
    // rendered view to a bounded tail, so an over-tall streaming group (e.g.
    // a very long thinking block) stays visible and keeps updating instead
    // of freezing inside Static.
    if (!lastGroupIsCompletedTool && (estimatedLines <= halfHeight || lastGroupStreaming)) {
      lastStaticGroupSignaturesRef.current = currentSignatures.slice(0, -1);
      return {
        staticGroups: allGroups.slice(0, -1),
        pendingGroups: [lastGroup],
      };
    }

    // Otherwise, put everything in static. A completed (streamEnd) over-tall
    // group entering Static here was pending until now, so Static sees it as
    // a brand-new item and renders its full final content in one shot.
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
              parts.push(count === 1 ? 'Search 1 query' : `Search ${count} queries`);
              break;
            case 'analyze':
              parts.push(count === 1 ? 'Analyze 1 file' : `Analyze ${count} files`);
              break;
            case 'web':
              parts.push(count === 1 ? 'Web 1 request' : `Web ${count} requests`);
              break;
            case 'browser':
              parts.push(count === 1 ? 'Browse 1 action' : `Browse ${count} actions`);
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
              parts.push(count === 1 ? 'Delegate 1 sub-agent task' : `Delegate ${count} sub-agent tasks`);
              break;
            case 'lark':
              parts.push(count === 1 ? '1 Lark notification' : `${count} Lark notifications`);
              break;
          }
        }
        
        // Group by type and build tree preview
        const MAX_PREVIEW_PER_TYPE = 20;
        const groupedByType = new Map<string, string[]>();
        
        tools.forEach(tool => {
          let items = groupedByType.get(tool.type) || [];

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
            <ToolHeading parts={parts} hint="ctrl+o to expand" />

            <Box flexDirection="column" paddingLeft={2}>
              {Array.from(groupedByType.entries()).map(([type, items], typeIndex) => {
                const previewItems = items.slice(0, MAX_PREVIEW_PER_TYPE);
                const hiddenCount = items.length - previewItems.length;
                const isLastType = typeIndex === groupedByType.size - 1;
                const totalItemsInGroup = previewItems.length + (hiddenCount > 0 ? 1 : 0);
                
                return (
                  <Box key={type} flexDirection="column">
                    {previewItems.map((item, itemIndex) => {
                      const isLastInGroup = itemIndex === previewItems.length - 1 && hiddenCount === 0;
                      const prefix = isLastInGroup && isLastType ? '└─ ' : '├─ ';
                      return (
                        <Box key={itemIndex}>
                          <Text color={colors.content.secondary}>
                            {prefix}{item}
                          </Text>
                        </Box>
                      );
                    })}

                    {hiddenCount > 0 && (
                      <Box>
                        <Text color={colors.content.secondary}>
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
