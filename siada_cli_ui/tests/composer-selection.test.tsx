import './helpers/chineseLocale.js';
import React from 'react';
import stringWidth from 'string-width';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { MainLayout, type MainLayoutProps } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { setActiveTheme } from '../src/themes/index.js';
import { githubTheme } from '../src/components/Input/theme.js';

const dimensions = { columns: 80, rows: 43 };
const handlers = new Set<(key: Key) => void>();
const clipboard = vi.hoisted(() => ({
  copy: vi.fn().mockResolvedValue('native'),
  read: vi.fn().mockResolvedValue({ kind: 'text', text: 'middle pasted' }),
}));
vi.mock('../src/utils/clipboard.js', () => ({
  copySelectionToClipboard: clipboard.copy,
  copyTextToClipboard: vi.fn(), getImageFromClipboard: vi.fn(), getTextFromClipboard: vi.fn(),
  readClipboardContent: clipboard.read,
  copyClipboardText: vi.fn(),
  discardClipboardContent: vi.fn(),
}));
vi.mock('../src/hooks/useTerminalSize.js', () => ({ useTerminalSize: () => dimensions }));
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void, options: { isActive?: boolean } = {}) => {
    React.useEffect(() => {
      if (options.isActive === false) return;
      handlers.add(handler);
      return () => { handlers.delete(handler); };
    }, [handler, options.isActive]);
  }};
});
const pause = () => new Promise(resolve => setTimeout(resolve, 70));

function harness(rows = 43, columns = 80, props: Partial<MainLayoutProps> = {}) {
  dimensions.rows = rows; dimensions.columns = columns;
  const stdout = Object.assign(new PassThrough(), { rows, columns });
  const screen = new TerminalScreen(rows, columns);
  const submitted = vi.fn(), interrupted = vi.fn();
  let frame = '', raw = '';
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  const app = render(<AppProvider><MainLayout workingDir="." model="synthetic-model" isCollapsed
    messages={[{ id: 'answer', type: 'agent', content: 'History text stays selectable.', author: 'Synthetic',
      timestamp: '', metadata: { subtype: 'answer' } }]}
    onSendMessage={submitted} onCtrlC={interrupted}
    todoItems={[{ content: 'Task below input', status: 'in_progress' }]}
    subAgentItems={[{ id: 'agent', title: 'Agent below input', status: 'running' }]}
    {...props}
  /></AppProvider>, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { raw = output; frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  const key = (name: string, extra: Partial<Key> = {}) => {
    // Match the real provider's copy routing before invoking subscribers.
    if (!app.getSelection().isCollapsed) {
      if ((extra.ctrl || extra.cmd) && name === 'c') name = 'selectioncopy';
      if (name === 'escape') name = 'selectionclear';
    }
    const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false,
      insertable: false, sequence: '', ...extra };
    [...handlers].forEach(handler => handler(event));
  };
  const mouse = (name: string, x: number, y: number) => key(name, {
    sequence: `\x1b[<${name === 'mousemove' ? 32 : name === 'mousemiddle' ? 1 : 0};${x};${y}${name === 'mouserelease' ? 'm' : 'M'}`,
  });
  const locate = (text: string) => {
    const lines = frame.split('\n');
    const y = lines.findLastIndex(line => line.includes(text));
    expect(y).toBeGreaterThanOrEqual(0);
    return { x: lines[y].indexOf(text) + 1, y: y + 1 };
  };
  const drag = async (text: string, columns: number, reverse = false) => {
    const { x, y } = locate(text);
    mouse('mouseclick', reverse ? x + columns : x, y);
    mouse('mousemove', reverse ? x : x + columns, y);
    await pause();
    expect(app.getSelection().isCollapsed).toBe(false);
    mouse('mouserelease', reverse ? x : x + columns, y);
    await pause();
  };
  return { app, screen, key, mouse, locate, drag, submitted, interrupted,
    get frame() { return frame; },
    get raw() { return raw; },
    close() { app.unmount(); app.cleanup(); },
  };
}

describe('composer and bottom text selection', () => {
  it.each(['up', 'down'])('keeps completion selection unchanged on Ctrl+%s', async direction => {
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: '/mo', insertable: true });
      await vi.waitFor(() => expect(test.frame).toContain('补全建议'));
      const suggestions = () => test.frame.split('\n').filter(line =>
        line.includes('model') || line.includes('memory'));
      const before = suggestions();
      expect(before.length).toBeGreaterThan(0);
      test.key(direction, { ctrl: true }); await pause();
      expect(suggestions()).toEqual(before);
      test.key('return'); await pause();
      expect(test.frame).toContain('/model');
      expect(test.submitted).not.toHaveBeenCalled();
      test.key('return'); await pause();
      expect(test.submitted).toHaveBeenCalledWith('/model', undefined);
    } finally { test.close(); }
  });

  it('scrolls history with Ctrl+arrows without moving the multiline draft cursor', async () => {
    const test = harness(24, 80, {
      messages: [{ id: 'long-answer', type: 'agent',
        content: Array.from({ length: 100 }, (_, i) => `KEYBOARD_HISTORY_${i}`).join('\n'),
        author: 'Synthetic', timestamp: '', metadata: { subtype: 'answer' } }],
    });
    try {
      await pause();
      test.key('paste', { sequence: 'first line\nlast line', insertable: true }); await pause();
      test.key('up', { ctrl: true }); await pause();
      expect(test.frame).toContain('回到底部');
      test.key('X', { sequence: 'X', insertable: true }); await pause();
      expect(test.frame).toContain('last lineX');
      test.key('a', { ctrl: true }); await pause();
      test.key('down', { ctrl: true }); await pause();
      test.key('Y', { sequence: 'Y', insertable: true }); await pause();
      expect(test.frame).toContain('Ylast lineX');
      test.key('return'); await pause();
      expect(test.submitted).toHaveBeenCalledWith('first line\nYlast lineX', undefined);
    } finally { test.close(); }
  });

  it.each([
    ['dark', false], ['dark', true], ['light', false], ['light', true],
  ] as const)('distinguishes placeholder from typed text in %s theme, presentation=%s', async (theme, demoPresentation) => {
    const originalLevel = chalk.level;
    chalk.level = 3;
    setActiveTheme(theme);
    const test = harness(43, 100, { demoPresentation });
    try {
      await pause();
      const placeholderLine = test.raw.split('\n').find(line => line.includes('输入消息'));
      expect(placeholderLine).toContain(chalk.hex(githubTheme.input.placeholder)('输入消息').split('输入消息')[0]);
      expect(githubTheme.input.placeholder).not.toBe(githubTheme.input.text);
      test.key('paste', { sequence: 'Synthetic draft', insertable: true });
      await pause();
      expect(test.frame).not.toContain('输入消息');
      const draftLine = test.raw.split('\n').find(line => line.includes('Synthetic draft'));
      expect(draftLine).toContain(chalk.hex(githubTheme.input.text)('Synthetic draft').split('Synthetic draft')[0]);
    } finally {
      test.close();
      chalk.level = originalLevel;
      setActiveTheme('dark');
    }
  });

  it('keeps VT replay moving past Kitty keyboard push and pop sequences', () => {
    const screen = new TerminalScreen(3, 20);
    screen.feed('\x1b[>1');
    screen.feed('uReady\n\x1b[<uRestored');
    expect(screen.display()).toContain('Ready\nRestored');
  });
  it.each([false, true])('selects Chinese draft text without changing the draft, reverse=%s', async reverse => {
    clipboard.copy.mockClear();
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: 'alpha 中文 beta', insertable: true }); await pause();
      await test.drag('中文', 4, reverse);
      expect(clipboard.copy).toHaveBeenCalledOnce();
      expect(clipboard.copy.mock.calls[0][0]).toBe('中文');
      test.key('c', { ctrl: true }); await pause();
      expect(test.interrupted).not.toHaveBeenCalled();
      expect(test.frame).toContain('alpha 中文 beta');
      test.key('return'); await pause();
      expect(test.submitted).toHaveBeenCalledWith('alpha 中文 beta', undefined);
    } finally { test.close(); }
  });

  it.each(['synthetic-model', 'Task below input', 'Agent below input'])('copies %s below input', async text => {
    clipboard.copy.mockClear();
    const test = harness();
    try {
      await pause();
      await test.drag(text, text.length);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe(text);
      test.key('c', { cmd: true }); await pause();
      expect(test.interrupted).not.toHaveBeenCalled();
      expect(test.frame).toContain('输入消息');
    } finally { test.close(); }
  });

  it('copies wrapped draft text using its logical newlines and excluding the cursor', async () => {
    clipboard.copy.mockClear();
    const text = `BEGIN-${'abcdefghij'.repeat(5)}\n第二行。`;
    const test = harness(43, 40);
    try {
      await pause();
      test.key('paste', { sequence: text, insertable: true }); await pause();
      const first = test.locate('BEGIN-'), last = test.locate('第二行。');
      test.mouse('mouseclick', first.x, first.y);
      test.mouse('mousemove', last.x + 8, last.y); await pause();
      test.mouse('mouserelease', last.x + 8, last.y); await pause();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe(text);
      expect(test.frame).toContain('第二行。');
    } finally { test.close(); }
  });

  it('double-clicks a word and triple-clicks the logical draft line', async () => {
    clipboard.copy.mockClear();
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: 'alpha beta gamma', insertable: true }); await pause();
      const { x, y } = test.locate('beta');
      for (let i = 0; i < 3; i++) {
        test.mouse('mouseclick', x + 1, y); test.mouse('mouserelease', x + 1, y); await pause();
        if (i === 0) expect(clipboard.copy).not.toHaveBeenCalled();
        if (i === 1) expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('beta');
        if (i === 2) expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('alpha beta gamma');
      }
    } finally { test.close(); }
  });

  it.each([false, true])('keeps history copying available after selecting a draft, presentation=%s', async demoPresentation => {
    clipboard.copy.mockClear();
    const test = harness(43, 80, { demoPresentation });
    try {
      await pause();
      test.key('paste', { sequence: 'Draft', insertable: true }); await pause();
      await test.drag('Draft', 5);
      await test.drag('History text', 12);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('History text');
      test.key('escape'); await pause();
      expect(test.frame).toContain('Draft');
      expect(test.app.getSelection().isCollapsed).toBe(true);
    } finally { test.close(); }
  });

  it.each([false, true])('returns mouse selection to messages while waiting for interactive input, presentation=%s', async demoPresentation => {
    clipboard.copy.mockClear();
    const test = harness(43, 80, { demoPresentation, interactiveInput: {
      prompt: 'Synthetic confirmation', inputType: 'confirmation', isPassword: false,
    } });
    try {
      await pause();
      test.key('paste', { sequence: 'Draft confirmation', insertable: true }); await pause();
      await test.drag('Draft', 5);
      await test.drag('History text', 12);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('History text');
      expect(test.frame).toContain('Draft confirmation');
      test.key('X', { sequence: 'X', insertable: true }); await pause();
      expect(test.app.getSelection().isCollapsed).toBe(true);
      expect(test.submitted).not.toHaveBeenCalled();
      test.key('return'); await pause();
      expect(test.submitted).toHaveBeenCalledWith('Draft confirmationX', undefined);
    } finally { test.close(); }
  });

  it('selects visible messages while command suggestions are open', async () => {
    clipboard.copy.mockClear();
    const test = harness(43, 80, { demoPresentation: true });
    try {
      await pause();
      test.key('paste', { sequence: '/mo', insertable: true });
      await vi.waitFor(() => expect(test.frame).toContain('命令建议'));
      await test.drag('/mo', 3);
      await test.drag('History text', 12);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('History text');
      expect(test.frame).toContain('命令建议');
      expect(test.submitted).not.toHaveBeenCalled();
      test.key('escape'); await pause();
      test.key('return'); await pause();
      expect(test.frame).toContain('/model');
      expect(test.submitted).not.toHaveBeenCalled();
      test.key('return'); await pause();
      expect(test.submitted).toHaveBeenCalledWith('/model', undefined);
    } finally { test.close(); }
  });

  it.each([false, true])('scrolls messages with the mouse while confirmation owns the keyboard, presentation=%s', async demoPresentation => {
    const content = Array.from({ length: 60 }, (_, index) => `History line ${index + 1}.`).join('\n');
    const test = harness(43, 80, { demoPresentation, interactiveInput: {
      prompt: 'Synthetic confirmation', inputType: 'confirmation', isPassword: false,
    }, messages: [{ id: 'answer', type: 'agent', content, author: 'Synthetic',
      timestamp: '', metadata: { subtype: 'answer' } }] });
    try {
      await pause();
      test.key('paste', { sequence: 'Pending confirmation', insertable: true }); await pause();
      const visibleLines = () => test.frame.split('\n').filter(line => line.includes('History line'));
      const before = visibleLines();
      expect(before.length).toBeGreaterThan(0);
      test.key('g', { ctrl: true }); test.key('pageup'); await pause();
      expect(visibleLines()).toEqual(before);
      const point = test.locate('History line');
      const atBottom = before.at(-1)?.includes('History line 60.');
      test.key(atBottom ? 'wheelup' : 'wheeldown', {
        sequence: `\x1b[<${atBottom ? 64 : 65};${point.x};${point.y}M`,
      }); await pause();
      expect(visibleLines()).not.toEqual(before);
      expect(test.frame).toContain('Pending confirmation');
      expect(test.submitted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('does not select or scroll messages through the command popup', async () => {
    clipboard.copy.mockClear();
    const content = Array.from({ length: 60 }, (_, index) => `History line ${index + 1}.`).join('\n');
    const test = harness(43, 80, { demoPresentation: true,
      messages: [{ id: 'answer', type: 'agent', content, author: 'Synthetic',
        timestamp: '', metadata: { subtype: 'answer' } }] });
    try {
      await pause();
      test.key('paste', { sequence: '/mo', insertable: true });
      await vi.waitFor(() => expect(test.frame).toContain('命令建议'));
      const firstLine = test.frame.split('\n').find(line => line.includes('History line'));
      const point = test.locate('命令建议');
      test.mouse('mouseclick', point.x, point.y);
      test.mouse('mousemove', point.x + 8, point.y); await pause();
      test.mouse('mouserelease', point.x + 8, point.y); await pause();
      expect(test.app.getSelection().isCollapsed).toBe(true);
      expect(clipboard.copy).not.toHaveBeenCalled();
      test.key('wheelup', { sequence: `\x1b[<64;${point.x};${point.y}M` }); await pause();
      expect(test.frame.split('\n').find(line => line.includes('History line'))).toBe(firstLine);
      expect(test.frame).toContain('命令建议');
      expect(test.submitted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('does not start a selection on the input placeholder or borders', async () => {
    clipboard.copy.mockClear();
    const test = harness();
    try {
      await pause();
      const placeholder = test.locate('输入消息');
      for (const y of [placeholder.y - 1, placeholder.y, placeholder.y + 1]) {
        test.mouse('mouseclick', placeholder.x, y);
        test.mouse('mousemove', placeholder.x + 9, y); await pause();
        test.mouse('mouserelease', placeholder.x + 9, y); await pause();
        expect(test.app.getSelection().isCollapsed).toBe(true);
        expect(clipboard.copy).not.toHaveBeenCalled();
      }
    } finally { test.close(); }
  });

  it('copies while the cursor is inside the draft and keeps its insertion position', async () => {
    clipboard.copy.mockClear();
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: 'alpha beta', insertable: true }); await pause();
      test.key('a', { ctrl: true });
      test.key('right'); test.key('right'); await pause();
      await test.drag('alpha', 5);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('alpha');
      test.key('c', { ctrl: true }); await pause();
      test.key('X', { sequence: 'X', insertable: true }); await pause();
      test.key('return'); await pause();
      expect(test.submitted).toHaveBeenCalledWith('alXpha beta', undefined);
      expect(test.interrupted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('retains the draft selection after a failed copy and retries on Ctrl+C', async () => {
    clipboard.copy.mockClear();
    clipboard.copy.mockResolvedValueOnce('failed');
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: 'Keep this draft', insertable: true }); await pause();
      await test.drag('Keep', 4);
      expect(test.frame).toContain('复制失败');
      expect(test.app.getSelection().isCollapsed).toBe(false);
      test.key('c', { ctrl: true }); await pause();
      expect(clipboard.copy).toHaveBeenCalledTimes(2);
      expect(test.app.getSelection().isCollapsed).toBe(true);
      expect(test.interrupted).not.toHaveBeenCalled();
      expect(test.frame).toContain('Keep this draft');
    } finally { test.close(); }
  });

  it.each(['draft', 'history', 'bottom'])('pastes without copying the %s selection on middle press', async surface => {
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: '中文 draft', insertable: true });
      await pause();
      const selected = surface === 'draft' ? '中文' : surface === 'history' ? 'History text' : 'Task below input';
      await test.drag(selected, stringWidth(selected));
      clipboard.copy.mockClear();
      clipboard.read.mockClear();
      const point = test.locate(selected);
      test.mouse('mousemiddle', point.x, point.y);
      await pause();
      expect(clipboard.copy).not.toHaveBeenCalled();
      expect(clipboard.read).toHaveBeenCalledWith(true);
      expect(test.frame).toContain('中文 draftmiddle pasted');
      expect(test.submitted).not.toHaveBeenCalled();
      expect(test.interrupted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('pastes on middle click without requiring a selection', async () => {
    const test = harness();
    try {
      await pause();
      clipboard.copy.mockClear();
      clipboard.read.mockClear();
      const point = test.locate('History text');
      test.mouse('mousemiddle', point.x, point.y);
      await pause();
      expect(clipboard.copy).not.toHaveBeenCalled();
      expect(clipboard.read).toHaveBeenCalledWith(true);
      expect(test.frame).toContain('middle pasted');
      expect(test.submitted).not.toHaveBeenCalled();
      expect(test.interrupted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('ignores modified middle clicks and keeps the selected draft', async () => {
    const test = harness();
    try {
      await pause();
      test.key('paste', { sequence: 'selected draft', insertable: true });
      await pause();
      await test.drag('selected', 8);
      clipboard.copy.mockClear();
      test.key('mousemiddle', { ctrl: true, sequence: '\x1b[<17;1;1M' });
      await pause();
      expect(clipboard.copy).not.toHaveBeenCalled();
      expect(test.app.getSelection().isCollapsed).toBe(false);
      expect(test.frame).toContain('selected draft');
    } finally { test.close(); }
  });

  it.each([20, 24, 43])('copies the bottom task within the rendered frame at %i rows', async rows => {
    clipboard.copy.mockClear();
    const test = harness(rows, 48);
    try {
      await pause();
      await test.drag('Task below input', 16);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('Task below input');
      expect(test.frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
      expect(test.screen.display()).toContain('输入消息');
      test.key('escape'); await pause();
      expect(test.app.getSelection().isCollapsed).toBe(true);
    } finally { test.close(); }
  });
});