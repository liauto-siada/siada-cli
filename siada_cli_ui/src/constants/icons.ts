/**
 * Icon Constants
 * Provides both Emoji and ASCII versions of icons to prevent Terminal crashes
 */

export interface IconSet {
  thinking: string;
  toolUse: string;
  agent: string;
  system: string;
  error: string;
  tool: string;
  bullet: string;
  success: string;
  warning: string;
  info: string;
  pending: string;
  connecting: string;
  fileEdited: string;
  fileText: string;
  fileMarkdown: string;
  fileJson: string;
  arrowRight: string;
  arrowDown: string;
}

export const EMOJI_ICONS: IconSet = {
  thinking: '💭',
  toolUse: '🔧',
  agent: '⚡',
  system: 'ℹ',
  error: '✗',
  tool: '🔧',
  bullet: '•',
  success: '✓',
  warning: '⚠',
  info: 'ℹ',
  pending: '⋯',
  connecting: '⏳',
  fileEdited: '📝',
  fileText: '📄',
  fileMarkdown: '📝',
  fileJson: '📋',
  arrowRight: '▶',
  arrowDown: '▼',
};

export const ASCII_ICONS: IconSet = {
  thinking: '...',
  toolUse: '[T]',
  agent: '●',
  system: '▶',
  error: '[X]',
  tool: '[T]',
  bullet: '*',
  success: '[OK]',
  warning: '[!]',
  info: '[i]',
  pending: '...',
  connecting: '...',
  fileEdited: '[E]',
  fileText: '[F]',
  fileMarkdown: '[M]',
  fileJson: '[J]',
  arrowRight: '>',
  arrowDown: 'v',
};

// Always use ASCII icons for terminal stability
const currentIconSet: IconSet = ASCII_ICONS;

export const getIcons = (): IconSet => currentIconSet;
