/**
 * MarkdownText Component
 * Renders markdown content with proper formatting for terminal
 * 
 * Note: ink-markdown is incompatible with Ink v5 due to ESM/CommonJS issues.
 * This component uses a custom renderer with chalk for terminal styling.
 */

import React from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import { logger } from '../../utils/logger.js';
import { RenderInline } from '../markdown/InlineMarkdownRenderer.js';
import { colorizeCode } from '../markdown/CodeColorizer.js';
import { TableRenderer } from '../markdown/TableRenderer.js';

export interface MarkdownTextProps {
  content: string;
  dimColor?: boolean;
}

/**
 * Parse and render markdown with terminal colors
 * Supports: headings, bold, italic, code blocks, inline code, lists
 */
function renderMarkdownLine(line: string, dimColor: boolean = false): React.ReactNode {
  // Empty line
  if (line.trim() === '') {
    return <Text key={Math.random()} dimColor={dimColor}>{' '}</Text>;
  }

  // Headings
  const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
  if (headingMatch) {
    const level = headingMatch[1].length;
    const text = headingMatch[2];
    const color = level === 1 ? 'cyan' : level === 2 ? 'blue' : 'white';
    return (
      <Text key={Math.random()} bold color={color as any}>
        <RenderInline text={text} defaultColor={color as any} />
      </Text>
    );
  }

  // Code block markers (```)
  if (line.trim().startsWith('```')) {
    return (
      <Text key={Math.random()} dimColor color="gray">
        {line}
      </Text>
    );
  }

  // List items
  const listMatch = line.match(/^(\s*)([-*+]|\d+\.)\s+(.+)$/);
  if (listMatch) {
    const indent = listMatch[1];
    const marker = listMatch[2];
    const text = listMatch[3];
    return (
      <Text key={Math.random()} dimColor={dimColor}>
        {indent}
        <Text color="yellow">{marker}</Text>
        {' '}
        <RenderInline text={text} />
      </Text>
    );
  }

  // Regular text with inline markdown
  return (
    <Text key={Math.random()} dimColor={dimColor}>
      <RenderInline text={line} />
    </Text>
  );
}

/**
 * MarkdownText - Renders markdown with terminal styling
 * Custom implementation compatible with Ink v5
 */
export const MarkdownText: React.FC<MarkdownTextProps> = ({ content, dimColor = false }) => {
  const { stdout } = useStdout();
  const terminalWidth = stdout?.columns || 80;
  
  logger.debug('MarkdownText: Rendering with custom markdown parser', {
    component: 'MarkdownText',
    contentLength: content.length,
    linesCount: content.split('\n').length
  });

  // Check if content contains markdown syntax
  const hasMarkdown = /[#*`\[\]_~]/.test(content);
  
  if (!hasMarkdown) {
    logger.debug('MarkdownText: No markdown syntax detected, rendering as plain text', {
      component: 'MarkdownText'
    });
  }

  // Normalize: collapse consecutive blank lines into a single blank line (outside code blocks)
  // This prevents double-spacing between paragraphs when LLM returns \n\n\n or more
  const normalizedContent = content.replace(/\n{3,}/g, '\n\n');
  
  const lines = normalizedContent.split('\n');
  let inCodeBlock = false;
  const codeBlockLines: string[] = [];
  let codeBlockLang: string | null = null;
  const elements: React.ReactNode[] = [];
  let currentKey = 0;
  let prevLineWasEmpty = false;
  
  // Table state
  let inTable = false;
  let tableHeaders: string[] = [];
  let tableRows: string[][] = [];
  const tableRowRegex = /^\s*\|(.+)\|\s*$/;
  const tableSeparatorRegex = /^\s*\|?\s*(:?-+:?)\s*(\|\s*(:?-+:?)\s*)+\|?\s*$/;

  lines.forEach((line, idx) => {
    // Track code blocks
    if (line.trim().startsWith('```')) {
      prevLineWasEmpty = false;
      if (inCodeBlock) {
        // End of code block - render accumulated lines
        if (codeBlockLines.length > 0) {
          const colorizedCode = colorizeCode({
            code: codeBlockLines.join('\n'),
            language: codeBlockLang,
            // Let parent Box control width; 0 + constrainWidth=false means "no fixed width".
            maxWidth: 0,
            hideLineNumbers: true,
            constrainWidth: false,
          });
          elements.push(
            <React.Fragment key={`codeblock_${currentKey++}`}>
              {colorizedCode}
            </React.Fragment>
          );
          codeBlockLines.length = 0;
          codeBlockLang = null;
        }
      } else {
        const fence = line.trim();
        const langMatch = fence.match(/^```(\w+)?/);
        codeBlockLang = langMatch && langMatch[1] ? langMatch[1] : null;
      }
      inCodeBlock = !inCodeBlock;
      return;
    }

    // Accumulate code block lines
    if (inCodeBlock) {
      codeBlockLines.push(line);
      return;
    }

    // Check for table rows
    const tableRowMatch = line.match(tableRowRegex);
    const tableSeparatorMatch = line.match(tableSeparatorRegex);

    if (tableRowMatch || tableSeparatorMatch) {
      if (!inTable) {
        // Start of table - first row is header
        inTable = true;
        if (tableRowMatch) {
          tableHeaders = tableRowMatch[1].split('|').map(cell => cell.trim());
        }
      } else if (tableSeparatorMatch) {
        // Separator line - skip it
        return;
      } else if (tableRowMatch) {
        // Data row
        const cells = tableRowMatch[1].split('|').map(cell => cell.trim());
        tableRows.push(cells);
      }
      return;
    }

    // If we were in a table and hit a non-table line, render the table
    if (inTable) {
      if (tableHeaders.length > 0 && tableRows.length > 0) {
        elements.push(
          <TableRenderer
            key={`table_${currentKey++}`}
            headers={tableHeaders}
            rows={tableRows}
            terminalWidth={terminalWidth}
          />
        );
      }
      inTable = false;
      tableHeaders = [];
      tableRows = [];
    }

    // Empty line: render as an empty Box with height={0.5} for paragraph spacing.
    // Previously used <Text>{' '}</Text> which caused double spacing.
    if (line.trim() === '') {
      elements.push(
        <Box key={`empty_${currentKey++}`} height={0.5} />
      );
      return;
    }

    // Render regular markdown line
    elements.push(
      <Box key={`line_${currentKey++}`}>
        {renderMarkdownLine(line, dimColor)}
      </Box>
    );
  });

  // Handle unclosed code block
  if (codeBlockLines.length > 0) {
    const colorizedCode = colorizeCode({
      code: codeBlockLines.join('\n'),
      language: codeBlockLang,
      maxWidth: 0,
      hideLineNumbers: true,
      constrainWidth: false,
    });
    elements.push(
      <React.Fragment key={`codeblock_${currentKey++}`}>
        {colorizedCode}
      </React.Fragment>
    );
  }

  // Handle table at end of content
  if (inTable && tableHeaders.length > 0 && tableRows.length > 0) {
    elements.push(
      <TableRenderer
        key={`table_${currentKey++}`}
        headers={tableHeaders}
        rows={tableRows}
        terminalWidth={terminalWidth}
      />
    );
  }

  return (
    <Box flexDirection="column">
      {elements}
    </Box>
  );
};
