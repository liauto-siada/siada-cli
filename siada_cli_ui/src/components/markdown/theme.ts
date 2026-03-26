/**
 * Markdown Theme Adapter
 */

import { colors } from '../../utils/colors.js';

export interface MarkdownTheme {
  text: {
    primary: string;
    secondary: string;
    accent: string;
    link: string;
    response: string;
  };
  code: Record<string, string>;
  defaultColor: string;
  getInkColor: (className: string) => string | undefined;
  // Smart highlighting colors
  highlight: {
    path: string;        // File path highlighting
    command: string;     // Bash command highlighting
    inlineCode: string;  // Inline code highlighting
    url: string;         // URL highlighting
  };
  // Border colors
  border: {
    default: string;
  };
}

/**
 * Syntax highlighting color mappings
 * Based on Dracula theme
 */
const syntaxColors: Record<string, string> = {
  // Keywords
  'hljs-keyword': colors.syntax.keyword,
  'hljs-built_in': colors.syntax.keyword,
  'hljs-type': colors.syntax.keyword,
  'hljs-literal': colors.syntax.keyword,
  'hljs-selector-tag': colors.syntax.keyword,
  'hljs-selector-id': colors.syntax.keyword,
  'hljs-selector-class': colors.syntax.keyword,
  
  // Strings
  'hljs-string': colors.syntax.string,
  'hljs-title.function': colors.syntax.string,
  'hljs-attribute': colors.syntax.string,
  'hljs-symbol': colors.syntax.string,
  'hljs-bullet': colors.syntax.string,
  'hljs-addition': colors.syntax.string,
  'hljs-link': colors.syntax.string,
  'hljs-regexp': colors.syntax.string,
  
  // Numbers
  'hljs-number': colors.syntax.number,
  'hljs-meta': colors.syntax.number,
  
  // Comments
  'hljs-comment': colors.syntax.comment,
  'hljs-quote': colors.syntax.comment,
  'hljs-doctag': colors.syntax.comment,
  
  // Functions
  'hljs-title': colors.syntax.function,
  'hljs-section': colors.syntax.function,
  'hljs-name': colors.syntax.function,
  'hljs-variable': colors.syntax.function,
  'hljs-template-variable': colors.syntax.function,
  
  // Classes & Types
  'hljs-class': colors.syntax.class,
  'hljs-title.class': colors.syntax.class,
  'hljs-params': colors.syntax.class,
  'hljs-attr': colors.syntax.class,
  
  // Variables
  'hljs-variable.language': colors.syntax.variable,
  'hljs-property': colors.syntax.variable,
  
  // Special
  'hljs-deletion': colors.error,
  'hljs-tag': colors.info,
  'hljs-operator': colors.gray[300],
  'hljs-punctuation': colors.gray[400],
  
  // Markdown specific
  'hljs-section.markdown': colors.primary,
  'hljs-emphasis': colors.syntax.keyword,
  'hljs-strong': colors.syntax.keyword,
  'hljs-code': colors.syntax.function,
};

/**
 * Create markdown theme instance
 */
export const markdownTheme: MarkdownTheme = {
  text: {
    primary: colors.white,
    secondary: colors.gray[400],
    accent: colors.syntax.function,
    link: colors.info,
    response: colors.white,
  },
  
  code: syntaxColors,
  
  defaultColor: colors.white,
  
  // Smart highlighting colors
  highlight: {
    path: '#58a6ff',        // Cyan/Blue for file paths
    command: '#3fb950',      // Green for bash commands
    inlineCode: '#f0883e',   // Orange for inline code
    url: '#58a6ff',          // Cyan for URLs
  },
  
  // Border colors
  border: {
    default: colors.gray[500],
  },
  
  getInkColor(className: string): string | undefined {
    return this.code[className];
  },
};

/**
 * Export for convenience
 */
export const theme = markdownTheme;

/**
 * Theme manager interface
 */
export const themeManager = {
  getCurrentTheme: () => markdownTheme,
};
