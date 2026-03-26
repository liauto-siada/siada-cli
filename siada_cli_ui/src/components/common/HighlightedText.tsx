/**
 * Highlighted Text Component
 * Smart text rendering with automatic highlighting for paths, commands, and code
 */

import React from 'react';
import { Text } from '@jrichman/ink';
import { highlightSegments, type TextSegment } from '../../utils/textHighlighter.js';
import { theme } from '../markdown/theme.js';

export interface HighlightedTextProps {
  /** Text content to render */
  text: string;
  
  /** Enable file path highlighting */
  enablePathHighlight?: boolean;
  
  /** Enable bash command highlighting */
  enableCommandHighlight?: boolean;
  
  /** Enable inline code highlighting */
  enableCodeHighlight?: boolean;
  
  /** Enable URL highlighting */
  enableURLHighlight?: boolean;
  
  /** Default text color */
  defaultColor?: string;
  
  /** Whether text is bold */
  bold?: boolean;
  
  /** Whether text is italic */
  italic?: boolean;
  
  /** Whether text is dimmed */
  dimColor?: boolean;
}

/**
 * Render a single text segment with appropriate styling
 */
function renderSegment(
  segment: TextSegment,
  key: string | number,
  defaultColor?: string,
  bold?: boolean,
  italic?: boolean,
  dimColor?: boolean,
): React.ReactNode {
  let color: string | undefined;
  
  switch (segment.type) {
    case 'path':
      color = theme.highlight.path;
      break;
    case 'command':
      color = theme.highlight.command;
      break;
    case 'inlineCode':
      color = theme.highlight.inlineCode;
      // Remove backticks for display
      const codeContent = segment.content.replace(/^`|`$/g, '');
      return (
        <Text key={key} color={color} bold>
          {codeContent}
        </Text>
      );
    case 'url':
      color = theme.highlight.url;
      break;
    case 'text':
    default:
      color = defaultColor || theme.defaultColor;
      break;
  }
  
  return (
    <Text
      key={key}
      color={color}
      bold={bold}
      italic={italic}
      dimColor={dimColor}
    >
      {segment.content}
    </Text>
  );
}

/**
 * HighlightedText Component
 * Automatically detects and highlights file paths, bash commands, inline code, and URLs
 */
export const HighlightedText: React.FC<HighlightedTextProps> = ({
  text,
  enablePathHighlight = true,
  enableCommandHighlight = true,
  enableCodeHighlight = true,
  enableURLHighlight = true,
  defaultColor,
  bold,
  italic,
  dimColor,
}) => {
  // Get highlighted segments
  const segments = highlightSegments(text, {
    enablePathHighlight,
    enableCommandHighlight,
    enableCodeHighlight,
    enableURLHighlight,
  });
  
  // If no special segments found, render as plain text
  if (segments.length === 1 && segments[0].type === 'text') {
    return (
      <Text
        color={defaultColor || theme.defaultColor}
        bold={bold}
        italic={italic}
        dimColor={dimColor}
      >
        {text}
      </Text>
    );
  }
  
  // Render each segment with appropriate styling
  return (
    <>
      {segments.map((segment, index) =>
        renderSegment(segment, index, defaultColor, bold, italic, dimColor)
      )}
    </>
  );
};

/**
 * Inline variant - for use within other text components
 */
export const InlineHighlightedText: React.FC<HighlightedTextProps> = (props) => {
  return <HighlightedText {...props} />;
};
