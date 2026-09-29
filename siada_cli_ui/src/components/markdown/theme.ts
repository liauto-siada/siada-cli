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
 * Syntax highlighting color mappings for the light theme (GitHub Light)
 */
const lightSyntaxColors: Record<string, string> = {
  // Keywords
  'hljs-keyword': '#cf222e',
  'hljs-built_in': '#cf222e',
  'hljs-type': '#cf222e',
  'hljs-literal': '#cf222e',
  'hljs-selector-tag': '#cf222e',
  'hljs-selector-id': '#cf222e',
  'hljs-selector-class': '#cf222e',

  // Strings
  'hljs-string': '#0a3069',
  'hljs-title.function': '#0a3069',
  'hljs-attribute': '#0a3069',
  'hljs-symbol': '#0a3069',
  'hljs-bullet': '#0a3069',
  'hljs-addition': '#0a3069',
  'hljs-link': '#0a3069',
  'hljs-regexp': '#0a3069',

  // Numbers
  'hljs-number': '#0550ae',
  'hljs-meta': '#0550ae',

  // Comments
  'hljs-comment': '#6e7781',
  'hljs-quote': '#6e7781',
  'hljs-doctag': '#6e7781',

  // Functions
  'hljs-title': '#8250df',
  'hljs-section': '#8250df',
  'hljs-name': '#8250df',
  'hljs-variable': '#8250df',
  'hljs-template-variable': '#8250df',

  // Classes & Types
  'hljs-class': '#953800',
  'hljs-title.class': '#953800',
  'hljs-params': '#953800',
  'hljs-attr': '#953800',

  // Variables
  'hljs-variable.language': '#1f2328',
  'hljs-property': '#1f2328',

  // Special
  'hljs-deletion': '#d1242f',
  'hljs-tag': '#0550ae',
  'hljs-operator': '#59636e',
  'hljs-punctuation': '#81898f',

  // Markdown specific
  'hljs-section.markdown': '#0969da',
  'hljs-emphasis': '#cf222e',
  'hljs-strong': '#cf222e',
  'hljs-code': '#8250df',
};

type MarkdownThemeData = Omit<MarkdownTheme, 'getInkColor'>;

const markdownDarkTheme: MarkdownThemeData = {
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
};

const markdownLightTheme: MarkdownThemeData = {
  text: {
    primary: '#1f2328',
    secondary: '#59636e',
    accent: '#8250df',
    link: '#0969da',
    response: '#1f2328',
  },

  code: lightSyntaxColors,

  defaultColor: '#1f2328',

  highlight: {
    path: '#0969da',
    command: '#1a7f37',
    inlineCode: '#be4e02',
    url: '#0969da',
  },

  border: {
    default: '#d1d9e0',
  },
};

/**
 * Live markdown theme. Starts as the dark theme; applyMarkdownTheme() swaps
 * its fields in place so components reading markdownTheme.* (or the `theme`
 * alias) at render time follow the active theme.
 */
export const markdownTheme: MarkdownTheme = {
  ...markdownDarkTheme,
  getInkColor(className: string): string | undefined {
    return this.code[className];
  },
};

/**
 * Apply a named markdown theme to the live `markdownTheme` object (in place).
 */
export function applyMarkdownTheme(theme: 'dark' | 'light'): void {
  Object.assign(markdownTheme, theme === 'light' ? markdownLightTheme : markdownDarkTheme);
}

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
