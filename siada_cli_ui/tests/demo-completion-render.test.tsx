import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import stringWidth from 'string-width';
import { describe, expect, it } from 'vitest';
import { DemoCompletionList } from '../src/components/layouts/DemoCompletionList.js';
import type { Suggestion } from '../src/types/autocomplete.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const wait = () => new Promise(resolve => setTimeout(resolve, 70));

describe('completion path rendering', () => {
  it.each([32, 48, 80, 160])('uses available width and keeps both path ends at %i columns', async columns => {
    const paths = [
      'chrome-acp/packages/core/src/transport/connection.ts',
      'chrome-acp/packages/core/src/transport/session.ts',
      'chrome-acp/中文目录/很长的中间路径/文件名称.ts',
      'chrome-acp/📁开发目录/very-long-middle-directory/末尾.ts',
      '.pytest_cache/',
    ];
    const suggestions: Suggestion[] = paths.map(label => ({ label, value: label, type: 'file' }));
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns });
    const screen = new TerminalScreen(24, columns);
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    let frame = '';
    const view = (width: number, activeIndex: number) =>
      <DemoCompletionList suggestions={suggestions} activeIndex={activeIndex} width={width} />;
    const app = render(view(columns, 0), {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      for (const width of [columns, 28, columns]) {
        app.rerender(view(width, 1));
        await wait();
        const lines = frame.split('\n');
        expect(lines).toHaveLength(7);
        paths.forEach((path, index) => {
          const row = lines[index + 1];
          expect(stringWidth(row)).toBeLessThanOrEqual(width);
          const label = row.slice(3).trimEnd();
          if (stringWidth(path) <= width - 4) {
            expect(label).toBe(path);
          } else {
            expect(label).toContain('…');
            const [head, tail] = label.split('…');
            expect(head.length).toBeGreaterThan(0);
            expect(tail.length).toBeGreaterThan(0);
            expect(path.startsWith(head)).toBe(true);
            expect(path.endsWith(tail)).toBe(true);
          }
          expect(screen.display()).toContain(label);
        });
        expect(lines[2]).toContain('›');
        expect(frame).not.toContain('\uFFFD');
      }
    } finally { app.unmount(); app.cleanup(); }
  });

  it('keeps command descriptions close to their labels', async () => {
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 100 });
    let frame = '';
    const app = render(<DemoCompletionList width={100} activeIndex={0} suggestions={[
      { label: '/help', value: '/help', type: 'command', description: 'Show help' },
      { label: '/very-long-command-name-ending', value: '/long', type: 'command', description: 'Description' },
    ]} />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await wait();
      const lines = frame.split('\n');
      expect(lines[1]).toContain('/help');
      expect(lines[1].indexOf('Show help')).toBe(23);
      expect(lines[2]).toContain('/very-lo');
      expect(lines[2]).toContain('ending');
      expect(lines[2]).toContain('…');
      expect(lines[2]).toContain('Description');
    } finally { app.unmount(); app.cleanup(); }
  });
});