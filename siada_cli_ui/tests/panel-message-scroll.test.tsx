import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { SideQuestionPanel } from '../src/components/SideQuestion/SideQuestionPanel.js';
import { AppProvider } from '../src/store/context.js';
import { createInitialDemoState } from '../examples/three-pane-demo-data.mjs';
import { TerminalScreen } from './helpers/terminalScreen.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { createKeypressProcessor, emitKeys } from '../src/contexts/KeypressContext.js';

const dimensions = { rows: 24, columns: 80 };
vi.mock('../src/hooks/useTerminalSize.js', () => ({ useTerminalSize: () => dimensions }));
const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void, options = {}) => {
    React.useEffect(() => {
      if (options.isActive === false) return;
      handlers.add(handler);
      return () => { handlers.delete(handler); };
    }, [handler, options.isActive]);
  }};
});
const wait = () => new Promise(resolve => setTimeout(resolve, 90));
const emit = async (name: string, sequence = '') => {
  [...handlers].forEach(handler => handler({
    name, sequence, ctrl: false, cmd: false, alt: false, shift: false, insertable: false,
  }));
  await wait();
};
const history = Array.from({ length: 120 }, (_, i) => `HISTORY-${String(i).padStart(3, '0')}`).join('\n');
const answer = 'SIDE-START\n\n' + '同步异步事件循环'.repeat(100) +
  '\n\n```python\n' + Array.from({ length: 35 }, (_, i) => `print("CODE-${i}")`).join('\n') +
  '\n```\n\nSIDE-END';

describe('scroll routing while a bottom panel owns the keyboard', () => {
  it.each([20, 24, 43])('keeps the multiline composer fixed during raw wheel input at %i rows', async rows => {
    dimensions.rows = rows; dimensions.columns = 80;
    const state = createInitialDemoState();
    state.messages = [{ id: 'history', type: 'agent', content: history, timestamp: '', author: 'Agent' }];
    const stdout = Object.assign(new PassThrough(), dimensions);
    let frame = '';
    const app = render(<AppProvider><MainLayout {...state} demoPresentation workingDir="."
      onSendMessage={() => {}} /></AppProvider>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false,
      maxFps: 0, onRender: ({ output }) => { frame = output; },
    });
    const parser = emitKeys(createKeypressProcessor(key => [...handlers].forEach(handler => handler(key))));
    parser.next();
    const feed = async (text: string) => {
      for (const character of text) parser.next(character);
      await wait();
    };
    try {
      await wait();
      await feed('\x1b[200~DRAFT-A\nDRAFT-B\nDRAFT-C\x1b[201~');
      const lines = frame.split('\n');
      const inputRow = lines.findIndex(line => line.includes('DRAFT-A'));
      expect(inputRow).toBeGreaterThan(0);
      const composer = lines.slice(inputRow - 1).join('\n');
      const historyBefore = lines.filter(line => line.includes('HISTORY-')).join('\n');
      await feed('\x1b[<64;3;2M\x1b[<64;3;2M\x1b[<64;3;2M');
      expect(frame.split('\n').filter(line => line.includes('HISTORY-')).join('\n')).not.toBe(historyBefore);
      expect(frame.split('\n').findIndex(line => line.includes('DRAFT-A'))).toBe(inputRow);
      expect(frame.split('\n').slice(inputRow - 1).join('\n')).toBe(composer);
      const beforeComposerWheel = frame;
      await feed(`\x1b[<65;3;${inputRow + 1}M`);
      expect(frame).toBe(beforeComposerWheel);
    } finally { app.unmount(); app.cleanup(); }
  });
  it.each([20, 43])('clips a full Mermaid diagram and preserves the footer at %i rows', async rows => {
    dimensions.rows = rows; dimensions.columns = 80;
    const diagram = '```mermaid\nsequenceDiagram\nparticipant A as Main thread\nparticipant B as Event loop\n' +
      Array.from({ length: 6 }, (_, i) => `A->>B: Request ${i}\nB-->>A: Result ${i}`).join('\n') + '\n```\nDIAGRAM-END';
    const stdout = Object.assign(new PassThrough(), dimensions);
    const screen = new TerminalScreen(rows, 80);
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    let frame = '';
    const app = render(<SideQuestionPanel height={10}
      items={[{ id: 'old', question: 'OLD QUESTION\n'.repeat(20), answer: 'old' },
        { id: 'new', question: 'DIAGRAM QUESTION', answer: diagram }]}
      onHide={() => {}} onRemove={() => {}} />,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output; } });
    try {
      await wait();
      expect(frame.split('\n').length).toBeLessThanOrEqual(10);
      expect(screen.display()).toContain('DIAGRAM QUESTION');
      expect(screen.display()).toContain('OLD QUESTION');
      for (let i = 0; i < 40 && !screen.display().includes('DIAGRAM-END'); i++) await emit('pagedown');
      expect(screen.display()).toContain('DIAGRAM-END');
      expect(screen.display()).toContain('DIAGRAM QUESTION');
      expect(screen.display()).toContain('Esc close');
      expect(frame.split('\n').length).toBeLessThanOrEqual(10);
    } finally { app.unmount(); app.cleanup(); }
  });
  it.each([20, 24, 43])('bounds long btw answers and scrolls each region separately at %i rows', async rows => {
    dimensions.rows = rows;
    dimensions.columns = rows === 43 ? 100 : 48;
    const state = createInitialDemoState();
    state.messages = [{ id: 'long-history', type: 'agent', content: history, timestamp: '', author: 'Agent' }];
    const stdout = Object.assign(new PassThrough(), dimensions);
    const screen = new TerminalScreen(rows, dimensions.columns);
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    let frame = '';
    const view = sideQuestions => <AppProvider><MainLayout {...state} demoPresentation
      sideQuestions={sideQuestions} sideQuestionPanelVisible={sideQuestions.length > 0}
      workingDir="." onSendMessage={() => {}} /></AppProvider>;
    const app = render(view([]), { stdout, stdin: new PassThrough(), patchConsole: false,
      exitOnCtrlC: false, maxFps: 0, onRender: ({ output }) => { frame = output; } });
    try {
      await wait();
      app.rerender(view([{ id: 'side', question: 'SIDE-QUESTION\n第二行', answer }]));
      await wait();
      expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
      expect(screen.display()).toContain('SIDE-QUESTION');
      expect(screen.display()).toContain('SIDE-START');
      expect(screen.display()).toContain('side panel is active');
      const lines = screen.display().split('\n');
      const sideRow = lines.findIndex(line => line.includes('SIDE-START'));
      const historyBefore = lines.filter(line => line.includes('HISTORY-')).join('\n');
      await emit('wheelup', '\x1b[<64;3;2M');
      const historyAfter = screen.display().split('\n').filter(line => line.includes('HISTORY-')).join('\n');
      expect(historyAfter).not.toBe(historyBefore);
      expect(screen.display()).toContain('SIDE-START');
      await emit('wheeldown', `\x1b[<65;3;${sideRow + 1}M`);
      expect(screen.display()).not.toContain('SIDE-START');
      expect(screen.display().split('\n').filter(line => line.includes('HISTORY-')).join('\n')).toBe(historyAfter);
      for (let i = 0; i < 130 && !screen.display().includes('SIDE-END'); i++) await emit('pagedown');
      expect(screen.display()).toContain('SIDE-END');
      expect(screen.display()).toContain('SIDE-QUESTION');
      expect(screen.display()).toContain('side panel is active');
      app.rerender(view([])); await wait();
      expect(screen.display()).not.toContain('SIDE-QUESTION');
      expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
    } finally { app.unmount(); app.cleanup(); }
  }, 20000);

  it('scrolls exposed history without scrolling the area covered by a picker', async () => {
    dimensions.rows = 24; dimensions.columns = 80;
    const state = createInitialDemoState();
    state.messages = [{ id: 'history', type: 'agent', content: history, timestamp: '', author: 'Agent' }];
    const stdout = Object.assign(new PassThrough(), dimensions);
    let frame = '';
    const app = render(<AppProvider><MainLayout {...state} demoPresentation workingDir="."
      onSendMessage={() => {}} demoOverlayHeight={10}
      demoOverlay={<Box height={10}><Text>PICKER</Text></Box>} /></AppProvider>,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output; } });
    try {
      await wait();
      const before = frame;
      await emit('wheelup', '\x1b[<64;3;20M');
      expect(frame).toBe(before);
      await emit('wheelup', '\x1b[<64;3;2M');
      expect(frame).not.toBe(before);
      expect(frame).toContain('PICKER');
      const scrolled = frame;
      await emit('pageup');
      expect(frame).toBe(scrolled);
    } finally { app.unmount(); app.cleanup(); }
  });
});