import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { render, type MermaidArt } from 'grok-mermaid';
import stringWidth from 'string-width';
import { theme } from './theme.js';
import { useThemeVersion } from '../../themes/index.js';
import { MAX_MARKDOWN_LENGTH, MAX_VISIBLE_LINES } from '../../constants/limits.js';

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
  if (!art || art.warnings.length || art.width > maxWidth || art.plain.length > maxHeight ||
      art.plain.some(line => stringWidth(line) > maxWidth)) return null;
  return art;
}

export const MermaidDiagram: React.FC<{ art: MermaidArt; dimColor?: boolean }> = ({ art, dimColor = false }) => {
  useThemeVersion();
  return (
    <Box flexDirection="column" flexShrink={0}>
      {art.styled.map((row, index) => (
        <Text key={index} dimColor={dimColor} wrap="truncate">
          {row.map((span, spanIndex) => (
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
    </Box>
  );
};