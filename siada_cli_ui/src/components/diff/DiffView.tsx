import { diffWordsWithSpace, type StructuredPatchHunk } from 'diff';
import * as React from 'react';
import { Box, Text } from '@jrichman/ink';
import path from 'node:path';
import stringWidth from 'string-width';
import { colors } from '../../utils/colors.js';
import { useThemeVersion } from '../../themes/index.js';

/**
 * Diff rows paint a tinted background band and leave the code in the
 * terminal's own foreground — the same color as every other body text — so a
 * hunk reads as the user's file rather than as decoration. Only the +/- signs
 * and the word-level highlight carry color, and each band is chosen so that
 * foreground still contrasts with it (light bands light text, dark bands
 * light-on-dark) instead of the old dark-on-dark rows.
 */
type DiffPalette = typeof colors.diff;

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
const graphemeSegmenter = new Intl.Segmenter();

function transformLines(lines: string[]): DiffLine[] {
  return lines.map(raw => {
    // Ink expands tabs to four columns when painting text. Expand them here
    // too so the wrapping and background padding use the same width.
    const code = raw.slice(1).replaceAll('\t', '    ');
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

// Ink measures terminal columns, not JS string length (CJK and emoji can
// occupy two columns). Wrap before painting the background so neither Yoga nor
// the terminal has to wrap a colored row after its padding has been computed.
function wrapCode(code: string, maxWidth: number): string[] {
  if (maxWidth <= 0) return [code];
  if (stringWidth(code) <= maxWidth) return [code];
  const result: string[] = [];
  let line = '';
  let usedWidth = 0;
  for (const { segment } of graphemeSegmenter.segment(code)) {
    const width = stringWidth(segment);
    if (usedWidth + width > maxWidth && line) {
      result.push(line);
      line = '';
      usedWidth = 0;
    }
    line += segment;
    usedWidth += width;
  }
  if (line) result.push(line);
  return result;
}

type RenderedLine = {
  lineNumStr: string;
  sigil: string;
  bgColor: string | undefined;
  signColor: string | undefined;
  codeColor: string | undefined;
  content: React.ReactNode;
  padding: number;
};

function renderStandardLine(
  item: DiffLine,
  maxWidth: number,
  totalWidth: number,
  lineIndex: number,
  line: string,
  palette: DiffPalette,
): RenderedLine {
  const { type, lineNum } = item;

  const lineNumStr =
    lineIndex === 0
      ? lineNum.toString().padStart(maxWidth) + ' '
      : ' '.repeat(maxWidth) + ' ';
  const sigil = lineIndex > 0 ? ' ' : type === 'add' ? '+' : type === 'remove' ? '-' : ' ';
  const contentWidth = stringWidth(lineNumStr) + 1 + stringWidth(line);
  const padding = Math.max(0, totalWidth - contentWidth);
  const bgColor = type === 'add' ? palette.addedBg : type === 'remove' ? palette.removedBg : undefined;
  // Unchanged context steps down one tone; the banded rows keep the terminal
  // foreground and let the band carry the emphasis.
  const codeColor = bgColor ? undefined : colors.content.secondary;
  const signColor = lineIndex > 0 ? undefined
    : type === 'add' ? palette.addedSign : type === 'remove' ? palette.removedSign : undefined;

  return { lineNumStr, sigil, bgColor, signColor, codeColor, content: line, padding };
}

function renderWordDiffLine(
  item: DiffLine,
  maxWidth: number,
  totalWidth: number,
  palette: DiffPalette,
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
  const bgColor = type === 'add' ? palette.addedBg : palette.removedBg;
  const wordBgColor = type === 'add' ? palette.addedWordBg : palette.removedWordBg;
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
  // Word-level spans are rendered in a single Ink row. Long lines must use
  // the standard wrapped renderer instead, or the colored spans overflow.
  if (stringWidth(fullText) > availWidth) return null;
  const contentWidth = stringWidth(lineNumStr) + 1 + stringWidth(fullText);
  const padding = Math.max(0, totalWidth - contentWidth);

  const contentNodes: React.ReactNode[] = visibleParts.map((p, i) => (
    <Text
      key={i}
      backgroundColor={p.wordHighlight ? wordBgColor : bgColor}
    >
      {p.text}
    </Text>
  ));
  contentNodes.push(<Text key="pad" backgroundColor={bgColor}>{' '.repeat(padding)}</Text>);

  return [
    <Box key={`${type}-${lineNum}`} flexDirection="row">
      <Text backgroundColor={bgColor} color={colors.content.tertiary}>{lineNumStr}</Text>
      <Text backgroundColor={bgColor} color={type === 'add' ? palette.addedSign : palette.removedSign} bold>{sigil}</Text>
      <Text backgroundColor={bgColor}>
        {contentNodes}
      </Text>
    </Box>,
  ];
}

function renderHunk(hunk: StructuredPatchHunk, totalWidth: number, palette: DiffPalette): React.ReactNode[] {
  const lineObjs = transformLines(hunk.lines);
  const paired = pairAdjacentLines(lineObjs);
  const numbered = numberLines(paired, hunk.oldStart);

  const maxLineNum = Math.max(...numbered.map(l => l.lineNum), 0);
  const maxWidth = Math.max(maxLineNum.toString().length + 1, 1);

  const nodes: React.ReactNode[] = [];
  for (const item of numbered) {
    // Try word-level diff for paired add/remove lines
    if (item.wordDiff && item.matchedLine) {
      const wordNodes = renderWordDiffLine(item, maxWidth, totalWidth, palette);
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
      const rendered = renderStandardLine(item, maxWidth, totalWidth, li, wrappedLines[li] ?? '', palette);
      const { lineNumStr, sigil, bgColor, signColor, codeColor, content, padding } = rendered;
      nodes.push(
        <Box key={`${item.type}-${item.lineNum}-${li}`} flexDirection="row">
          <Text backgroundColor={bgColor} color={colors.content.tertiary}>
            {lineNumStr}
          </Text>
          <Text backgroundColor={bgColor} color={signColor} bold={!!signColor}>{sigil}</Text>
          <Text backgroundColor={bgColor} color={codeColor}>
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
  showFrame?: boolean;
}

export const DiffView: React.FC<DiffViewProps> = ({ filePath, hunks, width, showFrame = true }) => {
  useThemeVersion(); // repaint on theme change (React.memo blocks prop-driven re-renders)
  const totalWidth = width ?? (process.stdout.columns || 80);
  const displayPath = path.basename(filePath);
  const palette = colors.diff;

  return (
    <Box flexDirection="column">
      {/* File path header */}
      {showFrame && <Text>{displayPath}</Text>}
      {/* Dashed top border */}
      {showFrame && <Text color={colors.content.tertiary}>{'─'.repeat(totalWidth)}</Text>}
      {/* Hunks */}
      {hunks.map((hunk, hunkIdx) => (
        <Box key={hunkIdx} flexDirection="column">
          {hunkIdx > 0 && (
            <Text color={colors.content.tertiary}>{'...'}</Text>
          )}
          {renderHunk(hunk, totalWidth, palette).map((node, i) => (
            <Box key={i}>{node}</Box>
          ))}
        </Box>
      ))}
      {/* Dashed bottom border */}
      {showFrame && <Text color={colors.content.tertiary}>{'─'.repeat(totalWidth)}</Text>}
    </Box>
  );
};
