import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { Command } from 'commander';
import { NoAltScreenContext } from '../src/contexts/TerminalModeContext.js';
import { useMouseTracking, hasMouseTracking } from '../src/hooks/useMouseTracking.js';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { resolveTerminalMode } from '../src/utils/terminalMode.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import type { Message } from '../src/types/index.js';
import type { Key } from '../src/hooks/useKeypress.js';

const handlers = vi.hoisted(() => new Set<(key: Key) => void>());
const subscribe = (handler: (key: Key) => void) => handlers.add(handler);
const unsubscribe = (handler: (key: Key) => void) => handlers.delete(handler);
vi.mock('../src/contexts/KeypressContext.js', async importOriginal => ({
  ...await importOriginal<typeof import('../src/contexts/KeypressContext.js')>(),
  useKeypressContext: () => ({ subscribe, unsubscribe }),
}));

const pause = () => new Promise(resolve => setTimeout(resolve, 100));
const message = (id: string, content: string, type: Message['type'] = 'agent'): Message => ({
  id, content, type, author: 'Synthetic', timestamp: '2026-01-01T00:00:00Z',
  metadata: type === 'agent' ? { subtype: 'answer', streamEnd: true } : undefined,
});
const banner = { version: 'synthetic', workingDir: '.', agent: 'coder', provider: 'synthetic', model: 'synthetic' };
function Owner() { useMouseTracking(); return null; }
function key(name: string, extra: Partial<Key> = {}) {
  const event: Key = { name, sequence: '', insertable: false,
    ctrl: false, alt: false, cmd: false, shift: false, ...extra };
  [...handlers].forEach(handler => handler(event));
}

function terminal(rows = 40, columns = 80) {
  const stdout = Object.assign(new PassThrough(), { rows, columns, isTTY: true });
  const stdin = Object.assign(new PassThrough(), { isTTY: true, setRawMode() {}, ref() {}, unref() {} });
  const screen = new TerminalScreen(rows, columns);
  const writes: string[] = [];
  stdout.on('data', chunk => { writes.push(chunk.toString()); screen.feed(chunk.toString()); });
  return { stdout, stdin, screen, writes };
}

describe('no-alt-screen uses native scrollback', () => {
  it('resolves the flag without changing the legacy buffer option', () => {
    const options = new Command().option('--alternate-buffer').option('--no-alternate-buffer')
      .option('--no-alt-screen').parse(['--no-alt-screen', '--alternate-buffer'], { from: 'user' }).opts();
    expect(resolveTerminalMode(options)).toEqual({ noAltScreen: true, alternateBuffer: false });
    expect(resolveTerminalMode({})).toEqual({ noAltScreen: false, alternateBuffer: true });
    expect(resolveTerminalMode({ alternateBuffer: false })).toEqual({ noAltScreen: false, alternateBuffer: false });
  });

  it('vetoes nested mouse ownership, including a newly mounted overlay', async () => {
    const test = terminal();
    const view = (overlay: boolean) => <NoAltScreenContext.Provider value={true}>
      <Box><Owner />{overlay && <Owner />}</Box>
    </NoAltScreenContext.Provider>;
    const app = render(view(false), { stdout: test.stdout, stdin: test.stdin,
      patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await pause();
      app.rerender(view(true)); await pause();
      expect(hasMouseTracking(test.stdout)).toBe(false);
      expect(test.writes.join('')).not.toMatch(/\x1b\[\?(?:1000|1002|1003|1006|1007|1049)h/);
    } finally { app.unmount(); app.cleanup(); }
  });

  const messages = [
    message('first-user', 'FIRST QUESTION', 'user'),
    message('long-answer', Array.from({ length: 100 }, (_, index) => `FIRST_LINE_${String(index + 1).padStart(3, '0')}`).join('\n')),
    message('last-user', 'LAST QUESTION', 'user'),
    message('last-answer', 'LATEST ANSWER\n```ts\nconst normalViewport = true;\n```'),
  ];

  it.each([24, 40])('prints completed content into real terminal history at %i rows', async rows => {
      const test = terminal(rows);
      const app = render(<NoAltScreenContext.Provider value={true}>
        <AppProvider><MainLayout {...banner} messages={messages}
          demoPresentation fullStatusBar bannerInHistory onSendMessage={() => {}} /></AppProvider>
      </NoAltScreenContext.Provider>, {
        stdout: test.stdout, stdin: test.stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      });
      try {
        await pause();
        for (let i = 1; i <= 100; i++) {
          const marker = `FIRST_LINE_${String(i).padStart(3, '0')}`;
          expect(test.screen.transcript()).toContain(marker);
          expect(test.screen.transcript().split(marker).length - 1).toBe(1);
        }
        expect(test.screen.history()).toContain('FIRST_LINE_001');
        expect(test.screen.transcript()).toContain('LATEST ANSWER');
        expect(test.screen.transcript()).toContain('normalViewport');
        expect(test.screen.display()).toContain('输入消息');
        expect(hasMouseTracking(test.stdout)).toBe(false);
        expect(test.writes.join('')).not.toMatch(/\x1b\[(?:2|3)J|\x1bc/);
      } finally { app.unmount(); app.cleanup(); }
  });

  it('preserves native history, the draft and overlays without reprinting old messages', async () => {
    const test = terminal();
    let frame = '';
    const send = vi.fn();
    const view = (overlay = false) => <NoAltScreenContext.Provider value={true}>
      <AppProvider><MainLayout {...banner} messages={messages}
        demoPresentation fullStatusBar bannerInHistory onSendMessage={send}
        demoOverlay={overlay ? <Text>KEYBOARD PICKER</Text> : undefined}
        demoOverlayHeight={12} /></AppProvider>
    </NoAltScreenContext.Provider>;
    const app = render(view(), {
      stdout: test.stdout, stdin: test.stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await pause();
      key('paste', { sequence: 'DRAFT_MARKER', insertable: true }); await pause();
      expect(frame).toContain('DRAFT_MARKER');
      const history = test.screen.history();
      expect(history).toContain('FIRST_LINE_001');
      app.rerender(view(true)); await pause();
      expect(frame).toContain('KEYBOARD PICKER');
      app.rerender(view()); await pause();
      expect(frame).toContain('DRAFT_MARKER');
      expect(test.screen.history().startsWith(history)).toBe(true);
      const unchanged = frame;
      key('wheelup', { sequence: '\x1b[<64;3;3M' });
      key('mouseclick', { sequence: '\x1b[<0;3;3M' });
      await pause();
      expect(frame).toBe(unchanged);
      expect(hasMouseTracking(test.stdout)).toBe(false);
      expect(test.writes.join('')).not.toMatch(/\x1b\[\?(?:1000|1002|1003|1006|1049)h/);
      key('return'); await pause();
      expect(send).toHaveBeenCalledWith('DRAFT_MARKER', undefined);
    } finally { app.unmount(); app.cleanup(); }
  });

  it('retains stable lines during generation, completion and resize', async () => {
    const test = terminal(24);
    const content = Array.from({ length: 100 }, (_, i) => `STREAM_LINE_${String(i).padStart(3, '0')}\n`).join('');
    const view = (complete = false) => <NoAltScreenContext.Provider value={true}>
      <AppProvider><MainLayout {...banner}
        messages={[{ ...message('stream', content), metadata: {
          subtype: 'answer', streamEnd: complete, isStreaming: !complete,
        } }]} loading={!complete} onSendMessage={() => {}} /></AppProvider>
    </NoAltScreenContext.Provider>;
    const app = render(view(), { stdout: test.stdout, stdin: test.stdin,
      patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await pause();
      expect(test.screen.history()).toContain('STREAM_LINE_000');
      expect(test.screen.display()).toContain('STREAM_LINE_099');
      app.rerender(view(true)); await pause();
      test.stdout.columns = 72;
      test.stdout.emit('resize');
      await pause();
      for (let i = 0; i < 100; i++) {
        const marker = `STREAM_LINE_${String(i).padStart(3, '0')}`;
        expect(test.screen.transcript().split(marker).length - 1).toBe(1);
      }
      expect(test.screen.display()).toContain('输入消息');
      expect(test.writes.join('')).not.toMatch(/\x1b\[(?:2|3)J|\x1bc/);
    } finally { app.unmount(); app.cleanup(); }
  });

  it('prints the ready Banner once and retains history through a readiness transition', async () => {
    const test = terminal(24);
    const view = (ready: boolean) => <NoAltScreenContext.Provider value={true}>
      <AppProvider><MainLayout {...banner} version={ready ? 'READY_VERSION' : 'BOOT_VERSION'}
        isReady={ready} messages={messages} onSendMessage={() => {}} /></AppProvider>
    </NoAltScreenContext.Provider>;
    const app = render(view(false), { stdout: test.stdout, stdin: test.stdin,
      patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await pause();
      expect(test.screen.transcript()).not.toContain('BOOT_VERSION');
      app.rerender(view(true)); await pause();
      expect(test.screen.transcript()).toContain('READY_VERSION');
      app.rerender(view(false)); await pause();
      app.rerender(view(true)); await pause();
      expect(test.screen.transcript().split('FIRST_LINE_001').length - 1).toBe(1);
      expect(test.screen.transcript().split('READY_VERSION').length - 1).toBe(1);
    } finally { app.unmount(); app.cleanup(); }
  });

  it('prints every line of a long Chinese code block into native history', async () => {
    const test = terminal(24, 48);
    const content = '```ts\n' + Array.from({ length: 100 }, (_, i) =>
      `const CODE_${String(i).padStart(3, '0')} = '中文';`).join('\n') + '\n```';
    const app = render(<NoAltScreenContext.Provider value={true}>
      <AppProvider><MainLayout {...banner} messages={[message('code', content)]}
        onSendMessage={() => {}} /></AppProvider>
    </NoAltScreenContext.Provider>, { stdout: test.stdout, stdin: test.stdin,
      patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await pause();
      expect(test.screen.history()).toContain('CODE_000');
      for (let i = 0; i < 100; i++) {
        expect(test.screen.transcript().split(`CODE_${String(i).padStart(3, '0')}`).length - 1).toBe(1);
      }
      expect(test.screen.display()).toContain('输入消息');
    } finally { app.unmount(); app.cleanup(); }
  });

  it('keeps the prompt visible when a picker closes above the agent management bar', async () => {
    const test = terminal(24);
    const view = (picker: boolean) => <NoAltScreenContext.Provider value={true}>
      <AppProvider><MainLayout {...banner} messages={messages} demoPresentation
        subAgentItems={[{ id: 'agent', title: 'Wire verifier', status: 'completed' }]}
        demoOverlay={picker ? <Text>MODEL PICKER</Text> : undefined} demoOverlayHeight={12}
        onSendMessage={() => {}} /></AppProvider>
    </NoAltScreenContext.Provider>;
    const app = render(view(false), { stdout: test.stdout, stdin: test.stdin,
      patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await pause();
      expect(test.screen.display()).toContain('输入消息');
      app.rerender(view(true)); await pause();
      expect(test.screen.display()).toContain('MODEL PICKER');
      app.rerender(view(false)); await pause();
      expect(test.screen.display()).toContain('输入消息');
      expect(test.screen.display()).toContain('Wire verifier');
      expect(test.screen.transcript().split('FIRST_LINE_001').length - 1).toBe(1);
    } finally { app.unmount(); app.cleanup(); }
  });
});