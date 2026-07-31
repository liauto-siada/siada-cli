/**
 * AgentMessage Component
 * Renders a complete agent message with Thinking, Answer, and Tool Use
 * Displays them in order: Thinking -> Answer -> Tool Use
 */

import React from 'react';
import { Box } from '@jrichman/ink';
import { Message } from '../../types/index.js';
import { ProcessBox } from './ProcessBox.js';
import { MarkdownDisplay } from '../markdown/MarkdownDisplay.js';

export interface AgentMessageProps {
  thinkingMessages?: Message[];
  answerMessage?: Message;
  toolMessages?: Message[];
  extractCleanContent: (content: string) => string;
  isCollapsed?: boolean;  // Collapse mode - hide tool use messages
  isSplitContent?: boolean;  // Marks this as a split content fragment
}

export const AgentMessage: React.FC<AgentMessageProps> = ({
  thinkingMessages = [],
  answerMessage,
  toolMessages = [],
  extractCleanContent,
  isCollapsed = false,
  isSplitContent = false,
}) => {
  const isLastSplit = answerMessage?.metadata?.isLastSplit ?? false;
  const splitIndex = answerMessage?.metadata?.splitIndex ?? 0;
  
  // Get terminal width for markdown rendering
  const terminalWidth = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.columns) || 80;
  
  return (
    <>
      {/* Thinking message: only shown on first fragment */}
      {thinkingMessages.length > 0 && (!isSplitContent || splitIndex === 0) && (() => {
        const elements: React.ReactNode[] = [];
        for (let i = 0; i < thinkingMessages.length; i++) {
          const msg = thinkingMessages[i];
          const cleanContent = extractCleanContent(msg.content).replace(/^\n+/, '').trim();
          if (cleanContent.length === 0) continue;
          elements.push(
            <Box key={`thinking_${i}`} marginBottom={1}>
              <MarkdownDisplay 
                text={cleanContent} 
                isPending={false} 
                terminalWidth={terminalWidth}
              />
            </Box>
          );
        }
        return elements;
      })()}

      {answerMessage && (() => {
        let cleanContent = extractCleanContent(answerMessage.content);
        if (cleanContent.trim().length === 0) return null;
        
        // In collapsed mode, replace trailing colon with period
        if (isCollapsed && (!isSplitContent || isLastSplit) && (cleanContent.endsWith(':') || cleanContent.endsWith('：'))) {
          cleanContent = cleanContent.slice(0, -1) + (cleanContent.endsWith(':') ? '.' : '。');
        }
        
        return (
          <Box marginBottom={isSplitContent && !isLastSplit ? 0 : 1}>
            {/* No bottom margin between non-last split fragments */}
            <MarkdownDisplay 
              text={cleanContent} 
              isPending={false} 
              terminalWidth={terminalWidth}
            />
          </Box>
        );
      })()}

      {/* Tool use: only shown on last or non-split fragment */}
      {!isCollapsed && (!isSplitContent || isLastSplit) && toolMessages.length > 0 && (
        <ProcessBox messages={toolMessages} maxLines={10} isFocused={true} />
      )}
    </>
  );
};
