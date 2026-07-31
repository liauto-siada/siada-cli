import { diffWordsWithSpace, type StructuredPatchHunk } from 'diff';
import * as React from 'react';
import { Box, Text } from '@jrichman/ink';
import path from 'node:path';

// Colors for diff display
const COLORS = {
  added: '#1a4a1a',
  removed: '#4a1a1a',
  addedWord: '#2d7a2d',
  removedWord: '#7a2d2d',
  lineNum: '#666666',
  filePath: '#8888cc',
};

interface DiffLine {
  code: string;
  type: 'add' | 'remove' | 'nochange';
  lineNum: number;
  originalCode: string;
  wordDiff?: boolean;
  matchedLine?: DiffLine;
}

interface DiffPart {
  added?: boolean;
  removed?: boolean;
  value: string;
}

const CHANGE_THRESHOLD = 0.4;

function transformLines(lines: string[]): DiffLine[] {
  return lines.map(raw => {
    const code = raw.slice(1);
    if (raw.startsWith('+')) return { code, type: 'add', lineNum: 0, originalCode: code };
    if (raw.startsWith('-')) return { code, type: 'remove', lineNum: 0, originalCode: code };
    return { code, type: 'nochange', lineNum: 0, originalCode: code };
  });
}

function pairAdjacentLines(lines: DiffLine[]): DiffLine[] {
  const result: DiffLine[] = [];
  let i = 0;
  while (i < lines.length) {
    const cur = lines[i];
    if (!cur) { i++; continue; }
    if (cur.type === 'remove') {
      const removes: DiffLine[] = [cur];
      let j = i + 1;
      while (j < lines.length && lines[j]?.type === 'remove') {
        removes.push(lines[j]!);
        j++;
      }
      const adds: DiffLine[] = [];
      while (j < lines.length && lines[j]?.type === 'add') {
        adds.push(lines[j]!);
        j++;
      }
      if (removes.length > 0 && adds.length > 0) {
        const pairCount = Math.min(removes.length, adds.length);
        for (let k = 0; k < pairCount; k++) {
          const r = removes[k]!;
          const a = adds[k]!;
          r.wordDiff = true;
          a.wordDiff = true;
          r.matchedLine = a;
          a.matchedLine = r;
        }
        result.push(...removes);
        result.push(...adds);
        i = j;
      } else {
        result.push(cur);
        i++;
      }
    } else {
      result.push(cur);
      i++;
    }
  }
  return result;
}

function numberLines(lines: DiffLine[], startLine: number): DiffLine[] {
  let n = startLine;
  const result: DiffLine[] = [];
  const queue = [...lines];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    const line = { ...cur, lineNum: n };
    if (cur.type === 'remove') {
      result.push(line);
      let numRemoved = 0;
      while (queue[0]?.type === 'remove') {
        n++;
        result.push({ ...queue.shift()!, lineNum: n });
        numRemoved++;
      }
      n -= numRemoved;
    } else {
      n++;
      result.push(line);
    }
  }
  return result;
}

// Simple character-level wrap (no dependency on ink's wrapText)
function wrapCode(code: string, maxWidth: number): string[] {
  if (maxWidth <= 0) return [code];
  if (code.length <= maxWidth) return [code];
  const result: string[] = [];
  for (let i = 0; i < code.length; i += maxWidth) {
    result.push(code.slice(i, i + maxWidth));
  }
  return result;
}

type RenderedLine = {
  lineNumStr: string;
  sigil: string;
  bgColor: string | undefined;
  content: React.ReactNode;
  padding: number;
};

function renderStandardLine(
  item: DiffLine,
  maxWidth: number,
  totalWidth: number,
  lineIndex: number,
): RenderedLine {
  const { type, code, lineNum } = item;
  const gutterWidth = maxWidth + 1; // linenum + space
  const diffPrefixWidth = 1;
  const availWidth = Math.max(1, totalWidth - gutterWidth - diffPrefixWidth);
  const wrappedLines = wrapCode(code, availWidth);
  const line = wrappedLines[lineIndex] ?? '';

  const lineNumStr =
    lineIndex === 0
      ? lineNum.toString().padStart(maxWidth) + ' '
      : ' '.repeat(maxWidth) + ' ';
  const sigil = type === 'add' ? '+' : type === 'remove' ? '-' : ' ';
  const contentWidth = lineNumStr.length + 1 + line.length;
  const padding = Math.max(0, totalWidth - contentWidth);
  const bgColor =
    type === 'add' ? COLORS.added : type === 'remove' ? COLORS.removed : undefined;

  return { lineNumStr, sigil, bgColor, content: line, padding };
}

function renderWordDiffLine(
  item: DiffLine,
  maxWidth: number,
  totalWidth: number,
): React.ReactNode[] | null {
  const { type, lineNum, wordDiff, matchedLine, originalCode } = item;
  if (!wordDiff || !matchedLine) return null;

  const removedText = type === 'remove' ? originalCode : matchedLine.originalCode;
  const addedText = type === 'remove' ? matchedLine.originalCode : originalCode;
  const parts: DiffPart[] = diffWordsWithSpace(removedText, addedText, { ignoreCase: false });

  const totalLen = removedText.length + addedText.length;
  const changedLen = parts
    .filter(p => p.added || p.removed)
    .reduce((s, p) => s + p.value.length, 0);
  if (totalLen > 0 && changedLen / totalLen > CHANGE_THRESHOLD) return null;

  const gutterWidth = maxWidth + 1;
  const diffPrefixWidth = 1;
  const availWidth = Math.max(1, totalWidth - gutterWidth - diffPrefixWidth);
  const bgColor = type === 'add' ? COLORS.added : COLORS.removed;
  const sigil = type === 'add' ? '+' : '-';
  const lineNumStr = lineNum.toString().padStart(maxWidth) + ' ';

  // Collect visible parts for this line type
  const visibleParts: { text: string; wordHighlight: boolean }[] = [];
  for (const part of parts) {
    let show = false;
    let isWordHighlight = false;
    if (type === 'add') {
      if (part.added) { show = true; isWordHighlight = true; }
      else if (!part.removed) { show = true; }
    } else {
      if (part.removed) { show = true; isWordHighlight = true; }
      else if (!part.added) { show = true; }
    }
    if (show) visibleParts.push({ text: part.value, wordHighlight: isWordHighlight });
  }

  const fullText = visibleParts.map(p => p.text).join('');
  // Render as a single row with word-level highlights
  const contentWidth = lineNumStr.length + 1 + fullText.length;
  const padding = Math.max(0, totalWidth - contentWidth);

  const contentNodes: React.ReactNode[] = visibleParts.map((p, i) => (
    <Text
      key={i}
      backgroundColor={p.wordHighlight ? (type === 'add' ? COLORS.addedWord : COLORS.removedWord) : bgColor}
    >
      {p.text}
    </Text>
  ));
  contentNodes.push(<Text key="pad" backgroundColor={bgColor}>{' '.repeat(padding)}</Text>);

  return [
    <Box key={`${type}-${lineNum}`} flexDirection="row">
      <Text backgroundColor={bgColor} dimColor={false}>
        {lineNumStr}
        {sigil}
      </Text>
      <Text backgroundColor={bgColor}>
        {contentNodes}
      </Text>
    </Box>,
  ];
}

function renderHunk(hunk: StructuredPatchHunk, totalWidth: number): React.ReactNode[] {
  const lineObjs = transformLines(hunk.lines);
  const paired = pairAdjacentLines(lineObjs);
  const numbered = numberLines(paired, hunk.oldStart);

  const maxLineNum = Math.max(...numbered.map(l => l.lineNum), 0);
  const maxWidth = Math.max(maxLineNum.toString().length + 1, 1);

  const nodes: React.ReactNode[] = [];
  for (const item of numbered) {
    // Try word-level diff for paired add/remove lines
    if (item.wordDiff && item.matchedLine) {
      const wordNodes = renderWordDiffLine(item, maxWidth, totalWidth);
      if (wordNodes) {
        nodes.push(...wordNodes);
        continue;
      }
    }

    // Standard rendering — may produce multiple wrapped rows
    const gutterWidth = maxWidth + 1;
    const diffPrefixWidth = 1;
    const availWidth = Math.max(1, totalWidth - gutterWidth - diffPrefixWidth);
    const wrappedLines = wrapCode(item.code, availWidth);
    const lineCount = Math.max(1, wrappedLines.length);

    for (let li = 0; li < lineCount; li++) {
      const rendered = renderStandardLine(item, maxWidth, totalWidth, li);
      const { lineNumStr, sigil, bgColor, content, padding } = rendered;
      nodes.push(
        <Box key={`${item.type}-${item.lineNum}-${li}`} flexDirection="row">
          <Text backgroundColor={bgColor} dimColor={item.type === 'nochange'}>
            {lineNumStr}
            {sigil}
          </Text>
          <Text backgroundColor={bgColor} dimColor={item.type === 'nochange'}>
            {content as string}
            {' '.repeat(padding)}
          </Text>
        </Box>,
      );
    }
  }
  return nodes;
}

interface DiffViewProps {
  filePath: string;
  hunks: StructuredPatchHunk[];
  width?: number;
}

export const DiffView: React.FC<DiffViewProps> = ({ filePath, hunks, width }) => {
  const totalWidth = width ?? (process.stdout.columns || 80);
  const displayPath = path.basename(filePath);

  return (
    <Box flexDirection="column">
      {/* File path header */}
      <Text color={COLORS.filePath}>{displayPath}</Text>
      {/* Dashed top border */}
      <Text dimColor>{'─'.repeat(totalWidth)}</Text>
      {/* Hunks */}
      {hunks.map((hunk, hunkIdx) => (
        <Box key={hunkIdx} flexDirection="column">
          {hunkIdx > 0 && (
            <Text dimColor>{'...'}</Text>
          )}
          {renderHunk(hunk, totalWidth).map((node, i) => (
            <Box key={i}>{node}</Box>
          ))}
        </Box>
      ))}
      {/* Dashed bottom border */}
      <Text dimColor>{'─'.repeat(totalWidth)}</Text>
    </Box>
  );
};
