/**
 * Table Renderer
 * Renders markdown tables with proper alignment and formatting.
 *
 * Layout algorithm (inspired by claude-code's MarkdownTable):
 *   1. Compute two width metrics per column:
 *        - idealWidth: full content width (no wrapping required)
 *        - minWidth:   longest single word width (smallest width that
 *                      still avoids breaking words)
 *   2. Three-tier sizing strategy:
 *        a. If sum(idealWidth) fits the terminal -> use ideal widths,
 *           no wrapping happens (matches the user's first example).
 *        b. Else if sum(minWidth) fits -> give every column its min,
 *           then distribute the leftover space proportionally to each
 *           column's overflow (idealWidth - minWidth). This produces
 *           the natural "wrap only the long column" look.
 *        c. Else -> shrink columns proportionally and hard-break words.
 *   3. Cell wrapping is word-aware (splits on whitespace) and falls
 *      back to character-wise breaking for words that are longer than
 *      the column width or for CJK runs without whitespace.
 */

import React from 'react';
import { Text, Box } from '@jrichman/ink';
import { theme } from './theme.js';
import { getPlainTextLength } from './InlineMarkdownRenderer.js';
import { colors } from '../../utils/colors.js';

interface TableRendererProps {
  headers: string[];
  rows: string[][];
  terminalWidth: number;
}

/**
 * Safety margin to prevent terminal wrapping / flicker loop on resize.
 */
const SAFETY_MARGIN = 4;
/** Minimum width allotted to any column (excluding cell padding). */
const MIN_COLUMN_WIDTH = 3;

/**
 * Strip simple inline markdown markers so width calculations match
 * the visible plain text.
 */
function stripInlineMarkdown(text: string): string {
  return (text || '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/_(.*?)_/g, '$1')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .replace(/<u>(.*?)<\/u>/g, '$1')
    .replace(/.*\[(.*?)\]\(.*\)/g, '$1');
}

/**
 * Word-aware wrap that returns lines fitting within `width` visual
 * columns. Long words (or CJK runs without spaces) are broken
 * character-by-character so we never overflow.
 */
function wrapCellText(text: string, width: number): string[] {
  if (width <= 0) return [text];
  if (!text) return [''];

  // Split keeping whitespace so we can preserve word boundaries.
  const tokens = text.split(/(\s+)/).filter((t) => t.length > 0);

  const lines: string[] = [];
  let line = '';
  let lineWidth = 0;

  const pushLine = () => {
    // Drop pure-whitespace lines that would otherwise appear at wrap points.
    if (line.length > 0) {
      lines.push(line.replace(/\s+$/, ''));
    }
    line = '';
    lineWidth = 0;
  };

  const appendChunk = (chunk: string) => {
    line += chunk;
    lineWidth += getPlainTextLength(chunk);
  };

  for (const token of tokens) {
    const tokenWidth = getPlainTextLength(token);
    const isWhitespace = /^\s+$/.test(token);

    if (lineWidth + tokenWidth <= width) {
      appendChunk(token);
      continue;
    }

    // Doesn't fit on the current line.
    if (isWhitespace) {
      // A line break naturally "consumes" the whitespace.
      pushLine();
      continue;
    }

    if (tokenWidth <= width) {
      // The whole word fits on a fresh line.
      pushLine();
      appendChunk(token);
      continue;
    }

    // Word is wider than the column -> hard-break it character by
    // character. This also handles CJK runs which lack whitespace.
    for (const ch of token) {
      const cw = getPlainTextLength(ch);
      if (lineWidth + cw > width) {
        pushLine();
      }
      appendChunk(ch);
    }
  }

  pushLine();
  return lines.length > 0 ? lines : [''];
}

/**
 * Returns the width of the longest "word" (whitespace-delimited token)
 * in the cell. For CJK content without spaces, this falls back to
 * MIN_COLUMN_WIDTH so that we still allow narrow rendering.
 */
function getMinWidth(text: string): number {
  const stripped = stripInlineMarkdown(text);
  const words = stripped.split(/\s+/).filter((w) => w.length > 0);
  if (words.length === 0) return MIN_COLUMN_WIDTH;

  let max = MIN_COLUMN_WIDTH;
  for (const w of words) {
    const wWidth = getPlainTextLength(w);
    // For very long CJK runs, avoid forcing the column wider than a
    // few characters: the wrapping algorithm will break them anyway.
    const effective = /^\s*$/.test(w)
      ? MIN_COLUMN_WIDTH
      : containsWideRun(w)
        ? Math.min(wWidth, MIN_COLUMN_WIDTH * 2)
        : wWidth;
    if (effective > max) max = effective;
  }
  return Math.max(max, MIN_COLUMN_WIDTH);
}

/** Detect strings that look like CJK (no ASCII letters/digits). */
function containsWideRun(s: string): boolean {
  return !/[A-Za-z0-9]/.test(s);
}

function getIdealWidth(text: string): number {
  return Math.max(
    getPlainTextLength(stripInlineMarkdown(text)),
    MIN_COLUMN_WIDTH,
  );
}

/**
 * Custom table renderer for markdown tables.
 */
export const TableRenderer: React.FC<TableRendererProps> = ({
  headers,
  rows,
  terminalWidth,
}) => {
  const numCols = headers.length;

  // Step 1: per-column min and ideal widths.
  const minWidths = headers.map((header, colIdx) => {
    let w = getMinWidth(header);
    for (const row of rows) {
      w = Math.max(w, getMinWidth(row[colIdx] || ''));
    }
    return w;
  });
  const idealWidths = headers.map((header, colIdx) => {
    let w = getIdealWidth(header);
    for (const row of rows) {
      w = Math.max(w, getIdealWidth(row[colIdx] || ''));
    }
    return w;
  });

  // Step 2: available content width.
  // Border overhead: │ col │ col │ -> 1 leading border + (2 padding + 1 border) per column.
  const borderOverhead = 1 + numCols * 3;
  const availableWidth = Math.max(
    terminalWidth - borderOverhead - SAFETY_MARGIN,
    numCols * MIN_COLUMN_WIDTH,
  );

  // Step 3: pick column widths using the three-tier strategy.
  const totalMin = minWidths.reduce((s, w) => s + w, 0);
  const totalIdeal = idealWidths.reduce((s, w) => s + w, 0);

  let columnContentWidths: number[];
  if (totalIdeal <= availableWidth) {
    // Everything fits: use ideal widths -> no wrapping.
    columnContentWidths = idealWidths.slice();
  } else if (totalMin <= availableWidth) {
    // Need to wrap: start at min, distribute the remainder
    // proportionally to each column's overflow (ideal - min).
    const extra = availableWidth - totalMin;
    const overflows = idealWidths.map((ideal, i) => Math.max(0, ideal - minWidths[i]!));
    const totalOverflow = overflows.reduce((s, o) => s + o, 0);
    columnContentWidths = minWidths.map((min, i) => {
      if (totalOverflow === 0) return min;
      const add = Math.floor((overflows[i]! / totalOverflow) * extra);
      return min + add;
    });
    // Distribute any leftover (rounding) to the column with the largest
    // overflow so we use the full available width.
    let used = columnContentWidths.reduce((s, w) => s + w, 0);
    let leftover = availableWidth - used;
    if (leftover > 0) {
      const order = overflows
        .map((o, i) => ({ o, i }))
        .sort((a, b) => b.o - a.o);
      let k = 0;
      while (leftover > 0 && order.length > 0) {
        columnContentWidths[order[k % order.length]!.i]! += 1;
        leftover -= 1;
        k += 1;
      }
    }
  } else {
    // Even the longest words don't fit: scale down min widths
    // proportionally and accept hard word-breaks.
    const scale = availableWidth / totalMin;
    columnContentWidths = minWidths.map((w) =>
      Math.max(Math.floor(w * scale), MIN_COLUMN_WIDTH),
    );
  }

  // adjustedWidths includes the 1-char padding on each side.
  const adjustedWidths = columnContentWidths.map((w) => w + 2);

  /**
   * Pad a single (already-wrapped) cell-line string to the column's
   * inner content width using spaces. We work on plain strings here so
   * Ink can never re-layout fragments mid-row.
   */
  const padCellLine = (text: string, contentWidth: number): string => {
    const visual = getPlainTextLength(text);
    const need = Math.max(0, contentWidth - visual);
    return text + ' '.repeat(need);
  };

  /** Build a horizontal border line as a single string. */
  const buildBorder = (type: 'top' | 'middle' | 'bottom'): string => {
    const chars = {
      top: { left: '┌', middle: '┬', right: '┐', horizontal: '─' },
      middle: { left: '├', middle: '┼', right: '┤', horizontal: '─' },
      bottom: { left: '└', middle: '┴', right: '┘', horizontal: '─' },
    };
    const c = chars[type];
    const parts = adjustedWidths.map((w) => c.horizontal.repeat(w));
    return c.left + parts.join(c.middle) + c.right;
  };

  /**
   * Build all the visual lines for a single logical row. Each cell is
   * wrapped independently and then padded to its column width; cells
   * with fewer lines are padded with spaces so column borders stay
   * aligned.
   */
  const buildRowLines = (cells: string[]): string[] => {
    const cellLines = cells.map((cell, index) => {
      const contentWidth = Math.max(0, (adjustedWidths[index] || 0) - 2);
      const plainContent = stripInlineMarkdown(cell || '');
      return wrapCellText(plainContent, contentWidth);
    });

    const maxLines = Math.max(...cellLines.map((ls) => ls.length), 1);
    const out: string[] = [];

    for (let lineIdx = 0; lineIdx < maxLines; lineIdx++) {
      let line = '│';
      for (let i = 0; i < cells.length; i++) {
        const contentWidth = Math.max(0, (adjustedWidths[i] || 0) - 2);
        const text = cellLines[i]?.[lineIdx] ?? '';
        line += ' ' + padCellLine(text, contentWidth) + ' │';
      }
      out.push(line);
    }
    return out;
  };

  // Pre-build every line of the table as a plain string. Rendering
  // each line in its own <Text> (no nested children) prevents Ink's
  // flex layout from breaking row alignment when a cell wraps.
  const borderColor = colors.gray[500];
  const textColor = theme.text.primary;
  const headerColor = theme.text.link;

  const lineNodes: React.ReactNode[] = [];
  let key = 0;

  lineNodes.push(
    <Text key={key++} color={borderColor}>
      {buildBorder('top')}
    </Text>,
  );

  for (const headerLine of buildRowLines(headers)) {
    lineNodes.push(
      <Text key={key++} bold color={headerColor}>
        {headerLine}
      </Text>,
    );
  }

  lineNodes.push(
    <Text key={key++} color={borderColor}>
      {buildBorder('middle')}
    </Text>,
  );

  for (let rowIdx = 0; rowIdx < rows.length; rowIdx++) {
    for (const dataLine of buildRowLines(rows[rowIdx]!)) {
      lineNodes.push(
        <Text key={key++} color={textColor}>
          {dataLine}
        </Text>,
      );
    }
    // Insert a ├─┼─┤ separator between data rows (not after the last one).
    if (rowIdx < rows.length - 1) {
      lineNodes.push(
        <Text key={key++} color={borderColor}>
          {buildBorder('middle')}
        </Text>,
      );
    }
  }

  lineNodes.push(
    <Text key={key++} color={borderColor}>
      {buildBorder('bottom')}
    </Text>,
  );

  return (
    <Box flexDirection="column" marginBottom={1}>
      {lineNodes}
    </Box>
  );
};
