/**
 * Markdown Display Component
 * Main component for rendering markdown with full support for:
 * - Headers, lists, code blocks, tables, horizontal rules
 * - Inline elements (bold, italic, code, links, etc.)
 * - Syntax highlighting for code blocks
 */

import React from 'react';
import { Text, Box } from '@jrichman/ink';
import { theme } from './theme.js';
import { colorizeCode } from './CodeColorizer.js';
import { TableRenderer } from './TableRenderer.js';
import { RenderInline } from './InlineMarkdownRenderer.js';
import { MAX_MARKDOWN_LENGTH, MAX_LINES_TO_RENDER } from '../../constants/limits.js';

interface MarkdownDisplayProps {
  text: string;
  isPending: boolean;
  availableTerminalHeight?: number;
  terminalWidth: number;
  renderMarkdown?: boolean;
}

// Constants for Markdown parsing and rendering
const EMPTY_LINE_HEIGHT = 1;
const CODE_BLOCK_PREFIX_PADDING = 1;
const LIST_ITEM_PREFIX_PADDING = 1;
const LIST_ITEM_TEXT_FLEX_GROW = 1;

const MarkdownDisplayInternal: React.FC<MarkdownDisplayProps> = ({
  text,
  isPending,
  availableTerminalHeight,
  terminalWidth,
  renderMarkdown = true,
}) => {
  const responseColor = theme.text.response ?? theme.text.primary;
  
  // Ensure terminal width is valid
  const safeTerminalWidth = Math.max(40, terminalWidth || 80);

  if (!text) return <></>;

  // Truncate text if too long to prevent memory issues
  let safeText = text;
  let isTruncated = false;
  
  if (text.length > MAX_MARKDOWN_LENGTH) {
    safeText = text.substring(0, MAX_MARKDOWN_LENGTH);
    isTruncated = true;
  }

  // Raw markdown mode - display syntax-highlighted markdown without rendering
  if (!renderMarkdown) {
    const colorizedMarkdown = colorizeCode({
      code: safeText,
      language: 'markdown',
      availableHeight: availableTerminalHeight,
      maxWidth: safeTerminalWidth - CODE_BLOCK_PREFIX_PADDING,
      hideLineNumbers: true,
    });
    return (
      <Box paddingLeft={CODE_BLOCK_PREFIX_PADDING} flexDirection="column">
        {colorizedMarkdown}
        {isTruncated && (
          <Text color={theme.text.secondary}>
            ... [content too long, truncated. {text.length - MAX_MARKDOWN_LENGTH} chars hidden]
          </Text>
        )}
      </Box>
    );
  }

  let allLines = safeText.split(/\r?\n/);
  
  // Preprocess: split inline list items into separate lines
  // This handles cases like "text - item1 - item2 - item3" -> separate lines
  const processedLines: string[] = [];
  for (const line of allLines) {
    // Check if line contains inline list items (multiple " - " in one line)
    // Pattern: text followed by multiple " - item" patterns
    const inlineListMatch = line.match(/^(.+?)(\s+-\s+.+)$/);
    if (inlineListMatch) {
      const prefix = inlineListMatch[1].trim();
      const listPart = inlineListMatch[2];
      
      // Split by " - " but keep the marker
      const items = listPart.split(/\s+-\s+/).filter(item => item.trim());
      
      // Add prefix line if it doesn't end with ":"
      if (prefix && !prefix.endsWith(':')) {
        processedLines.push(prefix);
      } else if (prefix) {
        processedLines.push(prefix);
      }
      
      // Add each list item as a separate line
      items.forEach(item => {
        if (item.trim()) {
          processedLines.push(`- ${item.trim()}`);
        }
      });
    } else {
      processedLines.push(line);
    }
  }
  
  allLines = processedLines;
  
  // Limit number of lines to render
  const lines = allLines.length > MAX_LINES_TO_RENDER 
    ? allLines.slice(0, MAX_LINES_TO_RENDER)
    : allLines;
  
  const linesSkipped = allLines.length - lines.length;
  const headerRegex = /^ *(#{1,4}) +(.*)/;
  const codeFenceRegex = /^ *(`{3,}|~{3,}) *(\w*?) *$/;
  const ulItemRegex = /^([ \t]*)([-*+]) +(.*)/;
  const olItemRegex = /^([ \t]*)(\d+)\. +(.*)/;
  const hrRegex = /^ *([-*_] *){3,} *$/;
  const tableRowRegex = /^\s*\|(.+)\|\s*$/;
  const tableSeparatorRegex = /^\s*\|?\s*(:?-+:?)\s*(\|\s*(:?-+:?)\s*)+\|?\s*$/;

  const contentBlocks: React.ReactNode[] = [];
  let inCodeBlock = false;
  let lastLineEmpty = true;
  let codeBlockContent: string[] = [];
  let codeBlockLang: string | null = null;
  let codeBlockFence = '';
  let inTable = false;
  let tableRows: string[][] = [];
  let tableHeaders: string[] = [];

  function addContentBlock(block: React.ReactNode) {
    if (block) {
      contentBlocks.push(block);
      lastLineEmpty = false;
    }
  }

  lines.forEach((line, index) => {
    const key = `line-${index}`;

    if (inCodeBlock) {
      const fenceMatch = line.match(codeFenceRegex);
      if (
        fenceMatch &&
        fenceMatch[1].startsWith(codeBlockFence[0]) &&
        fenceMatch[1].length >= codeBlockFence.length
      ) {
        addContentBlock(
          <RenderCodeBlock
            key={key}
            content={codeBlockContent}
            lang={codeBlockLang}
            isPending={isPending}
            availableTerminalHeight={availableTerminalHeight}
            terminalWidth={safeTerminalWidth}
          />,
        );
        inCodeBlock = false;
        codeBlockContent = [];
        codeBlockLang = null;
        codeBlockFence = '';
      } else {
        codeBlockContent.push(line);
      }
      return;
    }

    const codeFenceMatch = line.match(codeFenceRegex);
    const headerMatch = line.match(headerRegex);
    const ulMatch = line.match(ulItemRegex);
    const olMatch = line.match(olItemRegex);
    const hrMatch = line.match(hrRegex);
    const tableRowMatch = line.match(tableRowRegex);
    const tableSeparatorMatch = line.match(tableSeparatorRegex);

    if (codeFenceMatch) {
      inCodeBlock = true;
      codeBlockFence = codeFenceMatch[1];
      codeBlockLang = codeFenceMatch[2] || null;
    } else if (tableRowMatch && !inTable) {
      // Potential table start - check if next line is separator
      if (
        index + 1 < lines.length &&
        lines[index + 1].match(tableSeparatorRegex)
      ) {
        inTable = true;
        tableHeaders = tableRowMatch[1].split('|').map((cell) => cell.trim());
        tableRows = [];
      } else {
        // Not a table, treat as regular text
        addContentBlock(
          <Box key={key}>
            <Text wrap="wrap" color={responseColor}>
              <RenderInline text={line} defaultColor={responseColor} />
            </Text>
          </Box>,
        );
      }
    } else if (inTable && tableSeparatorMatch) {
      // Skip separator line - already handled
    } else if (inTable && tableRowMatch) {
      // Add table row
      const cells = tableRowMatch[1].split('|').map((cell) => cell.trim());
      // Ensure row has same column count as headers
      while (cells.length < tableHeaders.length) {
        cells.push('');
      }
      if (cells.length > tableHeaders.length) {
        cells.length = tableHeaders.length;
      }
      tableRows.push(cells);
    } else if (inTable && !tableRowMatch) {
      // End of table
      if (tableHeaders.length > 0 && tableRows.length > 0) {
        addContentBlock(
          <RenderTable
            key={`table-${contentBlocks.length}`}
            headers={tableHeaders}
            rows={tableRows}
            terminalWidth={safeTerminalWidth}
          />,
        );
      }
      inTable = false;
      tableRows = [];
      tableHeaders = [];

      // Process current line as normal
      if (line.trim().length > 0) {
        addContentBlock(
          <Box key={key}>
            <Text wrap="wrap" color={responseColor}>
              <RenderInline text={line} defaultColor={responseColor} />
            </Text>
          </Box>,
        );
      }
    } else if (hrMatch) {
      addContentBlock(
        <Box key={key}>
          <Text dimColor>───────────────────────────────────────</Text>
        </Box>,
      );
    } else if (headerMatch) {
      const level = headerMatch[1].length;
      const headerText = headerMatch[2];
      let headerNode: React.ReactNode = null;
      switch (level) {
        case 1:
          headerNode = (
            <Text bold color={theme.text.link}>
              <RenderInline text={headerText} defaultColor={theme.text.link} />
            </Text>
          );
          break;
        case 2:
          headerNode = (
            <Text bold color={theme.text.link}>
              <RenderInline text={headerText} defaultColor={theme.text.link} />
            </Text>
          );
          break;
        case 3:
          headerNode = (
            <Text bold color={responseColor}>
              <RenderInline text={headerText} defaultColor={responseColor} />
            </Text>
          );
          break;
        case 4:
          headerNode = (
            <Text italic color={theme.text.secondary}>
              <RenderInline
                text={headerText}
                defaultColor={theme.text.secondary}
              />
            </Text>
          );
          break;
        default:
          headerNode = (
            <Text color={responseColor}>
              <RenderInline text={headerText} defaultColor={responseColor} />
            </Text>
          );
          break;
      }
      if (headerNode) addContentBlock(<Box key={key}>{headerNode}</Box>);
    } else if (ulMatch) {
      const leadingWhitespace = ulMatch[1];
      const marker = ulMatch[2];
      const itemText = ulMatch[3];
      addContentBlock(
        <RenderListItem
          key={key}
          itemText={itemText}
          type="ul"
          marker={marker}
          leadingWhitespace={leadingWhitespace}
        />,
      );
    } else if (olMatch) {
      const leadingWhitespace = olMatch[1];
      const marker = olMatch[2];
      const itemText = olMatch[3];
      addContentBlock(
        <RenderListItem
          key={key}
          itemText={itemText}
          type="ol"
          marker={marker}
          leadingWhitespace={leadingWhitespace}
        />,
      );
    } else {
      if (line.trim().length === 0 && !inCodeBlock) {
        // Always render empty lines for paragraph spacing
        contentBlocks.push(
          <Box key={`spacer-${index}`} height={EMPTY_LINE_HEIGHT} />,
        );
        lastLineEmpty = true;
      } else {
        addContentBlock(
          <Box key={key} flexDirection="column">
            <Text color={responseColor} wrap="wrap">
              <RenderInline text={line} defaultColor={responseColor} />
            </Text>
          </Box>,
        );
      }
    }
  });

  if (inCodeBlock) {
    addContentBlock(
      <RenderCodeBlock
        key="line-eof"
        content={codeBlockContent}
        lang={codeBlockLang}
        isPending={isPending}
        availableTerminalHeight={availableTerminalHeight}
        terminalWidth={safeTerminalWidth}
      />,
    );
  }

  // Handle table at end of content
  if (inTable && tableHeaders.length > 0 && tableRows.length > 0) {
    addContentBlock(
      <RenderTable
        key={`table-${contentBlocks.length}`}
        headers={tableHeaders}
        rows={tableRows}
        terminalWidth={safeTerminalWidth}
      />,
    );
  }

  // Add truncation warning if content was truncated
  if (isTruncated || linesSkipped > 0) {
    contentBlocks.push(
      <Box key="truncation-warning" marginTop={1}>
        <Text color={theme.text.secondary}>
          {isTruncated && `... [content too long, truncated. ${text.length - MAX_MARKDOWN_LENGTH} chars hidden]`}
          {linesSkipped > 0 && !isTruncated && `... [${linesSkipped} lines omitted]`}
        </Text>
      </Box>
    );
  }

  return <>{contentBlocks}</>;
};

// Helper components

interface RenderCodeBlockProps {
  content: string[];
  lang: string | null;
  isPending: boolean;
  availableTerminalHeight?: number;
  terminalWidth: number;
}

const RenderCodeBlockInternal: React.FC<RenderCodeBlockProps> = ({
  content,
  lang,
  isPending,
  availableTerminalHeight,
  terminalWidth,
}) => {
  const MIN_LINES_FOR_MESSAGE = 1;
  const RESERVED_LINES = 2;

  // Handle pending state with truncation
  if (
    isPending &&
    availableTerminalHeight !== undefined
  ) {
    const MAX_CODE_LINES_WHEN_PENDING = Math.max(
      0,
      availableTerminalHeight - RESERVED_LINES,
    );

    if (content.length > MAX_CODE_LINES_WHEN_PENDING) {
      if (MAX_CODE_LINES_WHEN_PENDING < MIN_LINES_FOR_MESSAGE) {
        return (
          <Box paddingLeft={CODE_BLOCK_PREFIX_PADDING}>
            <Text color={theme.text.secondary}>
              ... code is being written ...
            </Text>
          </Box>
        );
      }
      const truncatedContent = content.slice(0, MAX_CODE_LINES_WHEN_PENDING);
      const colorizedTruncatedCode = colorizeCode({
        code: truncatedContent.join('\n'),
        language: lang,
        availableHeight: availableTerminalHeight,
        maxWidth: terminalWidth - CODE_BLOCK_PREFIX_PADDING,
      });
      return (
        <Box paddingLeft={CODE_BLOCK_PREFIX_PADDING} flexDirection="column">
          {colorizedTruncatedCode}
          <Text color={theme.text.secondary}>... generating more ...</Text>
        </Box>
      );
    }
  }

  const fullContent = content.join('\n');
  const colorizedCode = colorizeCode({
    code: fullContent,
    language: lang,
    availableHeight: availableTerminalHeight,
    maxWidth: terminalWidth - CODE_BLOCK_PREFIX_PADDING,
  });

  return (
    <Box
      paddingLeft={CODE_BLOCK_PREFIX_PADDING}
      flexDirection="column"
      flexShrink={0}
    >
      {colorizedCode}
    </Box>
  );
};

const RenderCodeBlock = React.memo(RenderCodeBlockInternal);

interface RenderListItemProps {
  itemText: string;
  type: 'ul' | 'ol';
  marker: string;
  leadingWhitespace?: string;
}

const RenderListItemInternal: React.FC<RenderListItemProps> = ({
  itemText,
  type,
  marker,
  leadingWhitespace = '',
}) => {
  const prefix = type === 'ol' ? `${marker}. ` : `${marker} `;
  const prefixWidth = prefix.length;
  const indentation = leadingWhitespace.length;
  const listResponseColor = theme.text.response ?? theme.text.primary;

  return (
    <Box
      paddingLeft={indentation + LIST_ITEM_PREFIX_PADDING}
      flexDirection="row"
    >
      <Box width={prefixWidth}>
        <Text color={listResponseColor}>{prefix}</Text>
      </Box>
      <Box flexGrow={LIST_ITEM_TEXT_FLEX_GROW}>
        <Text color={listResponseColor} wrap="wrap">
          <RenderInline text={itemText} defaultColor={listResponseColor} />
        </Text>
      </Box>
    </Box>
  );
};

const RenderListItem = React.memo(RenderListItemInternal);

interface RenderTableProps {
  headers: string[];
  rows: string[][];
  terminalWidth: number;
}

const RenderTableInternal: React.FC<RenderTableProps> = ({
  headers,
  rows,
  terminalWidth,
}) => (
  <TableRenderer headers={headers} rows={rows} terminalWidth={terminalWidth} />
);

const RenderTable = React.memo(RenderTableInternal);

export const MarkdownDisplay = React.memo(MarkdownDisplayInternal);
