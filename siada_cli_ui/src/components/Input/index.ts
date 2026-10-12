/**
 * Input components - GitHub themed
 */
// InputPromptWithWrapUseKPC - uses KeypressContext instead of Ink's useInput
export { InputPromptWithWrapUseKPC } from './InputPromptWithWrapUseKPC.js';
export type { InputPromptWithWrapUseKPCProps } from './InputPromptWithWrapUseKPC.js';

// Shortcut-enabled single-line input (reuses the TextBuffer engine + keymap)
export { ShortcutTextInput } from './ShortcutTextInput.js';
export type { ShortcutTextInputProps } from './ShortcutTextInput.js';
export { applyShortcutKey, toSingleLine } from './shortcutKeymap.js';
export type { ShortcutBuffer, ShortcutKeyEnv, ShortcutDirection } from './shortcutKeymap.js';

// TextBuffer system
export { useTextBuffer, useEnhancedTextBuffer, calculateLayout, logicalToVisualCursor } from './TextBuffer.js';
export type { TextBuffer, EnhancedTextBuffer, Viewport, Direction, CursorPosition, VisualLayout } from './TextBuffer.js';

// TextBuffer Reducer
export { textBufferReducer, createInitialState } from './TextBufferReducer.js';
export type { TextBufferState, TextBufferAction, TextBufferOptions, HistoryEntry } from './TextBufferReducer.js';

// Keyboard bindings
export { Command, keyMatchers, defaultKeyBindings } from './keyBindings.js';
export type { Key, KeyBinding, KeyBindingConfig, KeyMatchers } from './keyBindings.js';

// Text utilities
export * from './textUtils.js';

// Theme
export { githubTheme, getThemeColor } from './theme.js';
export type { GithubTheme } from './theme.js';
