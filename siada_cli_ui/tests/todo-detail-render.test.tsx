import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { TodoDetailView } from '../src/components/Todo/TodoDetailView.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const dimensions = { rows: 24, columns: 48 };
const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useTerminalSize.js', () => ({ useTerminalSize: () => dimensions }));
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void) => {
    React.useEffect(() => { handlers.add(handler); return () => { handlers.delete(handler); }; }, [handler]);
  } };
});
const wait = () => new Promise(resolve => setTimeout(resolve, 60));
const key = (name: string) => {
  const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false, insertable: false, sequence: '' };
  [...handlers].forEach(handler => handler(event));
};

describe('bounded todo detail', () => {
  it.each([20, 24, 43])('keeps long task records scrollable and the close hint visible at %i rows', async rows => {
    dimensions.rows = rows;
    const stdout = Object.assign(new PassThrough(), dimensions);
    const frames: string[] = [], chunks: string[] = [];
    const screen = new TerminalScreen(rows, dimensions.columns);
    stdout.on('data', chunk => { chunks.push(chunk.toString()); screen.feed(chunk.toString()); });
    const onClose = vi.fn();
    const app = render(<TodoDetailView embedded terminalWidth={48} onClose={onClose}
      todo={{ content: '检查一个具有长名称的原有任务详情与返回提示', status: 'completed' }}
      messages={[{ id: 'a', type: 'agent', author: 'Siada', timestamp: '',
        content: Array.from({ length: 100 }, (_, index) => `记录 ${index + 1}: 中文任务详情`).join('\n'),
        metadata: { subtype: 'answer' } }]}
      range={{ startIdx: 0, endIdx: 1 }} />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: frame => frames.push(frame.output.replace(/\x1b\[[0-9;]*m/g, '')),
    });
    try {
      await wait();
      expect(frames.at(-1)).toContain('记录 100');
      expect(frames.at(-1)).toContain('Esc 返回');
      expect(frames.at(-1)!.split('\n').length).toBeLessThanOrEqual(rows - 1);
      key('pageup'); await wait();
      expect(frames.at(-1)).not.toContain('记录 100');
      expect(screen.display()).toContain('Esc 返回');
      expect(chunks.join('')).not.toContain('\x1b[?1049h');
      key('escape');
      expect(onClose).toHaveBeenCalledOnce();
    } finally { app.unmount(); app.cleanup(); }
    expect(chunks.join('')).not.toContain('\x1b[?1049l');
    expect(chunks.join('')).toContain('\x1b[?1006l');
  });
});