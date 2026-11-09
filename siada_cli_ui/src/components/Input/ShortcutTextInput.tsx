/**
 * ShortcutTextInput - context-free single-line input with the same
 * readline-style key bindings as the main prompt.
 *
 * The main prompt (`InputPromptWithWrapUseKPC`) is coupled to the app store
 * and chat features and only renders inside AppProvider, after login. This
 * component reuses the SAME editing engine (`useEnhancedTextBuffer`) and the
 * shared keymap (`shortcutKeymap`) so standalone prompts — such as the
 * Custom Provider login fields — get the same shortcuts.
 *
 * Key bindings: Enter submit · Esc cancel · Ctrl+A/E/F/L, Home/End ·
 * Ctrl+K/U, Ctrl+W, Alt+D · Alt/Ctrl+Left/Right, Alt+B/F · Ctrl+B copy ·
 * Ctrl+V / bracketed paste · Ctrl+D clear.
 *
 * Note: `initialValue` is only read on mount — pass a changing `key` prop to
 * remount the input when the initial value must change (e.g. going back a step).
 */

import React, { useMemo } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useEnhancedTextBuffer } from './TextBuffer.js';
import { isClipboardPasteKey, useClipboard } from '../../hooks/useClipboard.js';
import { cpLen, cpSlice } from './textUtils.js';
import { applyShortcutKey, toSingleLine } from './shortcutKeymap.js';

export interface ShortcutTextInputProps {
  /** Called with the trimmed value on a plain Enter. */
  onSubmit: (value: string) => void;
  /** Called on Escape. */
  onCancel?: () => void;
  /** Initial buffer content; read on mount only (see the component note). */
  initialValue?: string;
  /** Dim hint shown after the cursor while the buffer is empty. */
  placeholder?: string;
  /** Render the value as bullets (API keys). */
  masked?: boolean;
  /** Whether the input currently receives keystrokes. */
  active?: boolean;
  /** Prompt glyph rendered before the text. */
  prompt?: string;
}

export const ShortcutTextInput: React.FC<ShortcutTextInputProps> = ({
  onSubmit,
  onCancel,
  initialValue = '',
  placeholder = '',
  masked = false,
  active = true,
  prompt = '> ',
}) => {
  const buffer = useEnhancedTextBuffer({ width: 10_000, height: 1 }, {}, initialValue);
  const clipboard = useClipboard({
    active,
    owner: `${buffer.text}\0${buffer.cursorCol}`,
    onPaste: content => {
      if (content.kind === 'text') buffer.insert(toSingleLine(content.text));
    },
  });

  useKeypress(
    (key) => {
      if (!active) return;
      if (key.name === 'mousemiddle' && !isClipboardPasteKey(key)) return;
      if (key.name === 'mouseright' && (key.ctrl || key.cmd || key.alt || key.shift)) return;
      clipboard.onKey(key);
      if (key.name === 'mouseright') {
        clipboard.pasteOnRightClick();
        return;
      }
      if (isClipboardPasteKey(key)) {
        clipboard.paste(false);
        return;
      }
      applyShortcutKey(key, buffer, {
        onSubmit,
        onCancel,
        copyText: clipboard.copy,
      });
    },
    { isActive: active },
  );

  const { before, after } = useMemo(() => {
    const display = masked ? '•'.repeat(cpLen(buffer.text)) : buffer.text;
    const col = Math.max(0, Math.min(buffer.cursorCol, cpLen(display)));
    return { before: cpSlice(display, 0, col), after: cpSlice(display, col) };
  }, [buffer.text, buffer.cursorCol, masked]);

  return (
    <Box flexDirection="column" paddingX={1} marginBottom={1}>
      <Box>
        <Text color="cyan">{prompt}</Text>
        <Text>{before}</Text>
        <Text color="cyan">{'█'}</Text>
        <Text>{after}</Text>
        {buffer.text === '' && placeholder ? <Text dimColor>{placeholder}</Text> : null}
      </Box>
      {clipboard.message && <Text color="yellow" wrap="truncate-end">{clipboard.message}</Text>}
    </Box>
  );
};