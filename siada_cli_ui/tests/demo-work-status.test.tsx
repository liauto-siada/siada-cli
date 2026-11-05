import './helpers/chineseLocale.js';
import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { createPresentationDemoState } from '../examples/three-pane-demo-data.mjs';
import { setActiveTheme } from '../src/themes/index.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { DemoPickerCard } from '../src/components/layouts/DemoPickerCard.js';
import { slashCommandService } from '../src/services/slashCommandService.js';
import { demoCommands } from '../examples/three-pane-demo-data.mjs';
import { ConversationViewport } from '../src/components/Chat/ConversationViewport.js';
import { Text } from '@jrichman/ink';
import { TerminalScreen } from './helpers/terminalScreen.js';

const dimensions = { rows: 24, columns: 80 };
const handlers = new Set<(key: Key) => void>();
const clipboard = vi.hoisted(() => ({ copy: vi.fn().mockResolvedValue('native') }));
vi.mock('../src/utils/clipboard.js', () => ({ copySelectionToClipboard: clipboard.copy }));
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
const wait = () => new Promise(resolve => setTimeout(resolve, 80));
describe('demo work summary', () => {
  it('sizes history to the visible area while a bottom picker owns keyboard focus', async () => {
    dimensions.rows = 24; dimensions.columns = 48;
    const stdout = Object.assign(new PassThrough(), dimensions);
    const screen = new TerminalScreen(24, 48);
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const props = {
      demoPresentation: true, workingDir: '.', bannerInHistory: false, isCollapsed: true,
      onSendMessage: () => {},
      messages: [{ id: 'picker-history', type: 'agent' as const, timestamp: '',
        content: Array.from({ length: 12 }, (_, i) => `History line ${i + 1}`).join('\n'),
        metadata: { subtype: 'answer' } }],
    };
    const app = render(<AppProvider><MainLayout {...props} /></AppProvider>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });
    try {
      await wait();
      app.rerender(<AppProvider><MainLayout {...props} demoOverlayHeight={16}
        demoOverlay={<Text>Picker test panel</Text>} /></AppProvider>);
      await wait();
      expect(screen.display()).toContain('History line 12');
      expect(screen.display()).toContain('Picker test panel');
      for (let i = 0; i < 5; i++) {
        [...handlers].forEach(handler => handler({ name: 'wheelup', sequence: '\x1b[<64;3;3M',
          insertable: false, ctrl: false, cmd: false, alt: false, shift: false }));
        await wait();
      }
      expect(screen.display()).toContain('History line 1');
      expect(screen.display()).toContain('Picker test panel');
      app.rerender(<AppProvider><MainLayout {...props} /></AppProvider>);
      await wait();
      expect(screen.display()).not.toContain('Picker test panel');
      expect(screen.display()).toContain('输入消息');
    } finally { app.unmount(); app.cleanup(); }
  });
  it.each([48, 80])('retains completed Goal until the next chat clears it at %i columns', async columns => {
    dimensions.rows = 24; dimensions.columns = columns;
    let now = Date.parse('2026-01-01T00:00:00Z');
    const clock = vi.spyOn(Date, 'now').mockImplementation(() => now);
    const state = createPresentationDemoState();
    const goal = { objective: 'Persist the synthetic Goal', status: 'active' as const,
      createdAt: '2026-01-01T00:00:00Z', elapsedSeconds: 62,
      elapsedUpdatedAt: '2026-01-01T00:00:00Z', turns: 2 };
    const props = { ...state, demoPresentation: true, workingDir: '.', onSendMessage: () => {},
      goalState: { goal, verifying: false } };
    let frame = '';
    const app = render(<AppProvider><MainLayout {...props} /></AppProvider>, {
      stdout: Object.assign(new PassThrough(), dimensions), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await wait();
      const row = frame.split('\n').findIndex(line => line.includes('› Goal'));
      expect(row).toBeGreaterThanOrEqual(0);
      const completed = { goal: { ...goal, status: 'complete' as const }, verifying: false };
      app.rerender(<AppProvider><MainLayout {...props} goalState={completed} /></AppProvider>);
      await wait();
      expect(frame.split('\n').findIndex(line => line.includes('› Goal'))).toBe(row);
      expect(frame.split('\n')[row]).toContain('Achieved (complete · 1m 2s · 2 turns)');
      now += 3_600_000;
      const messages = [...state.messages, { id: 'later-question', type: 'user' as const,
        timestamp: '', content: 'Discuss another topic' }];
      app.rerender(<AppProvider><MainLayout {...props} messages={messages}
        goalState={{ goal: null, verifying: false }} /></AppProvider>);
      await wait();
      expect(frame).not.toContain('› Goal');
      const replacement = { ...goal, objective: 'Replacement Goal', elapsedSeconds: 0,
        elapsedUpdatedAt: new Date(now).toISOString(), turns: 0 };
      app.rerender(<AppProvider><MainLayout {...props} goalState={{ goal: replacement, verifying: false }} /></AppProvider>);
      await wait();
      expect(frame).toContain('In progress (active · 0s · 0 turns)');
      expect(frame).not.toContain('complete ·');
      app.rerender(<AppProvider><MainLayout {...props} goalState={{ goal: null, verifying: false }} /></AppProvider>);
      await wait();
      expect(frame).not.toContain('› Goal');
    } finally { app.unmount(); app.cleanup(); clock.mockRestore(); }
  });

  it.each([48, 80])('keeps Goal in one left-aligned row across verification at %i columns', async columns => {
    dimensions.rows = 20; dimensions.columns = columns;
    const state = createPresentationDemoState();
    const goal = { ...state.goalState.goal, objective: '核对实现与验收证据'.repeat(8) + '\nsecond line' };
    let frame = '';
    const props = { ...state, demoPresentation: true, workingDir: '.', onSendMessage: () => {},
      goalState: { goal, verifying: false } };
    const app = render(<AppProvider><MainLayout {...props} /></AppProvider>, {
      stdout: Object.assign(new PassThrough(), dimensions), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await wait();
      const row = frame.split('\n').findIndex(line => line.includes('› Goal'));
      expect(frame.split('\n')[row]).toMatch(/^› Goal/);
      expect(frame.split('\n')[row]).toContain('In progress');
      expect(row).toBeLessThan(frame.split('\n').findIndex(line => line.includes('› Todo')));
      app.rerender(<AppProvider><MainLayout {...props} goalState={{ goal, verifying: true }} /></AppProvider>);
      await wait();
      expect(frame.split('\n').findIndex(line => line.includes('› Goal'))).toBe(row);
      expect(frame.split('\n')[row]).toContain('Verifying');
      expect(frame).not.toContain('Goal verifying...');
      expect(frame).not.toContain('ctrl+o for details');
      expect(frame.split('\n').length).toBeLessThanOrEqual(19);
    } finally { app.unmount(); app.cleanup(); }
  });
  it('moves the completed todo list to expandable message history', async () => {
    let frame = '';
    const state = createPresentationDemoState();
    const app = render(<AppProvider><MainLayout {...state} demoPresentation workingDir="."
      goalState={{ ...state.goalState, goal: { ...state.goalState.goal, status: 'complete' } }}
      onSendMessage={() => {}} todoItems={state.todoItems.map(item => ({ ...item, status: 'completed' as const }))}
      messages={[{ id: 'plan', type: 'agent', timestamp: '', content: '✓  唯一完成任务\n\n[1/1 completed]',
        metadata: { subtype: 'tool_use', streamEnd: true } }]} /></AppProvider>, {
      stdout: Object.assign(new PassThrough(), { rows: 24, columns: 100 }), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
    try {
      await wait();
      expect(frame).toContain('Plan completed (1/1)');
      expect(frame).not.toContain('唯一完成任务');
      expect(frame).not.toContain('› Todo');
      expect(frame).toContain('› Goal');
      expect(frame).toContain('(complete ·');
      const row = frame.split('\n').findIndex(line => line.includes('Plan completed')) + 1;
      for (const name of ['mouseclick', 'mouserelease']) {
        [...handlers].forEach(handler => handler({ name, sequence: `\x1b[<0;4;${row}${name === 'mouseclick' ? 'M' : 'm'}`,
          ctrl: false, cmd: false, alt: false, shift: false, insertable: false }));
        await wait();
      }
      expect(frame).toContain('唯一完成任务');
      expect(frame).not.toContain('› Todo');
    } finally { app.unmount(); app.cleanup(); }
  });
  it('prints each grouped one-line command once', async () => {
    let frame = '';
    const app = render(<ConversationViewport width={100} height={20} isCollapsed presentation messages={[
      { id: 'npm', type: 'agent', timestamp: '', content: 'Run the following command:\n```bash\nnpm test -- --run\n```',
        metadata: { subtype: 'tool_use' } },
      { id: 'pwd', type: 'agent', timestamp: '', content: 'Run the following command:\n```bash\npwd\n```',
        metadata: { subtype: 'tool_use' } },
    ]} />, { stdout: Object.assign(new PassThrough(), { rows: 24, columns: 100 }), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
    try {
      await wait();
      expect(frame.match(/npm test -- --run/g)).toHaveLength(1);
      expect(frame.match(/\bpwd\b/g)).toHaveLength(1);
    } finally { app.unmount(); app.cleanup(); }
  });
  it('collapses verification explanation by default and expands from its title', async () => {
    let frame = '';
    const app = render(<ConversationViewport width={100} height={20} isCollapsed presentation messages={[
      { id: 'verification', type: 'agent', timestamp: '', content: '', metadata: {
        subtype: 'goal_result', goalResult: { achieved: true, turns: 1, elapsedSeconds: 3, tokensUsed: 0,
          objective: '检查展示', reason: '验证说明全文' },
      } },
    ]} />, { stdout: Object.assign(new PassThrough(), { rows: 24, columns: 100 }), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
    try {
      await wait();
      expect(frame).toContain('✓ Goal Achieved · 检查展示');
      expect(frame).not.toContain('1 check');
      expect(frame).not.toContain('验证说明全文');
      const row = frame.split('\n').findIndex(line => line.includes('Goal Achieved')) + 1;
      for (const name of ['mouseclick', 'mouserelease']) {
        [...handlers].forEach(handler => handler({ name, sequence: `\x1b[<0;4;${row}${name === 'mouseclick' ? 'M' : 'm'}`,
          ctrl: false, cmd: false, alt: false, shift: false, insertable: false }));
        await wait();
      }
      expect(frame).toContain('验证说明全文');
      expect(frame.match(/Goal Achieved/g)).toHaveLength(1);
    } finally { app.unmount(); app.cleanup(); }
  });
  it('clicks the centered return control next to the composer without selecting text', async () => {
    dimensions.rows = 24; dimensions.columns = 100;
    let frame = '';
    const app = render(<AppProvider><MainLayout {...createPresentationDemoState()} demoPresentation
      workingDir="." onSendMessage={() => {}} /></AppProvider>, {
      stdout: Object.assign(new PassThrough(), dimensions), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    const key = async (name: string, sequence: string, ctrl = false) => {
      [...handlers].forEach(handler => handler({ name, sequence, ctrl, cmd: false, alt: false,
        shift: false, insertable: false }));
      await wait();
    };
    try {
      await wait();
      await key('home', '\x1b[1;5H', true);
      const lines = frame.split('\n');
      const row = lines.findIndex(line => line.includes('回到底部'));
      expect(row).toBeGreaterThanOrEqual(0);
      const x = lines[row].indexOf('回到底部') + 1;
      await key('mouseclick', `\x1b[<0;${x};${row + 1}M`);
      await key('mouserelease', `\x1b[<0;${x};${row + 1}m`);
      expect(frame).not.toContain('回到底部');
      expect(frame).not.toContain('最新回复');
      expect(frame).not.toContain('Ctrl+G 对话目录');
      expect(app.getSelection().isCollapsed).toBe(true);
    } finally { app.unmount(); app.cleanup(); }
  });
  it('shows a read path and line range once on the same row', async () => {
    let frame = '';
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 100 });
    const app = render(<ConversationViewport width={100} height={20} isCollapsed presentation messages={[
      { id: 'read', type: 'agent', timestamp: '',
        content: 'Read the file `src/example.tsx` from line 1 to line 80', metadata: { subtype: 'tool_use' } },
    ]} />, { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
    try {
      await wait();
      expect(frame.match(/src\/example\.tsx/g)).toHaveLength(1);
      expect(frame.split('\n').find(line => line.includes('src/example.tsx'))).toContain('Lines 1–80');
    } finally { app.unmount(); app.cleanup(); }
  });
  it('keeps a centered return control without default navigation tips', async () => {
    let frame = '';
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 100 });
    const app = render(<ConversationViewport width={100} height={20} isCollapsed presentation messages={[
      { id: 'answer', type: 'agent', timestamp: '', content: Array.from({ length: 60 }, (_, i) => `line ${i}`).join('\n'),
        metadata: { subtype: 'answer' } },
    ]} />, { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
    try {
      await wait();
      expect(frame).not.toContain('回到底部');
      [...handlers].forEach(handler => handler({ name: 'pageup', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: false, sequence: '\x1b[5~' }));
      await wait();
      const line = frame.split('\n').find(text => text.includes('回到底部'))!;
      expect(line).not.toContain('Ctrl+G 对话目录');
      expect(line.indexOf('↓ 回到底部')).toBeGreaterThan(30);
      [...handlers].forEach(handler => handler({ name: 'escape', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: false, sequence: '\x1b' }));
      await wait();
      expect(frame).not.toContain('回到底部');
      expect(frame).not.toContain('Ctrl+G 对话目录');
    } finally { app.unmount(); app.cleanup(); }
  });
  it('shows a standalone one-line command without a disclosure arrow', async () => {
    let frame = '';
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 80 });
    const app = render(<ConversationViewport width={80} height={20} isCollapsed presentation messages={[
      { id: 'command', type: 'agent', timestamp: '', content: 'Run the following command:\n```bash\npwd\n```\nTimeout: 30 seconds',
        metadata: { subtype: 'tool_use' } },
    ]} />, { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
    try {
      await wait();
      expect(frame).toContain('● Run pwd');
      expect(frame).not.toContain('pwd ›');
      expect(frame).not.toContain('pwd ⌄');
    } finally { app.unmount(); app.cleanup(); }
  });
  it('renders command completion above the input without mixing transcript text', async () => {
    dimensions.rows = 24;
    dimensions.columns = 80;
    slashCommandService.updateCommandsFromBackend(demoCommands);
    let frame = '';
    const stdout = Object.assign(new PassThrough(), dimensions);
    const app = render(<AppProvider><MainLayout {...createPresentationDemoState()} demoPresentation
      workingDir="." onSendMessage={() => {}} /></AppProvider>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await wait();
      const inputRow = frame.split('\n').findIndex(line => line.includes('▸'));
      [...handlers].forEach(handler => handler({ name: 'paste', sequence: '/mode', insertable: true,
        ctrl: false, cmd: false, alt: false, shift: false }));
      await new Promise(resolve => setTimeout(resolve, 600));
      expect(frame).toContain('命令建议');
      const lines = frame.split('\n');
      expect(lines.findIndex(line => line.includes('命令建议'))).toBeLessThan(inputRow);
      expect(lines.findIndex(line => line.includes('› Agents'))).toBeGreaterThan(
        lines.findIndex(line => line.includes('命令建议')));
      expect(lines.findIndex(line => line.includes('▸ /mode'))).toBe(inputRow);
      expect(lines.find(line => line.includes('命令建议'))).not.toContain('查看');
      [...handlers].forEach(handler => handler({ name: 'escape', sequence: '\x1b', insertable: false,
        ctrl: false, cmd: false, alt: false, shift: false }));
      await wait();
      expect(frame).not.toContain('命令建议');
      expect(frame).toContain('/mode');
    } finally { app.unmount(); app.cleanup(); }
  });
  it.each([['dark', 20, 48], ['light', 20, 48], ['dark', 24, 80], ['light', 24, 80]] as const)(
    'keeps summaries, failures and input visible in %s at %i rows', async (theme, rows, columns) => {
    dimensions.rows = rows;
    dimensions.columns = columns;
    setActiveTheme(theme);
    chalk.level = 3;
    const state = createPresentationDemoState();
    const stdout = Object.assign(new PassThrough(), dimensions);
    let frame = '';
    const renderedFrames: { plain: string; raw: string }[] = [];
    const app = render(<AppProvider><MainLayout {...state} demoPresentation workingDir="." onSendMessage={() => {}} /></AppProvider>,
      { stdout, stdin: new PassThrough(), exitOnCtrlC: false, patchConsole: false, maxFps: 0,
        onRender: ({ output }) => {
          frame = output.replace(/\x1b\[[0-9;]*m/g, '');
          renderedFrames.push({ plain: frame, raw: output });
        } });
    try {
      await wait();
      // The disclosure glyphs carry their own accent color, so the raw frame
      // separates `›` from the label with an escape sequence: match on the
      // escape-free text and assert against the raw row it came from.
      const rawRow = (needle: string) => renderedFrames.at(-1)?.raw.split('\n')
        .find(line => line.replace(/\x1b\[[0-9;]*m/g, '').includes(needle));
      const goalRow = frame.split('\n').find(line => line.includes('› Goal'))!;
      expect(goalRow).toMatch(/^› Goal/);
      expect(goalRow).toMatch(/In progress \(active · \d+s · 1 turn\)/);
      if (columns >= 80) expect(goalRow).toContain('目标');
      expect(frame).toContain('Todo');
      const todoHeader = frame.split('\n').find(line => line.includes('› Todo'))!;
      expect(todoHeader.trim()).toBe('› Todo 2/3 ▲ ▼');
      expect(todoHeader.indexOf('›')).toBe(0);
      const taskRows = frame.split('\n').filter(line => /[✓◐○] /.test(line) &&
        state.todoItems.some(task => line.includes(task.content)));
      expect(taskRows).toHaveLength(3);
      taskRows.forEach(line => {
        expect(line.search(/[✓◐○]/)).toBe(todoHeader.indexOf('Todo'));
      });
      expect(frame.split('\n').filter(line => /[├└]─/.test(line))).toHaveLength(0);
      expect(frame).toContain('○ 检查流式回复与任务入口');
      expect(frame).toContain('交互检查');
      expect(frame).toContain('输入消息');
      const tipLines = frame.split('\n');
      expect(tipLines.some(line => line.includes('Ctrl+G 对话目录'))).toBe(false);
      expect(tipLines[tipLines.findIndex(line => line.includes('▸')) - 2].trim()).toBe('');
      clipboard.copy.mockResolvedValue('native');
      clipboard.copy.mockClear();
      const copyLines = frame.split('\n');
      const copyRow = copyLines.findIndex(line => line.includes('› Goal'));
      const copyX = copyLines[copyRow].indexOf('Goal') + 1;
      const mouse = async (name: string, x: number) => {
        [...handlers].forEach(handler => handler({ name, ctrl: false, cmd: false, alt: false,
          shift: false, insertable: false,
          sequence: `\x1b[<${name === 'mousemove' ? 32 : 0};${x};${copyRow + 1}${name === 'mouserelease' ? 'm' : 'M'}` }));
        await wait();
      };
      await mouse('mouseclick', copyX);
      await mouse('mousemove', copyX + 4);
      await mouse('mouserelease', copyX + 4);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('Goal');
      expect(frame).not.toContain('Goal · Objective and verification');
      [...handlers].forEach(handler => handler({ name: 'selectionclear', ctrl: false, cmd: false,
        alt: false, shift: false, insertable: false, sequence: '\x1b' }));
      await wait();
      await new Promise(resolve => setTimeout(resolve, 2100));
      const hoverLines = frame.split('\n');
      const hoverRow = hoverLines.findIndex(line => line.includes('› Todo'));
      const hoverX = hoverLines[hoverRow].indexOf('Todo') + 1;
      [...handlers].forEach(handler => handler({ name: 'mousemove', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: false, sequence: `\x1b[<35;${hoverX};${hoverRow + 1}M` }));
      await wait();
      expect(renderedFrames.at(-1)?.raw.split('\n').find(line => line.includes('Todo'))).not.toContain('\x1b[4m');
      expect(renderedFrames.at(-1)?.raw.split('\n').find(line => line.includes('Todo'))).not.toContain('48;2;138;168;200');
      [...handlers].forEach(handler => handler({ name: 'mousemove', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: false, sequence: `\x1b[<35;${columns - 8};${hoverRow + 1}M` }));
      await wait();
      expect(rawRow('› Todo')).not.toContain('\x1b[4m');
      [...handlers].forEach(handler => handler({ name: 'mousemove', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: false, sequence: `\x1b[<35;1;${hoverLines.findIndex(line => line.includes('▸')) + 1}M` }));
      await wait();
      expect(rawRow('› Todo')).not.toContain('48;2;138;168;200');
      expect(frame.split('\n').findIndex(line => line.includes('› Agents'))).toBeGreaterThan(
        frame.split('\n').findIndex(line => line.includes('▸')));
      app.rerender(<AppProvider><MainLayout {...state} demoPresentation loading activeStep="reasoning"
        workingDir="." onSendMessage={() => {}} /></AppProvider>);
      await wait();
      const thinkingRow = frame.split('\n').find(line => line.includes('正在思考…'))!;
      expect(thinkingRow).not.toContain('最新回复');
      expect(thinkingRow).toMatch(/^◉ 正在思考…/);
      expect(goalRow.indexOf('›')).toBe(thinkingRow.indexOf('◉'));
      expect(todoHeader.indexOf('›')).toBe(thinkingRow.indexOf('◉'));
      expect(frame.split('\n').length).toBeLessThanOrEqual(dimensions.rows - 1);
      app.rerender(<AppProvider><MainLayout {...state} demoPresentation workingDir="."
        onSendMessage={() => {}} /></AppProvider>);
      await wait();
      const keyboard = async (name: string) => {
        [...handlers].forEach(handler => handler({ name, ctrl: false, cmd: false, alt: false,
          shift: false, insertable: false, sequence: name === 'tab' ? '\t' : name === 'return' ? '\r' : '\x1b' }));
        await wait();
      };
      await keyboard('tab');
      expect(rawRow('› Goal')).toContain('48;2;138;168;200');
      await keyboard('return');
      expect(frame).toContain('Goal · Objective and verification');
      expect(frame).not.toContain('› Todo');
      expect(frame).not.toContain('› Agents');
      expect(frame).toContain('Status: In progress');
      expect(frame).not.toContain('Enter 确定');
      expect(frame).not.toMatch(/1\. 完善目标/);
      await keyboard('escape');
      await keyboard('tab');
      await keyboard('tab');
      expect(renderedFrames.at(-1)?.raw.split('\n').find(line => line.includes('Todo'))).toContain('48;2;138;168;200');
      await keyboard('return');
      expect(frame).not.toContain('Todo · 待办清单');
      expect(frame).toContain('› Goal');
      await keyboard('return');
      expect(frame).toContain('› Todo');
      expect(frame).not.toContain('Task ·');
      await keyboard('escape');
      await keyboard('tab');
      await keyboard('tab');
      await keyboard('tab');
      expect(renderedFrames.at(-1)?.raw.split('\n').find(line => line.includes('Agents'))).toContain('48;2;138;168;200');
      await keyboard('return');
      expect(frame).toContain('Agents · 子智能体');
      await keyboard('escape');
      expect(frame).toContain('输入消息');
      await keyboard('tab');
      await keyboard('escape');
      [...handlers].forEach(handler => handler({ name: 'paste', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: true, sequence: '保留输入草稿' }));
      await wait();
      expect(frame).toContain('保留输入草稿');
      const baseline = frame;
      const overlay = <DemoPickerCard title="Model" pageHeight={Math.max(6, Math.min(10, Math.floor(rows / 2)))}
        items={['offline', 'offline-fast']} onSelect={() => {}} onClose={() => {}} />;
      app.rerender(<AppProvider><MainLayout {...state} demoPresentation demoOverlay={overlay} workingDir="."
        onSendMessage={() => {}} /></AppProvider>);
      await wait();
      expect(frame).toContain('Model');
      expect(frame.split('\n')[0]).toBe(baseline.split('\n')[0]);
      expect(frame).not.toContain('输入消息');
      app.rerender(<AppProvider><MainLayout {...state} demoPresentation workingDir="."
        onSendMessage={() => {}} /></AppProvider>);
      await wait();
      expect(frame.replace(/\((active|blocked|paused|complete) · \d+s ·/g, '($1 · time ·'))
        .toBe(baseline.replace(/\((active|blocked|paused|complete) · \d+s ·/g, '($1 · time ·'));
      const click = async (text: string) => {
        const lines = frame.split('\n');
        const row = lines.findLastIndex(line => line.includes(text));
        const x = lines[row].indexOf(text) + 2;
        for (const name of ['mouseclick', 'mouserelease']) {
          const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false, insertable: false,
            sequence: `\x1b[<0;${x};${row + 1}${name === 'mouseclick' ? 'M' : 'm'}` };
          [...handlers].forEach(handler => handler(event));
          await wait();
        }
      };
      await click('Agents');
      expect(frame).toContain('Agents · 子智能体');
      expect(frame.split('\n')[0]).toBe(baseline.split('\n')[0]);
      expect(frame).not.toContain('输入消息');
      const agentLines = frame.split('\n');
      const agentRow = agentLines.findIndex(line => line.includes('配色检查'));
      const agentX = agentLines[agentRow].indexOf('配色检查') + 1;
      [...handlers].forEach(handler => handler({ name: 'mousemove', ctrl: false, cmd: false, alt: false,
        shift: false, insertable: false, sequence: `\x1b[<35;${agentX};${agentRow + 1}M` }));
      await wait();
      expect(renderedFrames.at(-1)?.raw.split('\n').find(line => line.includes('配色检查')))
        .toContain('48;2;138;168;200');
      expect(frame).not.toContain('Agent · 配色检查');
      await click('配色检查');
      expect(frame).toContain('Agent · 配色检查');
      expect(frame).toContain('对比度');
      expect(frame.split('\n').length).toBeLessThanOrEqual(dimensions.rows - 1);
      const escape = () => [...handlers].forEach(handler => handler({ name: 'escape', ctrl: false,
        cmd: false, alt: false, shift: false, insertable: false, sequence: '\x1b' }));
      escape(); await wait();
      expect(frame).toContain('Agents · 子智能体');
      escape(); await wait();
      expect(frame.replace(/\((active|blocked|paused|complete) · \d+s ·/g, '($1 · time ·'))
        .toBe(baseline.replace(/\((active|blocked|paused|complete) · \d+s ·/g, '($1 · time ·'));
    } finally { app.unmount(); app.cleanup(); setActiveTheme('dark'); }
  }, 10000);
});