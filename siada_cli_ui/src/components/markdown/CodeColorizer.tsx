/**
 * Code Colorizer
 * Syntax highlighting using lowlight (highlight.js AST version)
 * 
 * Supports 38 languages: arduino, bash, c, cpp, csharp, css, diff, go, graphql,
 * ini, java, javascript, json, kotlin, less, lua, makefile, markdown, objectivec,
 * perl, php, php-template, plaintext, python, python-repl, r, ruby, rust, scss,
 * shell, sql, swift, typescript, vbnet, wasm, xml, yaml
 */

import React from 'react';
import { Text, Box } from '@jrichman/ink';
import { common, createLowlight } from 'lowlight';
import type {
  Root,
  Element,
  Text as HastText,
  ElementContent,
  RootContent,
} from 'hast';
import { themeManager, type MarkdownTheme } from './theme.js';
import { normalizeLanguage, isLanguageSupported } from '../../utils/textHighlighter.js';

// Create lowlight instance with common languages
const lowlight = createLowlight(common);

/**
 * Render HAST node to React components
 */
function renderHastNode(
  node: Root | Element | HastText | RootContent,
  theme: MarkdownTheme,
  inheritedColor: string | undefined,
): React.ReactNode {
  if (node.type === 'text') {
    const color = inheritedColor || theme.defaultColor;
    return <Text color={color}>{node.value}</Text>;
  }

  if (node.type === 'element') {
    const nodeClasses: string[] =
      (node.properties?.['className'] as string[]) || [];
    let elementColor: string | undefined = undefined;

    // Find color for this element's class
    for (let i = nodeClasses.length - 1; i >= 0; i--) {
      const color = theme.getInkColor(nodeClasses[i]);
      if (color) {
        elementColor = color;
        break;
      }
    }

    const colorToPassDown = elementColor || inheritedColor;

    const children = node.children?.map(
      (child: ElementContent, index: number) => (
        <React.Fragment key={index}>
          {renderHastNode(child, theme, colorToPassDown)}
        </React.Fragment>
      ),
    );

    return <React.Fragment>{children}</React.Fragment>;
  }

  if (node.type === 'root') {
    if (!node.children || node.children.length === 0) {
      return null;
    }

    return node.children?.map((child: RootContent, index: number) => (
      <React.Fragment key={index}>
        {renderHastNode(child, theme, inheritedColor)}
      </React.Fragment>
    ));
  }

  return null;
}

/**
 * Highlight and render a single line
 */
function highlightAndRenderLine(
  line: string,
  language: string | null,
  theme: MarkdownTheme,
): React.ReactNode {
  try {
    // Normalize language name (handle aliases like 'js' -> 'javascript')
    const normalizedLang = normalizeLanguage(language);
    
    const getHighlightedLine = () => {
      // If no language or language not registered, use auto-detection
      if (!normalizedLang || !lowlight.registered(normalizedLang)) {
        return lowlight.highlightAuto(line);
      }
      
      // Use specified language
      return lowlight.highlight(normalizedLang, line);
    };

    const renderedNode = renderHastNode(getHighlightedLine(), theme, undefined);

    return renderedNode !== null ? renderedNode : line;
  } catch (_error) {
    return line;
  }
}

/**
 * Colorize a single line
 */
export function colorizeLine(
  line: string,
  language: string | null,
  theme?: MarkdownTheme,
): React.ReactNode {
  const activeTheme = theme || themeManager.getCurrentTheme();
  return highlightAndRenderLine(line, language, activeTheme);
}

export interface ColorizeCodeOptions {
  code: string;
  language?: string | null;
  availableHeight?: number;
  maxWidth: number;
  theme?: MarkdownTheme | null;
  hideLineNumbers?: boolean;
  /**
   * Whether to force a fixed width on the outer Box.
   * - true: use maxWidth to set Box width (default, for standalone blocks)
   * - false: let parent container control width, only use maxWidth for internal layout
   */
  constrainWidth?: boolean;
}

/**
 * Colorize code block with syntax highlighting
 */
export function colorizeCode({
  code,
  language = null,
  availableHeight,
  maxWidth,
  theme = null,
  hideLineNumbers = false,
  constrainWidth = true,
}: ColorizeCodeOptions): React.ReactNode {
  const codeToHighlight = code.replace(/\n$/, '');
  const activeTheme = theme || themeManager.getCurrentTheme();
  const showLineNumbers = !hideLineNumbers;
  
  // Ensure maxWidth is valid
  const safeMaxWidth = Math.max(20, maxWidth || 80);

  try {
    let lines = codeToHighlight.split('\n');
    const padWidth = String(lines.length).length;

    let hiddenLinesCount = 0;

    // Limit lines if height is constrained
    if (availableHeight !== undefined && lines.length > availableHeight) {
      const sliceIndex = lines.length - availableHeight;
      hiddenLinesCount = sliceIndex;
      lines = lines.slice(sliceIndex);
    }

    const renderedLines = lines.map((line, index) => {
      const contentToRender = highlightAndRenderLine(
        line,
        language,
        activeTheme,
      );

      return (
        <Box key={index}>
          {showLineNumbers && (
            <Text color={activeTheme.text.secondary}>
              {`${String(index + 1 + hiddenLinesCount).padStart(
                padWidth,
                ' ',
              )} `}
            </Text>
          )}
          <Text color={activeTheme.defaultColor} wrap="wrap">
            {contentToRender}
          </Text>
        </Box>
      );
    });

    // Show hidden lines indicator if content was truncated
    if (hiddenLinesCount > 0) {
      return (
        <Box
          flexDirection="column"
          width={constrainWidth ? safeMaxWidth : undefined}
        >
          <Text color={activeTheme.text.secondary} dimColor>
            ... {hiddenLinesCount} more lines above ...
          </Text>
          {renderedLines}
        </Box>
      );
    }

    return (
      <Box
        flexDirection="column"
        width={constrainWidth ? safeMaxWidth : undefined}
      >
        {renderedLines}
      </Box>
    );
  } catch (error) {
    // Fallback to plain text on error
    const lines = codeToHighlight.split('\n');
    const padWidth = String(lines.length).length;
    
    const fallbackLines = lines.map((line, index) => (
      <Box key={index}>
        {showLineNumbers && (
          <Text color={activeTheme.text.secondary}>
            {`${String(index + 1).padStart(padWidth, ' ')} `}
          </Text>
        )}
        <Text color={activeTheme.text.secondary}>{line}</Text>
      </Box>
    ));

    return (
      <Box
        flexDirection="column"
        width={constrainWidth ? safeMaxWidth : undefined}
      >
        {fallbackLines}
      </Box>
    );
  }
}
