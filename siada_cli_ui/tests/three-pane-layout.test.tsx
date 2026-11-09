import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { Text, render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { inputRestoreStore } from '../src/store/inputRestoreStore.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const dimensions = { columns: 48, rows: 24 };
vi.mock('../src/hooks/useTerminalSize.js', () => ({ useTerminalSize: () => dimensions }));
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));
vi.mock('../src/components/Queue/PromptQueuePreview.js', () => ({
  PromptQueuePreview: () => null,
}));
const wait = () => new Promise(resolve => setTimeout(resolve, 80));
describe('three-pane main layout', () => {
  it.each([20, 24, 43])('keeps a multiline draft and Todo preview within %i rows', async rows => {
    dimensions.rows = rows;
    const stdout = Object.assign(new PassThrough(), dimensions);
    const frames: string[] = [];
    const app = render(<AppProvider><MainLayout workingDir="/synthetic/project" model="demo-model"
      onSendMessage={() => {}} demoPresentation
      todoItems={[
        { content: 'First task', status: 'completed' },
        { content: 'Running task', status: 'in_progress' },
        { content: 'Last task', status: 'pending' },
      ]}
      messages={[]} /></AppProvider>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => frames.push(output.replace(/\x1b\[[0-9;]*m/g, '')),
    });
    try {
      await wait();
      inputRestoreStore.request(Array.from({ length: 11 }, (_, i) => `DraftLine${i + 1}`).join('\n'));
      await wait();
      const frame = frames.at(-1)!;
      expect(frame).toContain('DraftLine11');
      expect(frame).toContain('Running task');
      expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
    } finally { app.unmount(); app.cleanup(); }
  });
  it.each([20, 24, 30, 43, 50, 60])('budgets the entire frame at %i rows', async rows => {
    dimensions.rows = rows;
    const stdout = Object.assign(new PassThrough(), dimensions);
    const frames: string[] = [];
    const screen = new TerminalScreen(rows, dimensions.columns);
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const app = render(<AppProvider><MainLayout workingDir="/synthetic/project" model="demo-model" onSendMessage={() => {}}
      messages={[
        { id: 'u', type: 'user', content: '最新问题始终固定在顶部。\n第二行。', author: 'You', timestamp: '' },
        { id: 'a', type: 'agent', content: '回复正文\n'.repeat(500), author: 'Siada', timestamp: '',
          metadata: { subtype: 'answer' } },
      ]} /></AppProvider>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => frames.push(output.replace(/\x1b\[[0-9;]*m/g, '')),
    });
    try {
      await wait();
      const frame = frames.at(-1)!;
      expect(frame).toContain('Siada CLI');
      if (rows > 20) expect(frame).toContain('最新问题');
      expect(frame).toContain('▸');
      expect(frame).toContain('输入消息');
      expect(screen.display()).toContain('Siada CLI');
      if (rows > 20) expect(screen.display()).toContain('最新问题');
      expect(screen.display()).toContain('▸');
      expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
    } finally { app.unmount(); app.cleanup(); }
  });
});