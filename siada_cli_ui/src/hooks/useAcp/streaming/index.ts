import { useRef, useCallback, Dispatch, SetStateAction, MutableRefObject } from 'react';
import { Writable } from 'stream';
import { Message } from '../../../types/index.js';
import { BannerInfo, TodoItem, TodoMessageRange } from '../types.js';
import { logger } from '../../../utils/logger.js';
import {
  findLastSafeSplitPoint,
  countLines,
  findEnclosingCodeBlockStart,
} from '../../../utils/markdownUtilities.js';
import {
  StreamRepetitionDetector,
  isRepetitionGuardModel,
} from '../../../utils/streamRepetition.js';
import { COMPACTION_CONTENT_PATTERN, ThinkingStep } from '../../../constants/phrases.js';
import { isRenderableToolDiff } from '../../../utils/diff.js';
import { parseTodoWriteContent } from '../../../utils/todoWrite.js';

// Throttle interval for streaming message flushes.
// 50-120ms is the sweet spot: lower causes too-frequent redraws, higher hurts the "typing" feel.
const STREAM_FLUSH_MS = 80;

interface StreamingDeps {
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setBannerInfo: Dispatch<SetStateAction<BannerInfo | null>>;
  stdout: (Writable & { rows?: number }) | null;
  workingDir: string;
  model: string | undefined;
  pullHistoryTimeoutRef: MutableRefObject<NodeJS.Timeout | null>;
  messagesRef: MutableRefObject<Message[]>;
  setTodoItems: Dispatch<SetStateAction<TodoItem[]>>;
  setTodoMessageRanges: Dispatch<SetStateAction<Map<string, TodoMessageRange>>>;
  setActiveStep?: Dispatch<SetStateAction<ThinkingStep | null>>;
}


/**
 * Classify an agent message into the current agent activity step, used to
 * label the thinking indicator / thinking content:
 *   - thinking / answer streams → model reasoning
 *   - tool_use streams         → tool execution
 *   - non-streaming notices mentioning compaction (e.g. the backend's
 *     "Compacting context..." from /compact) → context compaction
 *   - anything else (process/system notices)  → system processing
 *
 * NOTE on ordering: the backend maps most one-shot notices (info, warning,
 * tool results) to subtype 'tool_use' for rendering (see adapter
 * handleWarning/handleToolResult), so compaction content matching must run
 * BEFORE the tool_use check and only for non-streaming messages — otherwise
 * a "Compacting context..." notice would be misclassified as tool execution.
 */
function classifyAgentStep(message: Message): ThinkingStep {
  const subtype = message.metadata?.subtype;
  if (subtype === 'thinking' || subtype === 'answer') return 'reasoning';
  const isStreaming = message.metadata?.isStreaming !== false;
  if (!isStreaming && COMPACTION_CONTENT_PATTERN.test(message.content || '')) return 'compaction';
  if (subtype === 'tool_use') return 'tool_execution';
  return 'system_processing';
}

export function useStreamingMessages({ setMessages, setBannerInfo, stdout, workingDir, model, pullHistoryTimeoutRef, messagesRef, setTodoItems, setTodoMessageRanges, setActiveStep }: StreamingDeps) {
  const toolMessageIdCounterRef = useRef(0);
  const currentStreamingMessageRef = useRef<{
    id: string;
    type: 'answer' | 'thinking' | 'tool_use' | null;
  } | null>(null);
  const accumulatedContentRef = useRef<string>('');
  const splitCounterRef = useRef<number>(0);

  // ------------------------------
  // Stream throttling: coalesce frequent answer/thinking/tool_use chunks
  // ------------------------------
  const streamFlushTimerRef = useRef<NodeJS.Timeout | null>(null);
  const streamPendingAppendRef = useRef<string>('');
  const streamTargetSubtypeRef = useRef<'answer' | 'thinking' | 'tool_use' | null>(null);

  // ------------------------------
  // Repetition guard (deepseek-v4-flash family only):
  // while a stream looks repetitive we HOLD rendering (stop flushing) and wait
  // for the backend's verdict — a `stream_aborted` lifecycle event means the
  // backend caught the same loop and is retrying, so the held/rendered content
  // is dropped. A normal streamEnd means false positive → flush as usual.
  // ------------------------------
  const repetitionDetectorRef = useRef<StreamRepetitionDetector | null>(null);
  const streamHeldRef = useRef<boolean>(false);

  const flushStreamingNow = useCallback(() => {
    if (streamFlushTimerRef.current) {
      clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }

    const subtype = streamTargetSubtypeRef.current;

    if (subtype === 'answer') {
      // Repetition guard hold: don't flush suspicious content to the screen.
      if (streamHeldRef.current) {
        streamPendingAppendRef.current = '';
        return;
      }
      const fullContent = accumulatedContentRef.current;
      streamPendingAppendRef.current = '';
      if (!fullContent) return;

      // Guard: if the pending portion of the answer is too tall for the dynamic
      // (non-Static) area, skip the overwrite. The target message is likely
      // already in Static — overwriting its content would change content.length,
      // which (before the signature fix) triggered a flicker loop of
      // clear-screen + remount every 80ms.
      //
      // The content will still be flushed when:
      //   - A split happens in handleAgentMessage (freezes old part, creates new pending block)
      //   - The stream ends (streamEnd handler sets final content + metadata)
      //   - A new stream starts (flushStreamingNow is called explicitly)
      const splitPoint = findLastSafeSplitPoint(fullContent);
      const afterText = fullContent.substring(splitPoint);
      const afterLines = countLines(afterText);
      const terminalHeight = stdout?.rows || 50;
      const maxDynamicLines = Math.max(terminalHeight / 2, 5);

      if (afterLines > maxDynamicLines) {
        logger.debug('flushStreamingNow skipped — answer content too tall for pending area', {
          component: 'Streaming',
          operation: 'flush_skip',
          afterLines,
          maxDynamicLines,
          contentLength: fullContent.length,
        });
        return;
      }

      setMessages(prev => {
        for (let i = prev.length - 1; i >= 0; i--) {
          const m = prev[i];
          if (m.type === 'agent' && m.metadata?.subtype === 'answer') {
            const updated = [...prev];
            updated[i] = { ...m, content: fullContent };
            return updated;
          }
        }
        return prev;
      });
      return;
    }

    // For thinking / tool_use: keep the original append logic
    const append = streamPendingAppendRef.current;
    if (!append || subtype === null) {
      streamPendingAppendRef.current = '';
      return;
    }

    streamPendingAppendRef.current = '';

    setMessages(prev => {
      // Scan from the tail to find the latest message with the same subtype, avoiding index races
      for (let i = prev.length - 1; i >= 0; i--) {
        const m = prev[i];
        if (m.type === 'agent' && m.metadata?.subtype === subtype) {
          const updated = [...prev];
          updated[i] = { ...m, content: (m.content || '') + append };
          return updated;
        }
      }
      return prev;
    });
  }, [setMessages, stdout]);

  const scheduleStreamingFlush = useCallback(() => {
    if (streamFlushTimerRef.current) return;
    streamFlushTimerRef.current = setTimeout(() => {
      streamFlushTimerRef.current = null;
      flushStreamingNow();
    }, STREAM_FLUSH_MS);
  }, [flushStreamingNow]);

  const resetStreaming = useCallback(() => {
    if (streamFlushTimerRef.current) {
      clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }
    // Clear pullHistory timeout
    if (pullHistoryTimeoutRef.current) {
      clearTimeout(pullHistoryTimeoutRef.current);
      pullHistoryTimeoutRef.current = null;
    }
    streamPendingAppendRef.current = '';
    streamTargetSubtypeRef.current = null;
    currentStreamingMessageRef.current = null;
    accumulatedContentRef.current = '';
    splitCounterRef.current = 0;
    repetitionDetectorRef.current = null;
    streamHeldRef.current = false;
  }, []);

  const handleAgentMessage = useCallback((message: Message) => {
    if (message.metadata?.reason === 'quota_update') {
      try {
        const info = JSON.parse(message.content);
        setBannerInfo(prev => prev ? { ...prev, quotaUsage: info.quota_usage ?? null } : prev);
      } catch (e) {
        logger.error('Failed to parse quota_update', e);
      }
      return;
    }

    if (message.metadata?.reason === 'banner_info' && message.metadata?.type === 'banner') {
      try {
        const info = JSON.parse(message.content);
        setBannerInfo({
          version: info.version,
          workingDir: info.working_dir || workingDir,
          agent: info.agent || 'coder',
          provider: info.provider || 'default',
          model: info.model || model,
          prePlanMode: info.pre_plan || false,
          thinkingTokens: info.thinking_tokens,
          reasoningEffort: info.reasoning_effort,
          thinkingEnabled: info.thinking_enabled ?? undefined,
          parallelToolCalls: info.parallel_tool_calls,
          quotaUsage: info.quota_usage ?? null,
          memoryEnabled: info.memory_enabled ?? true,
        });
        logger.info('Banner info updated', { info });
      } catch (e) {
        logger.error('Failed to parse banner info', e);
      }
      return;
    }

    const subtype = message.metadata?.subtype;
    const isStreamingChunk = subtype === 'answer' || subtype === 'thinking' || subtype === 'tool_use';
    const streamEnd = message.metadata?.streamEnd || false;

    // Track the current agent activity step (reasoning / tool execution /
    // system processing / compaction) for the thinking indicator's label.
    if (setActiveStep) setActiveStep(classifyAgentStep(message));

    if (isStreamingChunk) {
      const shouldStartNewStream = !currentStreamingMessageRef.current ||
                                   currentStreamingMessageRef.current.type !== subtype ||
                                   streamEnd;

      if (!shouldStartNewStream) {
        streamPendingAppendRef.current += message.content;
        streamTargetSubtypeRef.current = subtype as 'answer' | 'thinking' | 'tool_use';

        if (subtype === 'answer') {
          accumulatedContentRef.current += message.content;

          // Repetition guard (whitelisted models: deepseek-v4-flash family,
          // lpai-glm-5.3): once the tail of this stream is a repeating loop,
          // stop flushing to the screen and wait for the backend verdict
          // (stream_aborted vs normal streamEnd).
          if (isRepetitionGuardModel(model)) {
            if (streamHeldRef.current) {
              // Already holding — keep buffering, render nothing more.
              return;
            }
            if (!repetitionDetectorRef.current) {
              repetitionDetectorRef.current = new StreamRepetitionDetector();
            }
            const hit = repetitionDetectorRef.current.feed(message.content);
            if (hit) {
              streamHeldRef.current = true;
              logger.warn('Repetition suspected in answer stream — holding render until backend verdict', {
                component: 'Streaming',
                operation: 'repetition_hold',
                kind: repetitionDetectorRef.current.kind,
                unitLength: hit.unit.length,
                repeats: hit.repeats,
                unitPreview: hit.unit.slice(0, 80),
              });
              return;
            }
          }

          // If inside an unfinished code block, only render the stable content before it
          const enclosingCodeBlockStart = findEnclosingCodeBlockStart(
            accumulatedContentRef.current,
            accumulatedContentRef.current.length,
          );

          if (enclosingCodeBlockStart !== -1) {
            const beforeCodeBlock = accumulatedContentRef.current.substring(0, enclosingCodeBlockStart);
            streamPendingAppendRef.current = '';
            if (streamFlushTimerRef.current) {
              clearTimeout(streamFlushTimerRef.current);
              streamFlushTimerRef.current = null;
            }
            setMessages(prev => {
              for (let i = prev.length - 1; i >= 0; i--) {
                const m = prev[i];
                if (m.type === 'agent' && m.metadata?.subtype === 'answer') {
                  const updated = [...prev];
                  updated[i] = { ...m, content: beforeCodeBlock };
                  return updated;
                }
              }
              return prev;
            });
            return;
          }

          const splitPoint = findLastSafeSplitPoint(accumulatedContentRef.current);
          const afterText = accumulatedContentRef.current.substring(splitPoint);
          const afterLines = countLines(afterText);
          const terminalHeight = stdout?.rows || 50;
          const maxDynamicLines = Math.max(terminalHeight / 2, 5);

          if (afterLines > maxDynamicLines) {
            return;
          }

          if (splitPoint < accumulatedContentRef.current.length) {
            const beforeText = accumulatedContentRef.current.substring(0, splitPoint);
            flushStreamingNow();
            splitCounterRef.current += 1;
            const splitIndex = splitCounterRef.current;

            let originalMetadata: any = {};
            setMessages(prev => {
              for (let i = prev.length - 1; i >= 0; i--) {
                const m = prev[i];
                if (m.type === 'agent' && m.metadata?.subtype === 'answer') {
                  originalMetadata = m.metadata;
                  const updated = [...prev];
                  updated[i] = { ...m, content: beforeText };
                  return updated;
                }
              }
              return prev;
            });

            const newMessage: Message = {
              id: `${message.id}_split_${splitIndex}`,
              type: 'agent',
              content: afterText,
              timestamp: new Date().toISOString(),
              author: 'Siada',
              metadata: {
                ...originalMetadata,
                subtype: 'answer',
                streamEnd: false,
                splitIndex,
              },
            };

            setMessages(prev => [...prev, newMessage]);
            accumulatedContentRef.current = afterText;
            streamPendingAppendRef.current = '';
            currentStreamingMessageRef.current = { id: newMessage.id, type: 'answer' };
          } else {
            scheduleStreamingFlush();
          }
        } else {
          scheduleStreamingFlush();
        }

        currentStreamingMessageRef.current!.id = message.id;
      } else {
        flushStreamingNow();
        streamTargetSubtypeRef.current = null;
        streamPendingAppendRef.current = '';

        if (streamEnd) {
          setMessages(prev => {
            for (let i = prev.length - 1; i >= 0; i--) {
              const m = prev[i];
              if (m.type === 'agent' && m.metadata?.subtype === subtype) {
                const updated = [...prev];
                updated[i] = {
                  ...m,
                  content: subtype === 'answer'
                    ? (accumulatedContentRef.current || m.content || message.content)
                    : ((m.content || '') + (message.content || '')),
                  metadata: { ...m.metadata, ...message.metadata, streamEnd: true, isStreaming: false },
                };
                return updated;
              }
            }
            return [...prev, message];
          });
          currentStreamingMessageRef.current = null;
          accumulatedContentRef.current = '';
          // Stream ended normally — any repetition hold was a false positive;
          // the final flush above already wrote the full accumulated content.
          repetitionDetectorRef.current = null;
          streamHeldRef.current = false;
        } else {
          currentStreamingMessageRef.current = {
            id: message.id,
            type: subtype as 'answer' | 'thinking' | 'tool_use',
          };
          streamTargetSubtypeRef.current = subtype as 'answer' | 'thinking' | 'tool_use';
          setMessages(prev => [...prev, message]);
          if (subtype === 'answer') {
            accumulatedContentRef.current = message.content;
            splitCounterRef.current = 0;
            // New answer stream — re-arm the repetition detector.
            repetitionDetectorRef.current = null;
            streamHeldRef.current = false;
          }
        }
      }
    } else {
      flushStreamingNow();
      streamTargetSubtypeRef.current = null;
      streamPendingAppendRef.current = '';
      currentStreamingMessageRef.current = null;
      accumulatedContentRef.current = '';
      setMessages(prev => [...prev, message]);
    }
  }, [setMessages, setBannerInfo, stdout, workingDir, model, flushStreamingNow, scheduleStreamingFlush, setActiveStep]);

  /**
   * Backend confirmed the current stream was bad (repetition loop) and is
   * retrying the request. Discard everything this stream produced: drop the
   * pending/held buffers and remove any already-rendered messages carrying
   * this streamStartId. The retried request arrives as a brand-new stream.
   */
  const handleStreamAborted = useCallback((data: { streamStartId?: string; reason?: string }) => {
    const { streamStartId, reason } = data;
    logger.warn('Stream aborted by backend — discarding rendered content', {
      component: 'Streaming',
      operation: 'stream_aborted',
      streamStartId,
      reason,
      wasHeld: streamHeldRef.current,
    });

    if (streamFlushTimerRef.current) {
      clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }
    streamPendingAppendRef.current = '';
    streamTargetSubtypeRef.current = null;
    currentStreamingMessageRef.current = null;
    accumulatedContentRef.current = '';
    repetitionDetectorRef.current = null;
    streamHeldRef.current = false;

    if (streamStartId) {
      setMessages(prev => {
        const kept = prev.filter(m => m.metadata?.streamStartId !== streamStartId);
        if (kept.length !== prev.length) {
          logger.warn('Dropped aborted stream messages', {
            component: 'Streaming',
            operation: 'stream_aborted_drop',
            streamStartId,
            droppedCount: prev.length - kept.length,
          });
        }
        return kept;
      });
    }
  }, [setMessages]);

  const handleToolUse = useCallback((toolData: any) => {
    const chunkIndex = toolData.metadata?.chunkIndex ?? 0;
    const isFinal = toolData.metadata.streamEnd;
    const content = toolData.content || '';

    // Tool call streaming — the agent is currently executing a tool.
    // Exception: one-shot notices (the backend maps print_info/warning to
    // tool_use events, e.g. "Compacting context..." from auto-compaction)
    // are classified as context compaction instead.
    if (setActiveStep) {
      setActiveStep(
        isFinal && COMPACTION_CONTENT_PATTERN.test(content)
          ? 'compaction'
          : 'tool_execution',
      );
    }

    if (chunkIndex === 0) {
      flushStreamingNow();
      streamTargetSubtypeRef.current = null;
      streamPendingAppendRef.current = '';
      currentStreamingMessageRef.current = null;
      accumulatedContentRef.current = '';
      const toolMessageId = `tool_${Date.now()}_${toolMessageIdCounterRef.current++}`;
      const newMessage: Message = {
        id: toolMessageId,
        type: 'agent',
        content,
        timestamp: new Date().toISOString(),
        author: 'Siada',
        // Only complete one-shot diff boxes bypass the dynamic area. Leave
        // all other tool messages and the chunked tool path unchanged.
        metadata: {
          subtype: 'tool_use',
          chunkIndex,
          ...(isFinal && isRenderableToolDiff(content) ? { streamEnd: true } : {}),
        },
      };
      currentStreamingMessageRef.current = { id: newMessage.id, type: 'tool_use' };
      setMessages(prev => [...prev, newMessage]);
    } else if (currentStreamingMessageRef.current?.type === 'tool_use') {
      setMessages(prev => {
        for (let i = prev.length - 1; i >= 0; i--) {
          const m = prev[i];
          if (m.type === 'agent' && m.metadata?.subtype === 'tool_use') {
            const updated = [...prev];
            updated[i] = { ...m, content: (m.content || '') + content, metadata: { ...m.metadata, chunkIndex } };
            return updated;
          }
        }
        return prev;
      });
    }

    if (isFinal) {
      flushStreamingNow();
      streamTargetSubtypeRef.current = null;
      streamPendingAppendRef.current = '';
      currentStreamingMessageRef.current = null;
      accumulatedContentRef.current = '';

      // Parse todo_write content and update todo state immediately (before ACP notification arrives)
      // Use setMessages functional form to read the latest state after flushStreamingNow
      setMessages(prev => {
        let finalContent = content;
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].metadata?.subtype === 'tool_use') {
            finalContent = prev[i].content || content;
            break;
          }
        }
        const parsed = parseTodoWriteContent(finalContent);
        if (parsed !== null) {
          setTodoItems(parsed);
          const currentMsgCount = prev.length;
          setTodoMessageRanges(prevRanges => {
            const next = new Map(prevRanges);
            // Close previously open in_progress ranges that are no longer in_progress
            for (const [key, range] of next.entries()) {
              if (range.endIdx === null) {
                const stillInProgress = parsed.some(t => t.content === key && t.status === 'in_progress');
                if (!stillInProgress) {
                  next.set(key, { ...range, endIdx: currentMsgCount });
                }
              }
            }
            // Open new in_progress ranges
            for (const todo of parsed) {
              if (todo.status === 'in_progress' && !next.has(todo.content)) {
                next.set(todo.content, { startIdx: currentMsgCount, endIdx: null });
              }
            }
            return next;
          });
        }
        return prev; // messages state unchanged, we only read it
      });
    }
  }, [setMessages, flushStreamingNow, setTodoItems, setTodoMessageRanges, setActiveStep]);

  return { flushStreamingNow, resetStreaming, handleAgentMessage, handleToolUse, handleStreamAborted };
}
