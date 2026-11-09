import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box, Text, useStdout, type DOMElement } from '@jrichman/ink';
import { render, type MermaidArt, type Span } from 'grok-mermaid';
import stringWidth from '../../utils/terminalWidth.js';
import { theme } from './theme.js';
import { useThemeVersion } from '../../themes/index.js';
import { MAX_MARKDOWN_LENGTH, MAX_VISIBLE_LINES } from '../../constants/limits.js';
import { useKeypress } from '../../contexts/KeypressContext.js';
import { useMouseTracking } from '../../hooks/useMouseTracking.js';
import { isVisibleMermaidTarget, registerMermaidControls } from '../../utils/mermaidControls.js';

// Keep layout results independent of themes and viewport size.
const cache = new Map<string, MermaidArt | null>();
const MAX_CACHE_ENTRIES = 50;

export function renderMermaidDiagram(source: string, maxWidth: number, maxHeight = MAX_VISIBLE_LINES): MermaidArt | null {
  if (!source.trim() || source.length > MAX_MARKDOWN_LENGTH || maxWidth <= 0 || maxHeight <= 0) return null;
  let art = cache.get(source);
  if (art === undefined) {
    try {
      art = render(source);
    } catch {
      // Malformed model output must not interrupt the message renderer.
      art = null;
    }
    if (cache.size >= MAX_CACHE_ENTRIES) {
      const oldest = cache.keys().next().value;
      if (oldest !== undefined) cache.delete(oldest);
    }
    cache.set(source, art);
  }
  // Best-effort parsers can drop statements: keep the source in that case.
  if (!art || art.warnings.length ||
      art.plain.length + (art.width > maxWidth ? 1 : 0) > maxHeight) return null;
  return art;
}

const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });

/** Clip styled runs by display columns, replacing partial wide glyphs with spaces. */
export function sliceMermaidRow(row: Span[], start: number, width: number): Span[] {
  const result: Span[] = [];
  const end = start + width;
  let column = 0;
  for (const span of row) {
    let text = '';
    for (const { segment } of segmenter.segment(span.text)) {
      const cells = stringWidth(segment);
      const next = column + cells;
      if (cells === 0) {
        if (column >= start && column < end) text += segment;
      } else if (next > start && column < end) {
        text += column >= start && next <= end
          ? segment : ' '.repeat(Math.min(next, end) - Math.max(column, start));
      }
      column = next;
      if (column >= end) break;
    }
    if (text) result.push({ text, cls: span.cls });
    if (column >= end) break;
  }
  return result;
}

const MermaidControls: React.FC<{
  width: number;
  offset: number;
  totalWidth: number;
  onMove: (direction: number) => void;
}> = ({ width, offset, totalWidth, onMove }) => {
  const controlsRef = useRef<DOMElement>(null);
  const leftRef = useRef<DOMElement>(null);
  const rightRef = useRef<DOMElement>(null);
  const pressed = useRef<{ direction: number; x: number; y: number } | null>(null);
  const { stdout } = useStdout();
  const buttonWidth = Math.max(1, Math.min(3, Math.floor(width / 2)));
  useMouseTracking();
  useLayoutEffect(() => {
    if (controlsRef.current) return registerMermaidControls(stdout, controlsRef.current);
  }, [stdout]);
  useKeypress(key => {
    const match = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/.exec(key.sequence);
    if (!match || key.shift || key.alt || key.ctrl) {
      pressed.current = null;
      return;
    }
    const x = Number(match[2]) - 1, y = Number(match[3]) - 1;
    const hit = (node: DOMElement | null) => isVisibleMermaidTarget(stdout, node, { x, y });
    const direction = hit(leftRef.current) ? -1 : hit(rightRef.current) ? 1 : 0;
    if (key.name === 'mouseclick') {
      pressed.current = direction ? { direction, x, y } : null;
    } else if (key.name === 'mouserelease') {
      const down = pressed.current;
      pressed.current = null;
      if (down && down.direction === direction && down.x === x && down.y === y) onMove(direction);
    } else if (key.name === 'mousemove' && pressed.current &&
      (pressed.current.x !== x || pressed.current.y !== y)) {
      pressed.current = null;
    }
  });
  return (
    <Box ref={controlsRef} width={width} height={1} flexShrink={0} userSelect="none" overflowX="hidden">
      <Box ref={leftRef} width={buttonWidth} flexShrink={0}>
        <Text color={theme.text.secondary} dimColor={offset === 0}>{buttonWidth === 3 ? ' ◀ ' : '◀'}</Text>
      </Box>
      <Box ref={rightRef} width={buttonWidth} flexShrink={0}>
        <Text color={theme.text.secondary} dimColor={offset + width >= totalWidth}>{buttonWidth === 3 ? ' ▶ ' : '▶'}</Text>
      </Box>
      {width > 7 && <Text color={theme.text.secondary} wrap="truncate">
        {` ${offset + 1}–${Math.min(offset + width, totalWidth)} / ${totalWidth}`}
      </Text>}
    </Box>
  );
};

export const MermaidDiagram: React.FC<{ art: MermaidArt; dimColor?: boolean; availableWidth?: number }> = ({
  art, dimColor = false, availableWidth,
}) => {
  useThemeVersion();
  const { stdout } = useStdout();
  const width = Math.max(1, Math.floor(availableWidth ?? stdout.columns ?? 80));
  const totalWidth = useMemo(() => Math.max(art.width, ...art.plain.map(line => stringWidth(line))), [art]);
  const maxOffset = Math.max(0, totalWidth - width);
  const [position, setPosition] = useState(0);
  const offset = Math.min(position, maxOffset);
  useEffect(() => { setPosition(0); }, [art]);
  useEffect(() => { setPosition(current => Math.min(current, maxOffset)); }, [maxOffset]);
  const rows = useMemo(() => art.styled.map(row => sliceMermaidRow(row, offset, width)), [art, offset, width]);
  return (
    <Box width={width} height={rows.length + (maxOffset > 0 ? 1 : 0)} flexDirection="column" flexShrink={0}>
      {rows.map((row, index) => (
        <Text key={index} dimColor={dimColor} wrap="truncate">
          {row.length === 0 ? ' ' : row.map((span, spanIndex) => (
            <Text key={spanIndex}
              color={span.cls === 'border' ? theme.border.default :
                span.cls === 'edge' || span.cls === 'title' ? theme.text.accent :
                span.cls === 'edgeLabel' ? theme.text.secondary : theme.text.response}
              bold={span.cls === 'title'}>
              {span.text}
            </Text>
          ))}
        </Text>
      ))}
      {maxOffset > 0 && <MermaidControls width={width} offset={offset} totalWidth={totalWidth}
        onMove={direction => setPosition(current => Math.max(0,
          Math.min(maxOffset, current + direction * Math.max(1, width - 4))))} />}
    </Box>
  );
};