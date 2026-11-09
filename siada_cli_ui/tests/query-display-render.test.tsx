import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, render } from '@jrichman/ink';
import { describe, expect, it } from 'vitest';
import stringWidth from 'string-width';
import { SemanticToolCallView } from '../src/components/Chat/SemanticToolCallView.js';
import { parseToolCall } from '../src/utils/toolCallParser.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

describe('query layout in a real terminal frame', () => {
  it.each([1, 3])('keeps a streaming query and its overflow hint within %i rows', async maxRows => {
    const screen = new TerminalScreen(24, 40);
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 40 });
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const app = render(<Box width={40}>
      <SemanticToolCallView tool={parseToolCall(`Searching memory: ${'长中文查询'.repeat(20)}`)!}
        width={40} maxRows={maxRows} />
    </Box>, { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const lines = screen.display().split('\n').filter(line => line.trim());
      expect(lines).toHaveLength(maxRows);
      expect(lines.at(-1)).toContain('more lines');
    } finally { app.unmount(); app.cleanup(); }
  });
  it.each([28, 40, 80])('wraps the complete Chinese query once at %i columns', async columns => {
    const query = '终端鼠标选择双击选词拖动选区边界行为中文查询验证';
    const screen = new TerminalScreen(24, columns);
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns });
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const app = render(<Box width={columns}>
      <SemanticToolCallView tool={parseToolCall(`Searching memory: ${query}`)!} width={columns} />
    </Box>, { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const text = screen.display();
      const joined = text.replace(/\s/g, '');
      expect(joined.match(new RegExp(query, 'g'))).toHaveLength(1);
      expect(text).not.toContain('query:');
      expect(text).not.toContain('…');
      expect(text).not.toContain('�');
      expect(Math.max(...text.split('\n').map(stringWidth))).toBeLessThanOrEqual(columns);
      if (columns === 28) {
        const lines = text.split('\n').filter(line => line.trim());
        expect(lines[1]).toMatch(/^ {16}\S/);
      }
    } finally { app.unmount(); app.cleanup(); }
  });
});