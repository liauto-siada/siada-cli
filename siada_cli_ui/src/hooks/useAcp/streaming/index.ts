import { useRef, useCallback, Dispatch, SetStateAction } from 'react';
import { Writable } from 'stream';
import { Message } from '../../../types/index.js';
import { BannerInfo } from '../types.js';
import { logger } from '../../../utils/logger.js';
import {
  findLastSafeSplitPoint,
  countLines,
  findEnclosingCodeBlockStart,
} from '../../../utils/markdownUtilities.js';

// Throttle interval for streaming message flushes.
// 50-120ms is the sweet spot: lower causes too-frequent redraws, higher hurts the "typing" feel.
const STREAM_FLUSH_MS = 80;

interface StreamingDeps {
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setBannerInfo: Dispatch<SetStateAction<BannerInfo | null>>;
  stdout: (Writable & { rows?: number }) | null;
  workingDir: string;
  model: string | undefined;
}

export function useStreamingMessages({ setMessages, setBannerInfo, stdout, workingDir, model }: StreamingDeps) {
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

  const flushStreamingNow = useCallback(() => {
    if (streamFlushTimerRef.current) {
      clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }

    const subtype = streamTargetSubtypeRef.current;

    if (subtype === 'answer') {
      const fullContent = accumulatedContentRef.current;
      streamPendingAppendRef.current = '';
      if (!fullContent) return;

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
  }, [setMessages]);

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
    streamPendingAppendRef.current = '';
    streamTargetSubtypeRef.current = null;
    currentStreamingMessageRef.current = null;
    accumulatedContentRef.current = '';
    splitCounterRef.current = 0;
  }, []);

  const handleAgentMessage = useCallback((message: Message) => {
    if (message.metadata?.reason === 'banner_info' && message.metadata?.type === 'banner') {
      try {
        const info = JSON.parse(message.content);
        setBannerInfo({
          version: info.version,
          workingDir: info.working_dir || workingDir,
          agent: info.agent || 'coder',
          provider: info.provider || 'li',
          model: info.model || model,
          prePlanMode: info.pre_plan || false,
          thinkingTokens: info.thinking_tokens,
          reasoningEffort: info.reasoning_effort,
          parallelToolCalls: info.parallel_tool_calls,
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

    if (isStreamingChunk) {
      const shouldStartNewStream = !currentStreamingMessageRef.current ||
                                   currentStreamingMessageRef.current.type !== subtype ||
                                   streamEnd;

      if (!shouldStartNewStream) {
        streamPendingAppendRef.current += message.content;
        streamTargetSubtypeRef.current = subtype as 'answer' | 'thinking' | 'tool_use';

        if (subtype === 'answer') {
          accumulatedContentRef.current += message.content;

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
  }, [setMessages, setBannerInfo, stdout, workingDir, model, flushStreamingNow, scheduleStreamingFlush]);

  const handleToolUse = useCallback((toolData: any) => {
    const chunkIndex = toolData.metadata?.chunkIndex ?? 0;
    const isFinal = toolData.metadata.streamEnd;
    const content = toolData.content || '';

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
        metadata: { subtype: 'tool_use', chunkIndex },
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
    }
  }, [setMessages, flushStreamingNow]);

  return { flushStreamingNow, resetStreaming, handleAgentMessage, handleToolUse };
}
