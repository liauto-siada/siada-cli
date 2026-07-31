/**
 * ProcessBox Component
 * Displays collapsed process information (THINKING, TOOL USE, etc.)
 * Maximum 10 lines, shows indicator if more content exists
 * Press Ctrl+O to expand/collapse
 */

import React, { useMemo, useState } from 'react';
import { Box, Text } from '@jrichman/ink';
import { Message } from '../../types/index.js';
import { MAX_TEXT_LENGTH } from '../../constants/limits.js';
import { getIcons } from '../../constants/icons.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { MarkdownDisplay } from '../markdown/MarkdownDisplay.js';
import { ShellOutput } from '../Shell/ShellOutput.js';
import { DiffView } from '../diff/DiffView.js';
import { parseFileEditContent, getSimplePatch } from '../../utils/diff.js';

/**
 * Calculate total wrapped lines considering terminal width
 * @param content - Message content
 * @param terminalWidth - Terminal width (defaults to process.stdout.columns or 80)
 * @returns Total physical lines occupied
 */
function calculateWrappedLines(content: string, terminalWidth?: number): number {
  const width = terminalWidth || process.stdout.columns || 80;
  // Subtract border and padding (1 char padding + 1 char border on each side)
  const effectiveWidth = Math.max(width - 4, 20);
  
  let totalLines = 0;
  const lines = content.split('\n');
  
  for (const line of lines) {
    if (line.length === 0) {
      totalLines += 1;
    } else {
      // Calculate physical rows needed for this line (including soft wraps)
      let lineWidth = 0;
      let physicalLines = 1;
      
      for (const char of line) {
        const charWidth = /[\u4e00-\u9fa5]/.test(char) ? 2 : 1;
        lineWidth += charWidth;
        
        if (lineWidth > effectiveWidth) {
          physicalLines += 1;
          lineWidth = charWidth;
        }
      }
      
      totalLines += physicalLines;
    }
  }
  
  return totalLines;
}

/**
 * Truncate content to specified number of display lines
 * @param content - Original content
 * @param maxLines - Maximum line count
 * @param terminalWidth - Terminal width
 * @returns Truncated content
 */
function truncateContentByLines(content: string, maxLines: number, terminalWidth?: number): string {
  const width = terminalWidth || process.stdout.columns || 80;
  const effectiveWidth = Math.max(width - 4, 20);
  
  let currentLines = 0;
  const lines = content.split('\n');
  const resultLines: string[] = [];
  
  for (const line of lines) {
    if (currentLines >= maxLines) {
      break;
    }
    
    if (line.length === 0) {
      resultLines.push(line);
      currentLines += 1;
    } else {
      let lineWidth = 0;
      let physicalLines = 1;
      
      for (const char of line) {
        const charWidth = /[\u4e00-\u9fa5]/.test(char) ? 2 : 1;
        lineWidth += charWidth;
        
        if (lineWidth > effectiveWidth) {
          physicalLines += 1;
          lineWidth = charWidth;
        }
      }
      
      if (currentLines + physicalLines > maxLines) {
        const remainingLines = maxLines - currentLines;
        if (remainingLines > 0) {
          let charCount = 0;
          let currentLineWidth = 0;
          let usedLines = 1;
          
          for (const char of line) {
            const charWidth = /[\u4e00-\u9fa5]/.test(char) ? 2 : 1;
            
            if (currentLineWidth + charWidth > effectiveWidth) {
              usedLines += 1;
              currentLineWidth = charWidth;
            } else {
              currentLineWidth += charWidth;
            }
            
            if (usedLines > remainingLines) {
              break;
            }
            
            charCount++;
          }
          
          if (charCount > 0) {
            resultLines.push(line.substring(0, charCount) + '...');
          }
        }
        break;
      } else {
        resultLines.push(line);
        currentLines += physicalLines;
      }
    }
  }
  
  return resultLines.join('\n');
}

export interface ProcessBoxProps {
  messages: Message[]; // Process messages (thinking, tool_use, etc.)
  maxLines?: number; // Maximum lines to show when collapsed (default: 10)
  isFocused?: boolean; // Whether this box can receive keyboard input
}

/**
 * Extract clean content from process message
 * Truncate if too long to prevent memory issues
 */
function extractCleanContent(content: string): string {
  // Truncate if too long
  let safeContent = content;
  if (content.length > MAX_TEXT_LENGTH) {
    safeContent = content.substring(0, MAX_TEXT_LENGTH) + '... [Content truncated due to length]';
  }
  
  // Remove box-drawing characters (╭, ╮, ╰, ╯, │, ─)
  let cleaned = safeContent.replace(/[╭╮╰╯│─]/g, '');
  
  // Remove arrow and **TYPE** headers
  cleaned = cleaned.replace(/[▶►]\s*\*\*[A-Z\s]+\*\*/g, '');
  
  // Remove token counter line
  cleaned = cleaned.replace(/[\d,]+\s*\/\s*[\d,]+\s+tokens?/gi, '');
  
  return cleaned.trim();
}

/**
 * Extract tool call summary from message
 */
function extractToolCallSummary(content: string): { toolName: string; description: string } | null {
  // Match "Siada wants to use the tool: <name>"
  const toolMatch = content.match(/Siada wants to use the tool:\s*(\w+)/i);
  if (toolMatch) {
    return {
      toolName: toolMatch[1],
      description: content.substring(0, 80).trim() + (content.length > 80 ? '...' : '')
    };
  }
  
  // Match success/error markers for file operations
  const resultMatch = content.match(/\[(?:OK|X)\]\s*(.+)|[✓✗]\s*(.+)/);
  if (resultMatch) {
    return {
      toolName: 'result',
      description: (resultMatch[1] || resultMatch[2] || '').trim()
    };
  }
  
  return null;
}

// 🔥 Use React.memo to prevent unnecessary re-renders
export const ProcessBox: React.FC<ProcessBoxProps> = React.memo(({ 
  messages, 
  maxLines = 10,
  isFocused = true
}) => {
  const icons = getIcons();
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Get terminal width for markdown rendering
  const terminalWidth = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.columns) || 80;

  // 🔥 Handle Ctrl+O to toggle expansion - using custom useKeypress
  // Wrapped in try-catch to handle cases where KeypressProvider is not available
  try {
    useKeypress((key) => {
      if (isFocused && key.ctrl && key.name === 'o') {
        setIsExpanded(prev => !prev);
      }
    });
  } catch (error) {
    // KeypressProvider not available, keyboard shortcuts disabled
  }

  // Separate shell messages from other messages
  const { shellMessages, otherMessages } = useMemo(() => {
    const shell: Message[] = [];
    const other: Message[] = [];
    
    // Get terminal height with 2-line reserve for borders and UI
    const terminalHeight = process.stdout.rows || 24;
    const maxDisplayLines = Math.max(terminalHeight /2 , 5);
    
    messages.forEach(msg => {
      const subtype = msg.metadata?.subtype ?? 'process';
      
      const targetArray = subtype === 'shell' ? shell : other;
      
      // Truncate messages that wrap beyond terminal height, replacing excess with ...
      let processedMsg = msg;
      
      if (!isExpanded) {
        const actualLines = calculateWrappedLines(msg.content);
        
        if (actualLines > maxDisplayLines) {
          const truncatedContent = truncateContentByLines(msg.content, maxDisplayLines);
          const omittedLines = actualLines - maxDisplayLines;
          
          processedMsg = { 
            ...msg, 
            content: truncatedContent + `\n... hiden ${omittedLines} lines`
          };
        }
      }
      
      targetArray.push(processedMsg);
    });
    
    return { shellMessages: shell, otherMessages: other };
  }, [messages, isExpanded]);


  // Combine all messages into sections for display
  const sections = useMemo(() => {
    const result: Array<
      | { type: 'answer' | 'process'; content: string }
      | { type: 'diff'; filePath: string; hunks: ReturnType<typeof getSimplePatch> }
    > = [];
    
    otherMessages.forEach(msg => {
      const subtype = msg.metadata?.subtype;
      const cleaned = extractCleanContent(msg.content);
      
      if (!cleaned) {
        return;
      }

      // Detect completed file-edit tool calls and render as diff
      if (subtype === 'tool_use' || msg.metadata?.streamEnd === true) {
        const editInfo = parseFileEditContent(cleaned);
        if (editInfo?.isComplete) {
          const hunks = getSimplePatch(editInfo.filePath, editInfo.oldString, editInfo.newString);
          if (hunks.length > 0) {
            result.push({ type: 'diff', filePath: editInfo.filePath, hunks });
            return;
          }
        }
      }
      
      // Route by message type: answer vs process
      const isAnswer = 
        subtype === 'answer' || 
        (!subtype && !msg.content.includes('Siada wants to use') && !msg.content.match(/\[OK\]|✓/));
      
      result.push({ 
        type: isAnswer ? 'answer' : 'process', 
        content: cleaned 
      });
    });
    
    return result;
  }, [otherMessages]);

  const hasContent = sections.length > 0;
  const shouldShowSummary = !isExpanded && hasContent;

  if (messages.length === 0) {
    return null;
  }

  // Simplified version: only display model output content without additional information
  return (
    <Box 
      flexDirection="column" 
      borderStyle="round" 
      borderColor="gray"
      paddingX={1}
      marginBottom={1}
    >
      {/* Render shell execution information */}
      {shellMessages.length > 0 && shellMessages.map((msg, idx) => {
        const shellExecution = msg.metadata?.shellExecution;
        if (shellExecution) {
          return (
            <Box key={msg.id} marginBottom={idx < shellMessages.length - 1 ? 1 : 0}>
              <ShellOutput
                command={shellExecution.command}
                executing={shellExecution.executing}
                stdout={shellExecution.stdout}
                stderr={shellExecution.stderr}
                exitCode={shellExecution.exitCode}
                duration={shellExecution.duration}
                isBinary={shellExecution.isBinary}
                error={shellExecution.error}
              />
            </Box>
          );
        }
        return null;
      })}

      {/* Display all message content directly */}
      <Box flexDirection="column">
        {sections.map((section, idx) => (
          <Box key={idx} marginBottom={idx < sections.length - 1 ? 1 : 0}>
            {section.type === 'diff' ? (
              <DiffView
                filePath={section.filePath}
                hunks={section.hunks}
                width={Math.max(terminalWidth - 4, 40)}
              />
            ) : (
              <MarkdownDisplay 
                text={section.content} 
                isPending={false} 
                terminalWidth={Math.max(terminalWidth - 6, 40)}
              />
            )}
          </Box>
        ))}
      </Box>
    </Box>
  );
});
