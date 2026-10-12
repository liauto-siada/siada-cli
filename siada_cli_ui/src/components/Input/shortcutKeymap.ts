/**
 * Shared readline-style keymap for single-line prompt inputs.
 *
 * This mirrors the editing half of the main prompt's key handler
 * (`InputPromptWithWrapUseKPC`) so standalone interactive prompts — e.g. the
 * Custom Provider login fields (base URL / model / API key) — get the same
 * shortcuts (Ctrl+A/E, Ctrl+K/U, Ctrl+W, Alt+D, Ctrl+B copy, Ctrl+V paste,
 * word navigation, ...).
 *
 * It is dependency-free so it can be unit tested without rendering Ink.
 */

import type { Key } from '../../contexts/KeypressContext.js';

/** Cursor directions this keymap can request from a text buffer. */
export type ShortcutDirection = 'left' | 'right' | 'home' | 'end' | 'wordLeft' | 'wordRight';

/** Minimal text-buffer surface the keymap drives (satisfied by `useEnhancedTextBuffer`). */
export interface ShortcutBuffer {
  readonly text: string;
  insert(text: string): void;
  backspace(count?: number): void;
  deleteWordLeft(): void;
  deleteWordRight(): void;
  killLineRight(): void;
  killLineLeft(): void;
  moveCursor(direction: ShortcutDirection): void;
  clear(): void;
}

/** Side effects the keymap needs from its host component. */
export interface ShortcutKeyEnv {
  /** Called with the trimmed value on a plain Enter. */
  onSubmit(value: string): void;
  /** Called on Escape (e.g. go back to the previous step). */
  onCancel?(): void;
  /** Copy the buffer to the OS clipboard (Ctrl+B). */
  copyText?(text: string): void;
  /** Read text from the OS clipboard (Ctrl/Cmd+V). */
  readClipboard?(): Promise<string | null>;
}

/** Single-line fields must never contain line breaks; drop them on insert. */
export function toSingleLine(text: string): string {
  return text.replace(/[\r\n]+/g, '');
}

/**
 * Apply one keypress to a single-line buffer. Returns nothing; the buffer is
 * mutated through its own actions and submit/cancel are reported via `env`.
 */
export function applyShortcutKey(key: Key, buffer: ShortcutBuffer, env: ShortcutKeyEnv): void {
  // Submit on a plain Enter. Modified Enter inserts a newline in the multi-line
  // main prompt — meaningless here, so it is a no-op.
  if (key.name === 'return' || key.name === 'enter') {
    if (key.shift || key.ctrl || key.alt || key.cmd) return;
    env.onSubmit(toSingleLine(buffer.text).trim());
    return;
  }
  if (key.name === 'escape') {
    env.onCancel?.();
    return;
  }

  // Cursor / kill ring (readline)
  if (key.ctrl && key.name === 'a') { buffer.moveCursor('home'); return; }
  if (key.ctrl && key.shift && key.name === 'a') { buffer.moveCursor('home'); return; }
  if (key.ctrl && key.name === 'e') { buffer.moveCursor('end'); return; }
  if (key.ctrl && key.shift && key.name === 'e') { buffer.moveCursor('end'); return; }
  if (key.ctrl && key.name === 'f') { buffer.moveCursor('right'); return; }
  if (key.ctrl && key.name === 'l') { buffer.moveCursor('end'); return; }
  if (key.ctrl && key.name === 'w') { buffer.deleteWordLeft(); return; }
  if (key.alt && key.name === 'd') { buffer.deleteWordRight(); return; }
  if ((key.cmd || key.alt) && key.name === 'backspace') { buffer.deleteWordLeft(); return; }
  if (key.ctrl && key.name === 'k') { buffer.killLineRight(); return; }
  if (key.ctrl && key.name === 'u') { buffer.killLineLeft(); return; }
  if (key.ctrl && key.name === 'd') { buffer.clear(); return; }
  if (key.ctrl && key.name === 'b') {
    if (buffer.text) env.copyText?.(buffer.text);
    return;
  }

  // Word movement: Alt/Option+Left/Right, Ctrl+Left/Right, Meta+B/F (readline)
  if ((key.alt || key.ctrl) && key.name === 'left') { buffer.moveCursor('wordLeft'); return; }
  if ((key.alt || key.ctrl) && key.name === 'right') { buffer.moveCursor('wordRight'); return; }
  if (key.alt && key.name === 'b') { buffer.moveCursor('wordLeft'); return; }
  if (key.alt && key.name === 'f') { buffer.moveCursor('wordRight'); return; }
  if (key.name === 'left') { buffer.moveCursor('left'); return; }
  if (key.name === 'right') { buffer.moveCursor('right'); return; }
  if (key.name === 'home') { buffer.moveCursor('home'); return; }
  if (key.name === 'end') { buffer.moveCursor('end'); return; }
  if (key.name === 'backspace' || key.name === 'delete') { buffer.backspace(); return; }

  // Ctrl+V / Cmd+V: read the OS clipboard explicitly (bracketed paste may be absent)
  if ((key.ctrl || key.cmd) && key.name === 'v') {
    void (async () => {
      const pasted = await env.readClipboard?.();
      if (pasted) buffer.insert(toSingleLine(pasted));
    })();
    return;
  }

  // Bracketed paste arrives as one event; insert it in a single dispatch.
  if (key.name === 'paste') {
    buffer.insert(toSingleLine(key.sequence ?? ''));
    return;
  }

  if (key.insertable && key.sequence && !key.ctrl && !key.alt && !key.cmd) {
    buffer.insert(toSingleLine(key.sequence));
  }
}