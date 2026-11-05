import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KeypressProvider, type Key } from '../src/contexts/KeypressContext.js';
import { useKeypress } from '../src/hooks/useKeypress.js';
import { MainLayout, type MainLayoutProps } from '../src/components/layouts/MainLayout.js';
import { ShortcutTextInput } from '../src/components/Input/ShortcutTextInput.js';
import { AppProvider } from '../src/store/context.js';
import type { ClipboardContent } from '../src/utils/clipboard.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const fake = vi.hoisted(() => ({
  stdin: null as unknown as NodeJS.ReadStream,
  read: vi.fn(),
  copy: vi.fn(),
  discard: vi.fn(),
}));
vi.mock('../src/services/windowsConsole.js', () => ({
  getTerminalInput: () => fake.stdin,
  getNativeWindowsInput: () => null,
}));
vi.mock('../src/utils/clipboard.js', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/utils/clipboard.js')>();
  return {
    ...actual,
    readClipboardContent: fake.read,
    copySelectionToClipboard: fake.copy,
    discardClipboardContent: fake.discard,
  };
});
vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const wait = () => new Promise(resolve => setTimeout(resolve, 80));
beforeEach(() => {
  vi.resetAllMocks();
  fake.read.mockResolvedValue({ kind: 'text', text: 'right 中文\nsecond line' });
  fake.copy.mockResolvedValue('native');
  for (const name of ['SSH_TTY', 'SSH_CONNECTION', 'SSH_CLIENT']) vi.stubEnv(name, '');
  vi.stubEnv('TERM_PROGRAM', 'Apple_Terminal');
  vi.stubEnv('TERMINAL_EMULATOR', '');
});
afterEach(() => vi.unstubAllEnvs());

function harness(props: Partial<MainLayoutProps> = {}, standalone = false) {
  const rows = 30, columns = 80;
  const stdin = Object.assign(new PassThrough(), { isTTY: true, isRaw: true, setRawMode() {} });
  fake.stdin = stdin as unknown as NodeJS.ReadStream;
  const stdout = Object.assign(new PassThrough(), { isTTY: true, rows, columns });
  const screen = new TerminalScreen(rows, columns);
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  const submitted = vi.fn(), interrupted = vi.fn();
  const events: Key[] = [];
  let frame = '';
  function Observer() {
    useKeypress(key => events.push(key));
    return null;
  }
  const view = (options: Partial<MainLayoutProps>) =>
    <KeypressProvider><Observer /><AppProvider>
      {standalone ? <ShortcutTextInput onSubmit={submitted} /> :
        <MainLayout workingDir="." model="synthetic-model" isCollapsed
          messages={[{ id: 'answer', type: 'agent', content: 'History stays selectable.',
            author: 'Synthetic', timestamp: '', metadata: { subtype: 'answer' } }]}
          onSendMessage={submitted} onCtrlC={interrupted} {...options} />}
    </AppProvider></KeypressProvider>;
  const app = render(view(props), {
    stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  const send = (sequence: string) => stdin.write(sequence);
  const paste = (text: string) => send(`\x1b[200~${text}\x1b[201~`);
  const mouse = (button: number, x: number, y: number, release = false) =>
    send(`\x1b[<${button};${x};${y}${release ? 'm' : 'M'}`);
  const locate = (text: string) => {
    const lines = frame.split('\n');
    const row = lines.findLastIndex(line => line.includes(text));
    expect(row).toBeGreaterThanOrEqual(0);
    return { x: lines[row].indexOf(text) + 1, y: row + 1 };
  };
  const select = async (text: string) => {
    const { x, y } = locate(text);
    mouse(0, x, y);
    mouse(32, x + text.length, y);
    await wait();
    mouse(0, x + text.length, y, true);
    await wait();
    expect(app.getSelection().isCollapsed).toBe(false);
    return { x, y };
  };
  return {
    app, screen, send, paste, mouse, locate, select, submitted, interrupted, events,
    rerender: (options: Partial<MainLayoutProps>) => app.rerender(view({ ...props, ...options })),
    get frame() { return frame; },
    close() {
      app.unmount(); app.cleanup();
      expect(stdin.listenerCount('data')).toBe(0);
    },
  };
}

describe('right click through real key parsing, selection routing and Ink input', () => {
  it.each([false, true])('pastes text once without submitting, standalone=%s', async standalone => {
    const test = harness({}, standalone);
    try {
      await wait();
      test.mouse(2, 4, 2);
      test.mouse(2, 4, 2, true);
      await vi.waitFor(() => expect(test.frame).toContain(standalone ? 'right 中文second line' : 'second line'));
      expect(fake.read).toHaveBeenCalledOnce();
      expect(fake.read).toHaveBeenCalledWith(false);
      expect(test.submitted).not.toHaveBeenCalled();
      expect(fake.copy).not.toHaveBeenCalled();
      test.send('\r');
      await vi.waitFor(() => expect(test.submitted).toHaveBeenCalledWith(
        ...(standalone ? ['right 中文second line'] : ['right 中文\nsecond line', undefined]),
      ));
    } finally { test.close(); }
  });

  it.each(['history', 'draft'])('copies the %s selection before paste and retains it until confirmed', async surface => {
    fake.copy.mockResolvedValueOnce('failed').mockResolvedValueOnce('osc52').mockResolvedValueOnce('native');
    const test = harness();
    try {
      await wait();
      test.paste('Selected draft');
      await wait();
      const point = await test.select(surface === 'history' ? 'History' : 'Selected');
      const readingRows = () => test.frame.split('\n').filter(line => line.includes('History'));
      const before = readingRows();
      for (const remains of [true, false]) {
        test.mouse(2, point.x, point.y);
        await vi.waitFor(() => expect(fake.copy).toHaveBeenCalledTimes(remains ? 2 : 3));
        await wait();
        expect(test.events.at(-1)?.name).toBe('selectioncopy');
        expect(test.app.getSelection().isCollapsed).toBe(!remains);
        expect(readingRows()).toEqual(before);
        expect(test.frame).toContain('Selected draft');
        expect(fake.read).not.toHaveBeenCalled();
        expect(test.submitted).not.toHaveBeenCalled();
        expect(test.interrupted).not.toHaveBeenCalled();
      }
    } finally { test.close(); }
  });

  it('does not reinterpret a synchronously cleared selection as a paste', async () => {
    const test = harness();
    try {
      await wait();
      const point = await test.select('History');
      test.mouse(2, point.x, point.y);
      await vi.waitFor(() => expect(test.app.getSelection().isCollapsed).toBe(true));
      expect(fake.copy).toHaveBeenCalledTimes(1);
      expect(fake.read).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('does not copy a selection through another surface or activate right-clicked controls', async () => {
    const test = harness();
    try {
      await wait();
      test.paste('Selected draft');
      await wait();
      await test.select('Selected');
      fake.copy.mockClear();
      const point = test.locate('History');
      test.mouse(2, point.x, point.y);
      await wait();
      expect(fake.copy).not.toHaveBeenCalled();
      expect(fake.read).not.toHaveBeenCalled();
      expect(test.app.getSelection().isCollapsed).toBe(false);
    } finally { test.close(); }
  });

  it.each([6, 10, 18])('ignores modified right presses with SGR button %i', async button => {
    const test = harness();
    try {
      await wait();
      await test.select('History');
      fake.copy.mockClear();
      const point = test.locate('History');
      test.mouse(button, point.x, point.y);
      await wait();
      expect(fake.copy).not.toHaveBeenCalled();
      expect(fake.read).not.toHaveBeenCalled();
      expect(test.app.getSelection().isCollapsed).toBe(false);
    } finally { test.close(); }
  });

  it.each(['SSH_TTY', 'SSH_CONNECTION', 'SSH_CLIENT', 'TERM_PROGRAM'])(
    'accepts terminal paste without a host read when %s identifies a terminal-owned path', async name => {
      vi.stubEnv(name, name === 'TERM_PROGRAM' ? 'vscode' : 'synthetic');
      const test = harness();
      try {
        await wait();
        test.mouse(2, 4, 2);
        await wait();
        expect(fake.read).not.toHaveBeenCalled();
        test.paste('Client clipboard 中文');
        await vi.waitFor(() => expect(test.frame).toContain('Client clipboard 中文'));
        expect(test.submitted).not.toHaveBeenCalled();
      } finally { test.close(); }
    },
  );

  it.each(['input', 'terminal-paste', 'session', 'inactive', 'unmount'])(
    'discards delayed right-click text after %s', async change => {
      let resolve!: (content: ClipboardContent) => void;
      fake.read.mockReturnValue(new Promise<ClipboardContent>(done => { resolve = done; }));
      const test = harness({ sessionId: 'first' });
      let closed = false;
      try {
        await wait();
        test.mouse(2, 4, 2);
        await vi.waitFor(() => expect(fake.read).toHaveBeenCalledOnce());
        if (change === 'input') test.send('X');
        if (change === 'terminal-paste') test.paste('Client paste');
        if (change === 'session') test.rerender({ sessionId: 'second' });
        if (change === 'inactive') test.rerender({ isReady: false });
        if (change === 'unmount') { test.close(); closed = true; }
        await wait();
        const content: ClipboardContent = { kind: 'text', text: 'STALE_CLIPBOARD' };
        resolve(content);
        await vi.waitFor(() => expect(fake.discard).toHaveBeenCalledWith(content));
        expect(test.frame).not.toContain('STALE_CLIPBOARD');
        expect(test.submitted).not.toHaveBeenCalled();
        if (change === 'terminal-paste') expect(test.frame).toContain('Client paste');
      } finally { if (!closed) test.close(); }
    },
  );

  it('keeps one pending read through repeated right presses and hover', async () => {
    let resolve!: (content: ClipboardContent) => void;
    fake.read.mockReturnValue(new Promise<ClipboardContent>(done => { resolve = done; }));
    const test = harness();
    try {
      await wait();
      test.mouse(2, 4, 2);
      await vi.waitFor(() => expect(fake.read).toHaveBeenCalledOnce());
      test.mouse(35, 5, 2);
      test.mouse(2, 4, 2, true);
      test.mouse(2, 4, 2);
      resolve({ kind: 'text', text: 'ONCE' });
      await vi.waitFor(() => expect(test.frame).toContain('ONCE'));
      expect(fake.read).toHaveBeenCalledOnce();
      test.send('\r');
      await vi.waitFor(() => expect(test.submitted).toHaveBeenCalledWith('ONCE', undefined));
    } finally { test.close(); }
  });

  it('does not paste while the main input is disabled', async () => {
    const test = harness({ isReady: false });
    try {
      await wait();
      test.mouse(2, 4, 2);
      await wait();
      expect(fake.read).not.toHaveBeenCalled();
      expect(test.submitted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('does not paste while command suggestions cover the conversation', async () => {
    const test = harness();
    try {
      await wait();
      test.paste('/mo');
      await vi.waitFor(() => expect(test.frame).toContain('补全建议'));
      test.mouse(2, 4, 2);
      await wait();
      expect(fake.read).not.toHaveBeenCalled();
      expect(test.frame).toContain('/mo');
      expect(test.submitted).not.toHaveBeenCalled();
    } finally { test.close(); }
  });
});