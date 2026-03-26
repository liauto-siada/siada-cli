/**
 * Thinking and Loading Phrases
 * Collection of phrases to display during model thinking
 */

export const THINKING_PHRASES = [
  'Thinking...',
  'Analyzing your request...',
  'Processing information...',
];

export const WITTY_PHRASES = [
  'Thinking...',
];

export const INFORMATIVE_TIPS = [
  'Tip: Press ESC or Ctrl+C to stop',
  'Tip: Use @filename to reference files',
  'Tip: Press Ctrl+X to open in external editor',
];

export const STATUS_PHRASES = {
  INITIALIZING: 'Initializing Agent...',
  CONNECTING: 'Connecting to siada-cli...',
  CONFIRMING: 'Thinking...',
  THINKING: 'Thinking...',
  PROCESSING: 'Thinking...',
};

// Phrase rotation interval (milliseconds)
export const PHRASE_CHANGE_INTERVAL = 15000; // 15 seconds
