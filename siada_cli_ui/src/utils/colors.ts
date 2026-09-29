/**
 * Color Theme System
 * Provides color utilities and theme management for terminal UI
 */

import chalk from 'chalk';

/**
 * Dark color palette (default)
 */
const darkColors = {
  // Primary colors
  primary: '#3B82F6',      // Blue
  secondary: '#8B5CF6',    // Purple
  success: '#10B981',      // Green
  warning: '#F59E0B',      // Orange
  error: '#EF4444',        // Red
  info: '#06B6D4',         // Cyan
  
  // Grayscale
  white: '#FFFFFF',
  black: '#000000',
  gray: {
    50: '#F9FAFB',
    100: '#F3F4F6',
    200: '#E5E7EB',
    300: '#D1D5DB',
    400: '#9CA3AF',
    500: '#6B7280',
    600: '#4B5563',
    700: '#374151',
    800: '#1F2937',
    900: '#111827',
  },
  
  // Message types
  user: '#10B981',         // Green
  agent: '#3B82F6',        // Blue
  system: '#F59E0B',       // Orange
  tool: '#8B5CF6',         // Purple
  
  // Syntax highlighting
  syntax: {
    keyword: '#FF79C6',
    string: '#50FA7B',
    number: '#BD93F9',
    comment: '#6272A4',
    function: '#8BE9FD',
    class: '#FFB86C',
    variable: '#F8F8F2',
  },

  // Message bodies (tool values, commands, answers) inherit the terminal's own
  // foreground, exactly like the plain text of a "Run N commands" heading. The
  // two tones below add the hierarchy back on top of it: `secondary` is a
  // clearly readable step down (reasoning text, hints, diff context) rather
  // than a washed-out gray, and `tertiary` is for structure (line numbers,
  // separators). Every value is checked against Solarized, Gruvbox, Nord and
  // friends instead of assuming a pure black or pure white canvas.
  content: {
    secondary: '#b9c2cc', // Reasoning text, hints, connectors, diff context
    tertiary: '#8f97a1',  // Line numbers, separators, tertiary metadata
    border: '#4b5563',    // Frames around thinking and tool blocks
    surface: '#262a30',   // Subtle background behind expanded commands
  },

  // Diff bands: the band tints the background and the code keeps the terminal
  // foreground, so a band must stay far enough from that foreground's pole.
  // Only the +/- signs and the word-level highlight carry their own color.
  diff: {
    addedBg: '#1a4a1a',
    addedSign: '#4ade80',
    addedWordBg: '#1f5f27',
    removedBg: '#4a1a1a',
    removedSign: '#f87171',
    removedWordBg: '#6b2626',
  },
};

/**
 * Light color palette (GitHub Light style, tuned for light terminal backgrounds)
 */
const lightColors: typeof darkColors = {
  // Primary colors
  primary: '#0969da',
  secondary: '#8250df',
  success: '#1a7f37',
  warning: '#9a6700',
  error: '#d1242f',
  info: '#0550ae',

  // Grayscale
  white: '#FFFFFF',
  black: '#000000',
  gray: {
    50: '#F9FAFB',
    100: '#F3F4F6',
    200: '#E5E7EB',
    300: '#D1D5DB',
    400: '#9CA3AF',
    500: '#6B7280',
    600: '#4B5563',
    700: '#374151',
    800: '#1F2937',
    900: '#111827',
  },

  // Message types
  user: '#1a7f37',
  agent: '#0969da',
  system: '#9a6700',
  tool: '#8250df',

  // Syntax highlighting (GitHub Light)
  syntax: {
    keyword: '#cf222e',
    string: '#0a3069',
    number: '#0550ae',
    comment: '#6e7781',
    function: '#8250df',
    class: '#953800',
    variable: '#1f2328',
  },

  // Message bodies (thinking, tool output, diffs) — see darkColors.content.
  content: {
    secondary: '#4b5563',
    tertiary: '#6e7781',
    border: '#c8d1da',
    surface: '#f0f1f3',
  },

  diff: {
    addedBg: '#d3f2dc',
    addedSign: '#14752f',
    addedWordBg: '#8fe0a4',
    removedBg: '#ffdfdd',
    removedSign: '#b81f2a',
    removedWordBg: '#ffb8b3',
  },
};

/**
 * Live color palette. Starts as the dark theme; applyColorsTheme() mutates
 * it in place so helpers that read colors.* at call time follow the active
 * theme.
 */
export const colors: typeof darkColors = {
  ...darkColors,
  gray: { ...darkColors.gray },
  syntax: { ...darkColors.syntax },
  content: { ...darkColors.content },
  diff: { ...darkColors.diff },
};

/**
 * Apply a named palette to the live `colors` object (in place).
 */
export function applyColorsTheme(theme: 'dark' | 'light'): void {
  const source = theme === 'light' ? lightColors : darkColors;
  colors.primary = source.primary;
  colors.secondary = source.secondary;
  colors.success = source.success;
  colors.warning = source.warning;
  colors.error = source.error;
  colors.info = source.info;
  colors.user = source.user;
  colors.agent = source.agent;
  colors.system = source.system;
  colors.tool = source.tool;
  Object.assign(colors.syntax, source.syntax);
  Object.assign(colors.content, source.content);
  Object.assign(colors.diff, source.diff);
}

/**
 * Color utilities using chalk
 */
export const colorize = {
  // Status colors
  success: (text: string) => chalk.hex(colors.success)(text),
  error: (text: string) => chalk.hex(colors.error)(text),
  warning: (text: string) => chalk.hex(colors.warning)(text),
  info: (text: string) => chalk.hex(colors.info)(text),
  
  // Message types
  user: (text: string) => chalk.hex(colors.user)(text),
  agent: (text: string) => chalk.hex(colors.agent)(text),
  system: (text: string) => chalk.hex(colors.system)(text),
  tool: (text: string) => chalk.hex(colors.tool)(text),
  
  // Emphasis
  bold: (text: string) => chalk.bold(text),
  dim: (text: string) => chalk.dim(text),
  italic: (text: string) => chalk.italic(text),
  underline: (text: string) => chalk.underline(text),
  
  // Grayscale
  gray: (text: string) => chalk.hex(colors.gray[500])(text),
  darkGray: (text: string) => chalk.hex(colors.gray[700])(text),
  lightGray: (text: string) => chalk.hex(colors.gray[300])(text),
  
  // Syntax
  keyword: (text: string) => chalk.hex(colors.syntax.keyword)(text),
  string: (text: string) => chalk.hex(colors.syntax.string)(text),
  number: (text: string) => chalk.hex(colors.syntax.number)(text),
  comment: (text: string) => chalk.hex(colors.syntax.comment)(text),
  
  // Custom hex color
  hex: (color: string) => (text: string) => chalk.hex(color)(text),
  
  // Background colors
  bgSuccess: (text: string) => chalk.bgHex(colors.success).black(text),
  bgError: (text: string) => chalk.bgHex(colors.error).white(text),
  bgWarning: (text: string) => chalk.bgHex(colors.warning).black(text),
  bgInfo: (text: string) => chalk.bgHex(colors.info).black(text),
};

/**
 * Get color for message type
 */
export function getMessageColor(type: string): string {
  const colorMap: Record<string, string> = {
    user: colors.user,
    agent: colors.agent,
    system: colors.system,
    error: colors.error,
    tool: colors.tool,
  };
  return colorMap[type] || colors.gray[500];
}

/**
 * Get color for status
 */
export function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    success: colors.success,
    pending: colors.warning,
    running: colors.info,
    error: colors.error,
    idle: colors.gray[500],
    connected: colors.success,
    disconnected: colors.error,
    connecting: colors.warning,
  };
  return colorMap[status] || colors.gray[500];
}

/**
 * Format diff colors
 */
export const diffColors = {
  added: (text: string) => chalk.green(text),
  removed: (text: string) => chalk.red(text),
  modified: (text: string) => chalk.yellow(text),
  unchanged: (text: string) => chalk.gray(text),
  lineNumber: (text: string) => chalk.dim(text),
};

/**
 * Format file type colors
 */
export function getFileTypeColor(filename: string): (text: string) => string {
  const ext = filename.split('.').pop()?.toLowerCase();
  
  const colorMap: Record<string, string> = {
    // Code files
    js: colors.syntax.keyword,
    ts: colors.primary,
    jsx: colors.syntax.keyword,
    tsx: colors.primary,
    py: colors.info,
    go: colors.info,
    rs: colors.error,
    java: colors.error,
    
    // Web files
    html: colors.error,
    css: colors.primary,
    scss: colors.secondary,
    
    // Config files
    json: colors.syntax.number,
    yaml: colors.warning,
    yml: colors.warning,
    toml: colors.warning,
    
    // Docs
    md: colors.gray[400],
    txt: colors.gray[400],
    
    // Other
    default: colors.gray[500],
  };
  
  const color = ext ? colorMap[ext] || colorMap.default : colorMap.default;
  return chalk.hex(color);
}

/**
 * Create gradient text (simple simulation)
 */
export function gradient(text: string, startColor: string, endColor: string): string {
  // Simple implementation - just use start color
  // Full gradient would require char-by-char coloring
  return chalk.hex(startColor)(text);
}

/**
 * Format timestamp with color
 */
export function colorizeTimestamp(timestamp: string | Date): string {
  const time = typeof timestamp === 'string' ? timestamp : timestamp.toISOString();
  return colorize.dim(`[${time}]`);
}

/**
 * Format badge with background color
 */
export function badge(text: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): string {
  const badgeColors = {
    success: colorize.bgSuccess,
    error: colorize.bgError,
    warning: colorize.bgWarning,
    info: colorize.bgInfo,
  };
  return badgeColors[type](` ${text} `);
}

/**
 * Progress bar color based on percentage
 */
export function getProgressColor(percentage: number): string {
  if (percentage < 33) return colors.error;
  if (percentage < 66) return colors.warning;
  return colors.success;
}

/**
 * Format log level with color
 */
export function colorizeLogLevel(level: string): string {
  const levelColors: Record<string, (text: string) => string> = {
    DEBUG: colorize.gray,
    INFO: colorize.info,
    WARN: colorize.warning,
    ERROR: colorize.error,
  };
  const colorFn = levelColors[level.toUpperCase()] || colorize.gray;
  return colorFn(level.toUpperCase().padEnd(5));
}

/**
 * Box drawing characters with colors
 */
export const boxChars = {
  topLeft: '┌',
  topRight: '┐',
  bottomLeft: '└',
  bottomRight: '┘',
  horizontal: '─',
  vertical: '│',
  cross: '┼',
  teeUp: '┴',
  teeDown: '┬',
  teeLeft: '┤',
  teeRight: '├',
};

/**
 * Create colored box
 */
export function coloredBox(
  text: string,
  color: string = colors.primary,
  padding: number = 1
): string {
  const lines = text.split('\n');
  const maxLength = Math.max(...lines.map(l => l.length));
  const width = maxLength + padding * 2;
  
  const colorFn = chalk.hex(color);
  const pad = ' '.repeat(padding);
  
  const top = colorFn(boxChars.topLeft + boxChars.horizontal.repeat(width) + boxChars.topRight);
  const bottom = colorFn(boxChars.bottomLeft + boxChars.horizontal.repeat(width) + boxChars.bottomRight);
  
  const content = lines.map(line => {
    const paddedLine = line.padEnd(maxLength);
    return colorFn(boxChars.vertical) + pad + paddedLine + pad + colorFn(boxChars.vertical);
  });
  
  return [top, ...content, bottom].join('\n');
}

/**
 * Rainbow colors for fun
 */
export const rainbow = [
  '#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF', '#4B0082', '#9400D3'
];

/**
 * Apply rainbow effect to text
 */
export function rainbowText(text: string): string {
  return text.split('').map((char, i) => {
    const color = rainbow[i % rainbow.length];
    return chalk.hex(color)(char);
  }).join('');
}
