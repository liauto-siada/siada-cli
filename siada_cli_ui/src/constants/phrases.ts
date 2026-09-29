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

/**
 * Thinking Steps
 * Step descriptions for the phases an agent turn goes through while the
 * "thinking" indicator is visible. Derived from the incoming ACP message
 * stream so the UI can tell the user WHAT the agent is currently doing.
 */
export type ThinkingStep = 'reasoning' | 'tool_execution' | 'system_processing' | 'compaction';

export interface ThinkingStepInfo {
  /** Short label shown next to thinking content summaries */
  label: string;
  /** Live phrase shown in the thinking indicator while the step is active */
  phrase: string;
}

export const THINKING_STEPS: Record<ThinkingStep, ThinkingStepInfo> = {
  reasoning: { label: 'Model Reasoning', phrase: 'Model reasoning...' },
  tool_execution: { label: 'Tool Execution', phrase: 'Executing tools...' },
  system_processing: { label: 'System Processing', phrase: 'System processing...' },
  compaction: { label: 'Context Compaction', phrase: 'Compacting context...' },
};

/**
 * Content pattern marking a non-streaming process/system message as context
 * compaction activity (backend compaction notices mention compact/compress,
 * or the Chinese term for compression).
 */
export const COMPACTION_CONTENT_PATTERN = /compact|compress|压缩/i;

/**
 * Shortcut hints shown after the thinking step phrase as "(tips: ...)".
 * One entry per shortcut (from the siada-cli shortcuts wiki) so each hint
 * gets its own slot when the indicator rotates tips for the user.
 */
export const SHORTCUT_TIPS = [
  'Tip: Ctrl+J inserts a newline',
  'Tip: Alt+Enter inserts a newline (VSCode / Ubuntu terminals; behavior varies, prefer Ctrl+J)',
  'Tip: Type ! to toggle Shell mode',
  'Tip: Esc exits Shell mode, dismisses completion, or interrupts the answer',
  'Tip: Ctrl+W deletes the word left of the cursor (space separated)',
  'Tip: Ctrl+K deletes from the cursor to the end of the line',
  'Tip: Ctrl+U deletes from the cursor to the start of the line',
  'Tip: Ctrl+A moves the cursor to the start of the line',
  'Tip: Ctrl+E moves the cursor to the end of the line',
  'Tip: Ctrl+X opens the current input in an external editor',
  'Tip: Ctrl+D clears the entire input',
  'Tip: Ctrl+C interrupts the answer; press twice to exit (Esc equals one Ctrl+C)',
  'Tip: Ctrl+O toggles compact / expand display mode',
  'Tip: Option+Left/Right moves the cursor by word',
  'Tip: Ctrl+V pastes clipboard images and text',
  'Tip: Shift+Enter inserts a newline (iTerm2 and other Kitty-protocol terminals)',
  'Tip: Ctrl+L moves the cursor to the end of the line (same as Ctrl+E)',
  'Tip: Ctrl+B copies the entire input to the system clipboard',
];

// Input hint rotation interval (milliseconds)
export const TIP_CHANGE_INTERVAL = 30000; // 30 seconds
