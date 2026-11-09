import './helpers/chineseLocale.js';
import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { createInitialDemoState, createPresentationDemoState } from '../examples/three-pane-demo-data.mjs';
import { TerminalScreen } from './helpers/terminalScreen.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { setActiveTheme } from '../src/themes/index.js';

const dimensions = { rows: 24, columns: 48 };
vi.mock('../src/hooks/useTerminalSize.js', () => ({ useTerminalSize: () => dimensions }));
const handlers = new Set<(key: Key) => void>();
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
const wait = () => new Promise(resolve => setTimeout(resolve, 70));

describe('original components in the three-pane demo', () => {
  it.each([[20, 48], [24, 80], [43, 100]].flatMap(([rows, columns]) =>
    (['dark', 'light'] as const).map(theme => ({ rows, columns, theme }))))(
    'links clickable work labels to hover color and right-side tips at $rows×$columns in $theme',
    async ({ rows, columns, theme }) => {
      dimensions.rows = rows;
      dimensions.columns = columns;
      chalk.level = 3;
      setActiveTheme(theme);
      const hoverAnsi = theme === 'dark' ? '\x1b[38;2;208;215;223m' : '\x1b[38;2;57;66;78m';
      const initial = createPresentationDemoState();
      initial.todoItems = Array.from({ length: 8 }, (_, index) => ({
        content: `Preview ${index + 1} ${'中文长任务'.repeat(20)}\n第二行`,
        status: index < 4 ? 'completed' : index === 4 ? 'in_progress' : 'pending',
      }));
      const stdout = Object.assign(new PassThrough(), dimensions);
      let frame = '', raw = '', terminalOutput = '';
      stdout.on('data', chunk => { terminalOutput += chunk.toString(); });
      const app = render(<AppProvider><MainLayout {...initial} demoPresentation workingDir="." provider="offline"
        onSendMessage={() => {}} /></AppProvider>, {
        stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ output }) => { raw = output; frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
      });
      const move = async (x: number, y: number) => {
        const event: Key = { name: 'mousemove', ctrl: false, cmd: false, alt: false,
          shift: false, insertable: false, sequence: `\x1b[<35;${x};${y}M` };
        [...handlers].forEach(handler => handler(event));
        await wait();
      };
      try {
        await wait();
        expect(frame.split('\n').filter(line => /Preview \d/.test(line))).toHaveLength(3);
        expect(frame).toContain('Todo 4/8 ▲ ▼');
        expect(frame).not.toContain('第二行');
        for (const [label, tip] of [
          ['› Goal', 'Click to view Goal'],
          ['› Agents', '点击查看智能体'],
        ]) {
          const lines = frame.split('\n');
          const row = lines.findIndex(line => line.includes(label));
          expect(row).toBeGreaterThanOrEqual(0);
          const x = lines[row].indexOf(label) + 1;
          await move(x, row + 1);
          expect(frame).toContain(tip);
          const tipRow = frame.split('\n').find(line => line.includes(tip))!;
          expect(tipRow.trimEnd().endsWith(tip)).toBe(true);
          expect(raw.split('\n')[row]).toContain(hoverAnsi);
          expect(raw.split('\n')[row]).not.toContain('\x1b[4m');
          await move(1, rows);
          expect(frame).not.toContain(tip);
          expect(raw.split('\n')[row]).not.toContain(hoverAnsi);
        }
        const emit = async (name: string, sequence = '') => {
          const event: Key = { name, ctrl: false, cmd: false, alt: false,
            shift: false, insertable: false, sequence };
          [...handlers].forEach(handler => handler(event));
          await wait();
        };
        const agentsRow = frame.split('\n').findIndex(line => line.includes('› Agents'));
        await emit('mouseclick', `\x1b[<0;3;${agentsRow + 1}M`);
        await emit('mouserelease', `\x1b[<0;3;${agentsRow + 1}m`);
        expect(frame).toContain('Agents · 子智能体');
        await emit('return', '\r');
        expect(frame).toContain('Agent · 展示检查');
        await emit('escape', '\x1b');
        await emit('escape', '\x1b');
        expect(frame).toContain('› Agents');
        expect(terminalOutput.lastIndexOf('\x1b[?1006h'))
          .toBeGreaterThan(terminalOutput.lastIndexOf('\x1b[?1006l'));
        const todoRow = frame.split('\n').findIndex(line => line.includes('› Todo'));
        await move(3, todoRow + 1);
        expect(frame).not.toContain('点击查看待办清单');
        await emit('mouseclick', `\x1b[<0;3;${todoRow + 1}M`);
        await emit('mouserelease', `\x1b[<0;3;${todoRow + 1}m`);
        expect(frame).not.toContain('Todo ·');
        await emit('tab', '\t');
        await emit('tab', '\t');
        expect(frame).toContain('▶ ◐ Preview 5');
        await emit('return', '\r');
        expect(frame).not.toContain('Todo ·');
        await emit('up', '\x1b[A');
        expect(frame).toContain('▶ ✓ Preview 4');
        for (let index = 0; index < 5; index++) await emit('up', '\x1b[A');
        expect(frame).toContain('▶ ✓ Preview 1');
        for (let index = 0; index < 9; index++) await emit('down', '\x1b[B');
        expect(frame).toContain('▶ ○ Preview 8');
        expect(frame).not.toContain('Preview 1 ');
        await emit('escape', '\x1b');
        expect(frame).toContain('◐ Preview 5');
        expect(frame).not.toContain('▶ ');
        const progressed = { ...initial, todoItems: initial.todoItems.map((task, index) => ({
          ...task, status: index < 6 ? 'completed' : index === 6 ? 'in_progress' : 'pending',
        })) };
        app.rerender(<AppProvider><MainLayout {...progressed} demoPresentation workingDir="." provider="offline"
          onSendMessage={() => {}} /></AppProvider>);
        await wait();
        expect(frame).toContain('◐ Preview 7');
        expect(frame).not.toContain('Preview 5 ');
        const clickArrow = async (symbol: string) => {
          const lines = frame.split('\n');
          const row = lines.findIndex(line => line.includes('› Todo'));
          const x = lines[row].indexOf(symbol) + 1;
          await emit('mouseclick', `\x1b[<0;${x};${row + 1}M`);
          await emit('mouserelease', `\x1b[<0;${x};${row + 1}m`);
        };
        await clickArrow('▲');
        expect(frame).toContain('Preview 5 ');
        expect(frame).toContain('▶ ✓ Preview 6');
        await clickArrow('▼');
        expect(frame).not.toContain('Preview 5 ');
        expect(frame).toContain('▶ ◐ Preview 7');
        const taskLines = () => frame.split('\n').filter(line => /Preview \d/.test(line));
        const lastPage = taskLines();
        await clickArrow('▼');
        expect(taskLines()).toEqual(lastPage);
        await emit('tab', '\t');
        expect(frame).not.toContain('▶ ');
        await emit('escape', '\x1b');
        expect(frame).toContain('◐ Preview 7');
        expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
      } finally { app.unmount(); app.cleanup(); setActiveTheme('dark'); }
    },
  );
  it.each([20, 24, 43])('keeps the composer visible across panel states at %i rows', async rows => {
    dimensions.rows = rows;
    dimensions.columns = rows === 43 ? 100 : 48;
    const initial = createInitialDemoState();
    const scenarios = [
      initial,
      { ...initial, loading: true, activeStep: 'tool_execution',
        promptQueue: [{ id: 'q1', content: 'Queued message', addedAt: '' }] },
      { ...initial, sideQuestions: [{ id: 'side', question: '旁路问题', answer: '旁路答案' }],
        sideQuestionPanelVisible: true },
      { ...initial, goalState: { goal: { objective: '检查目标展示', status: 'active' }, verifying: true } },
      { ...initial, interactiveInput: { prompt: '输入 yes 继续', inputType: 'confirmation', isPassword: false } },
      { ...initial, todoItems: Array.from({ length: 8 }, (_, index) => ({
        content: `Preview ${index + 1} ${'中文长任务'.repeat(20)}\n第二行`,
        status: index < 4 ? 'completed' : index === 4 ? 'in_progress' : 'pending',
      })) },
    ];
    const stdout = Object.assign(new PassThrough(), dimensions);
    const screen = new TerminalScreen(rows, dimensions.columns);
    let frame = '';
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const view = state => <AppProvider><MainLayout {...state} workingDir="." provider="offline"
      onSendMessage={() => {}} /></AppProvider>;
    const app = render(view(initial), {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      for (const state of scenarios) {
        app.rerender(view(state)); await wait();
        expect(frame).toContain('▸');
        expect(screen.display()).toContain('▸');
        expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
        if (state.sideQuestionPanelVisible) expect(frame).toContain('旁路答案');
        if (state.interactiveInput) expect(frame).toContain('请输入内容…');
        if (state.promptQueue.length) expect(frame).toContain('1 条消息排队中');
        if (state.todoItems.length === 8) {
          expect(frame.split('\n').filter(line => /Preview \d/.test(line))).toHaveLength(3);
          expect(screen.display()).toContain('Preview 5');
        }
      }
    } finally { app.unmount(); app.cleanup(); }
  });
});