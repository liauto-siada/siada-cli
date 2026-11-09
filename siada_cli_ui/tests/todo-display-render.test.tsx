import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { TodoDisplay } from '../src/components/Todo/TodoDisplay.js';
import type { TodoItem } from '../src/hooks/useAcp/types.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import { t } from '../src/i18n/index.js';

const plan = (current: number): TodoItem[] => Array.from({ length: 7 }, (_, index) => ({
  content: `Step ${index + 1}`,
  status: index < current ? 'completed' : index === current ? 'in_progress' : 'pending',
}));

async function preview(items: TodoItem[], activeIndex = -1, columns = 48, compact = true) {
  const stdout = Object.assign(new PassThrough(), { columns, rows: 20 });
  const screen = new TerminalScreen(20, columns);
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  let frame: string | undefined;
  const app = render(<TodoDisplay items={items} activeIndex={activeIndex} width={columns}
    compact={compact} onSelect={() => {}} onClose={() => {}} />, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  try {
    await vi.waitFor(() => expect(frame).toBeDefined());
    return { frame: frame!, screen: screen.display() };
  } finally { app.unmount(); app.cleanup(); }
}

describe('three-row Todo preview', () => {
  it.each([
    [0, ['Step 1', 'Step 2', 'Step 3']],
    [3, ['Step 3', 'Step 4', 'Step 5']],
    [6, ['Step 5', 'Step 6', 'Step 7']],
  ])('follows the current task at index %i in plan order', async (current, expected) => {
    const result = await preview(plan(current));
    const lines = result.frame.split('\n').filter(line => line.trim());
    expect(lines).toHaveLength(3);
    expected.forEach((text, index) => {
      expect(lines[index]).toContain(text);
      expect(result.screen).toContain(text);
    });
    expect(result.frame).toContain(`◐ Step ${current + 1}`);
  });

  it('keeps a keyboard-focused task visible independently of task progress', async () => {
    const result = await preview(plan(6), 0);
    expect(result.frame).toContain('▶ ✓ Step 1');
    expect(result.frame).not.toContain('Step 7');
  });

  it.each([1, 2, 3])('uses only %i rows for a short plan', async count => {
    const result = await preview(plan(0).slice(0, count));
    expect(result.frame.split('\n').filter(line => line.trim())).toHaveLength(count);
  });

  it('follows the first pending task when none is in progress', async () => {
    const items = plan(4);
    items[4].status = 'pending';
    const result = await preview(items);
    expect(result.frame).toContain('Step 4');
    expect(result.frame).toContain('Step 5');
    expect(result.frame).toContain('Step 6');
    expect(result.frame).not.toContain('Step 1');
  });

  it.each([16, 48, 80])('truncates CJK and embedded newlines into three real rows at %i columns', async columns => {
    const items: TodoItem[] = [
      { content: '验证 &lt;id&gt;\r\n以及\t第二行', status: 'completed' },
      { content: '检查中文宽度'.repeat(30), status: 'in_progress' },
      { content: '读取文件\n核对结果\u2028记录结论', status: 'pending' },
      { content: 'Hidden task', status: 'pending' },
    ];
    const result = await preview(items, -1, columns);
    expect(result.frame.split('\n').filter(line => line.trim())).toHaveLength(3);
    expect(result.screen.split('\n').filter(line => line.trim())).toHaveLength(3);
    expect(result.frame).toContain('…');
    expect(result.frame).not.toContain('&lt;');
    expect(result.frame).not.toContain('Hidden task');
    expect(items[0].content).toContain('\r\n');
  });

  it('caps the legacy list at three tasks while keeping navigation hints', async () => {
    const result = await preview(plan(3), 3, 100, false);
    expect(result.frame.split('\n').filter(line => /Step \d/.test(line))).toHaveLength(3);
    expect(result.frame).toContain('▲');
    expect(result.frame).toContain('▼');
    expect(result.frame).toContain(t('待办清单', 'Todos'));
  });
});