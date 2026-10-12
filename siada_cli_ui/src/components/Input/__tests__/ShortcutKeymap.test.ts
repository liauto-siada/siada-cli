import { describe, it, expect, vi } from 'vitest';
import { applyShortcutKey, toSingleLine } from '../shortcutKeymap.js';
import type { ShortcutBuffer, ShortcutKeyEnv } from '../shortcutKeymap.js';
import type { Key } from '../../../contexts/KeypressContext.js';

function makeKey(overrides: Partial<Key>): Key {
  return {
    name: '',
    shift: false,
    alt: false,
    ctrl: false,
    cmd: false,
    insertable: false,
    sequence: '',
    ...overrides,
  };
}

class RecorderBuffer implements ShortcutBuffer {
  calls: string[] = [];
  constructor(public text = '') {}
  insert(text: string) { this.calls.push(`insert:${text}`); }
  backspace() { this.calls.push('backspace'); }
  deleteWordLeft() { this.calls.push('deleteWordLeft'); }
  deleteWordRight() { this.calls.push('deleteWordRight'); }
  killLineRight() { this.calls.push('killLineRight'); }
  killLineLeft() { this.calls.push('killLineLeft'); }
  moveCursor(direction: string) { this.calls.push(`moveCursor:${direction}`); }
  clear() { this.calls.push('clear'); }
}

function run(key: Partial<Key>, text = 'hello world', env: Partial<ShortcutKeyEnv> = {}) {
  const buffer = new RecorderBuffer(text);
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  applyShortcutKey(makeKey(key), buffer, { onSubmit, onCancel, ...env });
  return { buffer, onSubmit, onCancel };
}

describe('toSingleLine', () => {
  it('strips all line breaks', () => {
    expect(toSingleLine('a\r\nb\rc\nd')).toBe('abcd');
  });
});

describe('applyShortcutKey - submit / cancel', () => {
  it('submits the trimmed value on a plain Enter', () => {
    const { onSubmit, buffer } = run({ name: 'return' }, '  https://x/v1  ');
    expect(onSubmit).toHaveBeenCalledWith('https://x/v1');
    expect(buffer.calls).toEqual([]);
  });

  it('ignores modified Enter (newline in the multi-line prompt)', () => {
    const { onSubmit } = run({ name: 'return', shift: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('cancels on Escape', () => {
    const { onCancel } = run({ name: 'escape' });
    expect(onCancel).toHaveBeenCalled();
  });
});

describe('applyShortcutKey - readline editing shortcuts', () => {
  it.each([
    [{ name: 'a', ctrl: true }, 'moveCursor:home'],
    [{ name: 'e', ctrl: true }, 'moveCursor:end'],
    [{ name: 'f', ctrl: true }, 'moveCursor:right'],
    [{ name: 'l', ctrl: true }, 'moveCursor:end'],
    [{ name: 'w', ctrl: true }, 'deleteWordLeft'],
    [{ name: 'd', alt: true }, 'deleteWordRight'],
    [{ name: 'k', ctrl: true }, 'killLineRight'],
    [{ name: 'u', ctrl: true }, 'killLineLeft'],
    [{ name: 'd', ctrl: true }, 'clear'],
    [{ name: 'left', alt: true }, 'moveCursor:wordLeft'],
    [{ name: 'right', ctrl: true }, 'moveCursor:wordRight'],
    [{ name: 'b', alt: true }, 'moveCursor:wordLeft'],
    [{ name: 'f', alt: true }, 'moveCursor:wordRight'],
    [{ name: 'backspace' }, 'backspace'],
    [{ name: 'delete' }, 'backspace'],
  ])('%j -> %s', (key, expected) => {
    const { buffer } = run(key);
    expect(buffer.calls).toEqual([expected]);
  });

  it('copies the buffer on Ctrl+B without touching it', () => {
    const copyText = vi.fn();
    const { buffer } = run({ name: 'b', ctrl: true }, 'secret', { copyText });
    expect(copyText).toHaveBeenCalledWith('secret');
    expect(buffer.calls).toEqual([]);
  });
});

describe('applyShortcutKey - text insertion', () => {
  it('inserts printable input', () => {
    const { buffer } = run({ name: 'x', sequence: 'x', insertable: true });
    expect(buffer.calls).toEqual(['insert:x']);
  });

  it('inserts a bracketed paste as a single line', () => {
    const { buffer } = run({ name: 'paste', sequence: 'https://a\n/v1\n' });
    expect(buffer.calls).toEqual(['insert:https://a/v1']);
  });

  it('reads the clipboard on Ctrl+V and inserts it as a single line', async () => {
    const readClipboard = vi.fn().mockResolvedValue('sk-\n123');
    const { buffer } = run({ name: 'v', ctrl: true }, '', { readClipboard });
    await Promise.resolve();
    await Promise.resolve();
    expect(readClipboard).toHaveBeenCalled();
    expect(buffer.calls).toEqual(['insert:sk-123']);
  });
});