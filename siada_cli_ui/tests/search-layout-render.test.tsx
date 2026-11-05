import React, { useState } from 'react';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import stringWidth from 'string-width';
import { describe, expect, it, vi } from 'vitest';
import { ConversationViewport } from '../src/components/Chat/ConversationViewport.js';
import { useKeypress, type Key } from '../src/hooks/useKeypress.js';
import type { Message } from '../src/types/index.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const handlers = new Set<(key: Key) => void>();
vi.mock('../src/utils/clipboard.js', () => ({ copySelectionToClipboard: vi.fn() }));
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

const pause = () => new Promise(resolve => setTimeout(resolve, 90));
const message = (id: string, content: string): Message => ({
  id, type: 'agent', content, author: 'Synthetic', timestamp: '2026-01-01T00:00:00Z',
  metadata: { subtype: 'tool_use', streamEnd: true },
});
const search = (id: string, query: string) =>
  message(id, `Search for: ${query} in src with file pattern *.{ts,tsx} in /tmp/project`);
const key = (name: string, extra: Partial<Key> = {}) => {
  const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false,
    insertable: false, sequence: '', ...extra };
  [...handlers].forEach(handler => handler(event));
};

function Scene({ messages, columns }: { messages: Message[]; columns: number }) {
  const [collapsed, setCollapsed] = useState(true);
  useKeypress(event => {
    if (event.ctrl && event.name === 'o') setCollapsed(value => !value);
  });
  return <Box height={39} width={columns} flexDirection="column">
    <ConversationViewport messages={messages} width={columns} height={36}
      presentation isCollapsed={collapsed} />
    <Text>INPUT DRAFT</Text>
  </Box>;
}

async function mount(messages: Message[], columns = 80) {
  const screen = new TerminalScreen(40, columns);
  const stdout = Object.assign(new PassThrough(), { rows: 40, columns });
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  const app = render(<Scene messages={messages} columns={columns} />,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0 });
  await pause();
  return { screen, close() { app.unmount(); app.cleanup(); } };
}

describe('Search presentation in real Ink frames', () => {
  it('puts each expression beside its action and keeps cwd behind disclosure', async () => {
    const test = await mount([search('a', 'timeout:'), search('b', '●')]);
    try {
      let text = test.screen.display();
      expect(text).toContain('2 searches');
      expect(text).toContain('├─ Search "timeout:" in src ›');
      expect(text).toContain('└─ Search "●" in src ›');
      expect(text.match(/file pattern:/g)).toHaveLength(2);
      expect(text).not.toContain('cwd:');
      expect(text.match(/timeout:/g)).toHaveLength(1);
      const lines = text.split('\n');
      const row = lines.findIndex(line => line.includes('Search "timeout:"'));
      const x = lines[row].indexOf('Search') + 2;
      key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` });
      key('mouserelease', { sequence: `\x1b[<0;${x};${row + 1}m` });
      await pause();
      text = test.screen.display();
      expect(text.match(/cwd:/g)).toHaveLength(1);
      expect(text).toContain('Search "timeout:" in src ⌄');
      expect(text).toContain('Search "●" in src ›');
      key('o', { ctrl: true }); await pause();
      expect(test.screen.display().match(/cwd:/g)).toHaveLength(2);
      key('o', { ctrl: true }); await pause();
      expect(test.screen.display()).not.toContain('cwd:');
    } finally { test.close(); }
  });

  it('keeps Search on one line in a mixed group and preserves legacy arguments', async () => {
    const test = await mount([
      message('read', 'Read the file `/tmp/project/a.ts`'),
      message('search', 'Search for: a|b in src with file pattern *.ts'),
      message('run', 'Run the following command:\n```bash\npwd\n```\ntimeout:60s'),
    ]);
    try {
      const text = test.screen.display();
      expect(text).toContain('├─ Search "a|b" in src');
      expect(text).toContain('└─ file pattern: *.ts');
      expect(text).toContain('a.ts');
      expect(text).toContain('pwd');
      expect(text).not.toContain('timeout:60s');
      expect(text).not.toMatch(/^\s*[├└]─ Search\s*$/m);
    } finally { test.close(); }
  });

  it.each([24, 32, 80])('wraps a complete Chinese expression once at %i columns', async columns => {
    const query = '终端鼠标选择双击选词拖动选区边界中文验证';
    const test = await mount([search('a', query)], columns);
    try {
      key('o', { ctrl: true }); await pause();
      const text = test.screen.display();
      expect(text.replace(/\s+/g, '').split(query)).toHaveLength(2);
      expect(text).toContain('● Search "');
      expect(text.replace(/\s+/g, '')).toContain('cwd:/tmp/project');
      expect(text).not.toContain('�');
      expect(text).toContain('INPUT DRAFT');
      for (const line of text.split('\n')) expect(stringWidth(line)).toBeLessThanOrEqual(columns);
    } finally { test.close(); }
  });

  it('distinguishes embedded quotes from the expression delimiters', async () => {
    const test = await mount([search('a', '"timeout"|●')]);
    try {
      expect(test.screen.display()).toContain('Search "\\"timeout\\"|●" in src');
    } finally { test.close(); }
  });
});