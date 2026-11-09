import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { copySelectionToClipboard, selectionClipboardSequence } from '../src/utils/clipboard.js';
import { nativeClipboard } from '../src/utils/nativeClipboard.js';

vi.mock('../src/utils/nativeClipboard.js', () => ({
  nativeClipboard: { writeText: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  for (const key of ['SSH_TTY', 'SSH_CONNECTION', 'SSH_CLIENT', 'TERM_PROGRAM', 'TMUX', 'TMUX_PANE', 'STY']) {
    vi.stubEnv(key, '');
  }
  vi.stubEnv('TERM', 'xterm-256color');
});
afterEach(() => vi.unstubAllEnvs());
describe('selection clipboard transport', () => {
  it('encodes Unicode and escape characters as base64 and wraps multiplexers', () => {
    const text = '中文👩‍💻\x1b[2J';
    const raw = selectionClipboardSequence(text, {});
    expect(Buffer.from(raw.slice(7, -1), 'base64').toString()).toBe(text);
    expect(raw).not.toContain('\x1b[2J');
    expect(selectionClipboardSequence(text, { TMUX: 'test' })).toContain('\x1bPtmux;');
    expect(selectionClipboardSequence(text, { STY: 'test' })).toContain('\x1bP\x1b]52;');
  });
  it('does not spawn native clipboard helpers over SSH and reports OSC52 as sent', async () => {
    vi.stubEnv('SSH_CONNECTION', 'synthetic'); vi.stubEnv('TERM_PROGRAM', 'ghostty');
    const write = vi.fn();
    expect(await copySelectionToClipboard('selected', { isTTY: true, write } as any)).toBe('osc52');
    expect(write).toHaveBeenCalledOnce();
    expect(nativeClipboard.writeText).not.toHaveBeenCalled();
  });
  it.each(['', 'Unknown', 'Windows_Terminal', 'Apple_Terminal'])(
    'sends remote selections without a terminal allowlist (%s)', async program => {
      vi.stubEnv('SSH_CONNECTION', 'synthetic');
      vi.stubEnv('TERM_PROGRAM', program || undefined);
      const text = 'selected 中文\nsecond line';
      const write = vi.fn();
      expect(await copySelectionToClipboard(text, { isTTY: true, write } as any)).toBe('osc52');
      expect(write).toHaveBeenCalledOnce();
      expect(write).toHaveBeenCalledWith(
        `\x1b]52;c;${Buffer.from(text).toString('base64')}\x07`,
      );
      expect(nativeClipboard.writeText).not.toHaveBeenCalled();
    },
  );
  it.each(['SSH_TTY', 'SSH_CLIENT'])('uses OSC52 for %s-only sessions without terminal identity', async key => {
    vi.stubEnv(key, 'synthetic');
    const write = vi.fn();
    expect(await copySelectionToClipboard('selected', { isTTY: true, write } as any)).toBe('osc52');
    expect(write).toHaveBeenCalledOnce();
    expect(nativeClipboard.writeText).not.toHaveBeenCalled();
  });
  it('rejects cancelled, empty, oversized and non-interactive remote copies without output', async () => {
    vi.stubEnv('SSH_CONNECTION', 'synthetic');
    const write = vi.fn(), output = { isTTY: true, write } as any;
    for (const text of ['', '  ', 'a'.repeat(100001), '中'.repeat(33334)]) {
      expect(await copySelectionToClipboard(text, output)).toBe('failed');
    }
    expect(await copySelectionToClipboard('valid', output, AbortSignal.abort())).toBe('failed');
    expect(await copySelectionToClipboard('valid', undefined)).toBe('failed');
    expect(await copySelectionToClipboard('valid', { ...output, isTTY: false })).toBe('failed');
    vi.stubEnv('TERM', 'dumb');
    expect(await copySelectionToClipboard('valid', output)).toBe('failed');
    expect(write).not.toHaveBeenCalled();
  });
  it('reports failed output delivery instead of a sent request', async () => {
    vi.stubEnv('SSH_CONNECTION', 'synthetic');
    const write = vi.fn(() => { throw new Error('synthetic output failure'); });
    expect(await copySelectionToClipboard('selected', { isTTY: true, write } as any)).toBe('failed');
    expect(write).toHaveBeenCalledOnce();
  });
});