import './helpers/chineseLocale.js';
import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import stringWidth from 'string-width';
import { describe, expect, it, vi } from 'vitest';
import { ConversationViewport, conversationBlocks } from '../src/components/Chat/ConversationViewport.js';
import type { Message } from '../src/types/index.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import { setActiveTheme } from '../src/themes/index.js';
import { colors } from '../src/utils/colors.js';
import { createInitialDemoState, goalResultMessage } from '../examples/three-pane-demo-data.mjs';

const handlers = new Set<(key: Key) => void>();
const clipboard = vi.hoisted(() => ({ copy: vi.fn().mockResolvedValue('native') }));
vi.mock('../src/utils/clipboard.js', () => ({ copySelectionToClipboard: clipboard.copy }));
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void, options: { isActive?: boolean } = {}) => {
    React.useEffect(() => {
      if (options.isActive === false) return;
      handlers.add(handler); return () => { handlers.delete(handler); };
    }, [handler, options.isActive]);
  }};
});
const wait = () => new Promise(resolve => setTimeout(resolve, 60));
const message = (id: string, type: Message['type'], content: string, subtype?: string): Message => ({
  id, type, content, author: 'Synthetic', timestamp: '2026-01-01T00:00:00Z', metadata: { subtype },
});
const key = (name: string, extra: Partial<Key> = {}) => {
  const event: Key = { name, alt: false, ctrl: false, cmd: false, shift: false, insertable: false, sequence: '', ...extra };
  [...handlers].forEach(handler => handler(event));
  if (name === 'mouseclick') {
    [...handlers].forEach(handler => handler({ ...event, name: 'mouserelease', sequence: event.sequence.replace(/M$/, 'm') }));
  }
};
function harness(messages: Message[], rows = 24, columns = 80, withBanner = false, presentation = false) {
  let currentMessages = messages;
  const stdout = Object.assign(new PassThrough(), { rows, columns });
  const frames: string[] = [];
  const rawFrames: string[] = [];
  const chunks: string[] = [];
  const screen = new TerminalScreen(rows, columns);
  stdout.on('data', chunk => { chunks.push(chunk.toString()); screen.feed(chunk.toString()); });
  const view = (items: Message[], active = true) => <Box height={rows - 1} width={columns} flexDirection="column">
    <ConversationViewport messages={items} width={columns} height={rows - 4} isCollapsed active={active} presentation={presentation}
      bannerProps={withBanner ? { version: 'test', workingDir: '.', isCollapsed: true } : undefined} />
    <Text>INPUT DRAFT</Text>
  </Box>;
  const app = render(view(messages), {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { rawFrames.push(output); frames.push(output.replace(/\x1b\[[0-9;]*m/g, '')); },
  });
  return { frames, rawFrames, chunks, screen, app,
    rerender: (items: Message[], active = true) => { currentMessages = items; app.rerender(view(items, active)); },
    resize: (nextRows: number, nextColumns: number) => {
      rows = nextRows; columns = nextColumns;
      stdout.rows = rows; stdout.columns = columns;
      app.rerender(view(currentMessages));
    },
    close: () => { app.unmount(); app.cleanup(); } };
}

function mouse(name: string, x: number, y: number, shift = false) {
  const button = (name === 'mousemove' ? 32 : 0) + (shift ? 4 : 0);
  const event: Key = { name, alt: false, ctrl: false, cmd: false, shift, insertable: false,
    sequence: `\x1b[<${button};${x};${y}${name === 'mouserelease' ? 'm' : 'M'}` };
  [...handlers].forEach(handler => handler(event));
}

describe('bounded conversation viewport', () => {
  it('scrolls Ctrl+arrows like the wheel and resumes following at the bottom', async () => {
    const items = Array.from({ length: 100 }, (_, index) =>
      message(`keyboard-${index}`, 'agent', `KEYBOARD_ROW_${index}`, 'answer'));
    const test = harness(items, 24, 80, false, true);
    try {
      await vi.waitFor(() => expect(test.screen.display()).toContain('KEYBOARD_ROW_99'));
      key('home', { ctrl: true }); await wait();
      const top = test.screen.display();
      key('down', { ctrl: true }); await wait();
      const keyboardDown = test.screen.display();
      expect(keyboardDown).not.toBe(top);
      key('home', { ctrl: true }); await wait();
      key('wheeldown'); await wait();
      expect(test.screen.display()).toBe(keyboardDown);
      key('up', { ctrl: true }); await wait();
      expect(test.screen.display()).toBe(top);
      key('up', { ctrl: true }); await wait();
      expect(test.screen.display()).toBe(top);

      key('end', { ctrl: true }); await wait();
      key('up', { ctrl: true }); await wait();
      const browsing = test.screen.display();
      key('end', { ctrl: true }); await wait();
      key('wheelup'); await wait();
      expect(test.screen.display()).toBe(browsing);
      const appended = [...items, message('new-tail', 'agent', 'KEYBOARD_NEW_TAIL', 'answer')];
      test.rerender(appended); await wait();
      expect(test.screen.display()).not.toContain('KEYBOARD_NEW_TAIL');
      for (let i = 0; i < 10; i++) { key('down', { ctrl: true }); await wait(); }
      expect(test.screen.display()).toContain('KEYBOARD_NEW_TAIL');
      test.rerender([...appended, message('following-tail', 'agent', 'KEYBOARD_FOLLOWING_TAIL', 'answer')]);
      await vi.waitFor(() => expect(test.screen.display()).toContain('KEYBOARD_FOLLOWING_TAIL'));
      test.rerender(appended, false); await wait();
      const inactive = test.screen.display();
      key('up', { ctrl: true }); await wait();
      expect(test.screen.display()).toBe(inactive);
    } finally { test.close(); }
  });

  it('drags the thin scrollbar to both ends, captures outside motion and releases without selecting text', async () => {
    clipboard.copy.mockClear();
    const items = Array.from({ length: 100 }, (_, index) =>
      message(`scroll-${index}`, 'agent', `SCROLL_ROW_${index}`, 'answer'));
    const test = harness(items, 24, 80, false, true);
    try {
      await vi.waitFor(() => expect(test.screen.display()).toContain('SCROLL_ROW_99'));
      const lines = test.screen.display().split('\n');
      const thumbRow = lines.findIndex(line => line[79] === '│');
      expect(thumbRow).toBeGreaterThan(0);
      mouse('mouseclick', 80, thumbRow + 1);
      mouse('mousemove', 40, 1);
      await vi.waitFor(() => expect(test.screen.display()).toContain('SCROLL_ROW_0'));
      mouse('mousemove', 40, 24);
      await vi.waitFor(() => expect(test.screen.display()).toContain('SCROLL_ROW_99'));
      mouse('mouserelease', 40, 24);
      const released = test.screen.display();
      mouse('mousemove', 80, 1);
      await wait();
      expect(test.screen.display()).toBe(released);
      expect(clipboard.copy).not.toHaveBeenCalled();
      const appended = [...items, message('tail', 'agent', 'SCROLL_NEW_TAIL', 'answer')];
      test.rerender(appended);
      await vi.waitFor(() => expect(test.screen.display()).toContain('SCROLL_NEW_TAIL'));
    } finally { test.close(); }
  });

  it('jumps on the scrollbar track and cancels capture when resized or deactivated', async () => {
    const items = Array.from({ length: 100 }, (_, index) =>
      message(`track-${index}`, 'agent', `TRACK_ROW_${index}`, 'answer'));
    const test = harness(items, 24, 80, false, true);
    try {
      await vi.waitFor(() => expect(test.screen.display()).toContain('TRACK_ROW_99'));
      mouse('mouseclick', 80, 1);
      await vi.waitFor(() => expect(test.screen.display()).toContain('TRACK_ROW_0'));
      test.resize(24, 60);
      await wait();
      mouse('mousemove', 40, 24);
      await wait();
      expect(test.screen.display()).toContain('TRACK_ROW_0');
      mouse('mouseclick', 60, 10);
      await wait();
      expect(test.screen.display()).not.toContain('TRACK_ROW_0');
      expect(test.screen.display()).not.toContain('TRACK_ROW_99');
      test.rerender(items, false);
      await wait();
      const inactive = test.screen.display();
      mouse('mousemove', 40, 1);
      mouse('mouserelease', 40, 1);
      await wait();
      expect(test.screen.display()).toBe(inactive);
    } finally { test.close(); }
  });

  it.each([32, 100])('renders prose after long code through the viewport at %i columns', async width => {
    const content = '```text\n' + 'literal **code** `value`\n'.repeat(200) +
      '```\n## MARKDOWN_TAIL\n**BOLD_TAIL** `INLINE_TAIL`';
    const test = harness([message('markdown-tail', 'agent', content, 'answer')], 24, width, false, true);
    try {
      await wait();
      await vi.waitFor(() => {
        const output = test.screen.display();
        expect(output).toContain('MARKDOWN_TAIL');
        expect(output).toContain('BOLD_TAIL');
        expect(output).toContain('INLINE_TAIL');
        expect(output).not.toContain('## MARKDOWN_TAIL');
        expect(output).not.toContain('**BOLD_TAIL**');
        expect(output).not.toContain('`INLINE_TAIL`');
      });
    } finally { test.close(); }
  });
  it.each([
    'Searching memory: unique_query',
    'Fact memory [search/project] unique_query',
    'Search for: unique_query in src with file pattern *.ts',
    'Web search: search: unique_query',
    '▶ TOOL USE Web search: unique_query',
  ])('shows the query once in the default production presentation: %s', async content => {
    const test = harness([message('t', 'agent', content, 'tool_use')], 24, 80, false, true);
    try {
      await wait();
      expect(test.screen.display().match(/unique_query/g)).toHaveLength(1);
      expect(test.screen.display()).not.toContain('query:');
      if (content.includes('[search/project]')) expect(test.screen.display()).toContain('target: project');
    } finally { test.close(); }
  });
  it.each([
    ['Searching memory: unique_query', 'Search memory'],
    ['Fact memory [search/project] unique_query', 'Fact memory search'],
    ['Search for: unique_query in src with file pattern *.ts', 'Search'],
    ['Web search: search: unique_query', 'Web Search'],
    ['▶ TOOL USE Web search: unique_query', 'Web Search'],
  ])('shows the query once before and after expanding %s', async (content, heading) => {
    const test = harness([message('u', 'user', 'Question'), message('t', 'agent', content, 'tool_use')]);
    try {
      await wait();
      expect(test.screen.display().match(/unique_query/g)).toHaveLength(1);
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('unique_query'));
      key('mouseclick', { sequence: `\x1b[<0;3;${y + 1}M` }); await wait();
      expect(test.screen.display()).toContain(heading);
      expect(test.screen.display().match(/unique_query/g)).toHaveLength(1);
      expect(test.screen.display()).not.toContain('query:');
      if (content.includes('[search/project]')) expect(test.screen.display()).toContain('target: project');
      key('mouseclick', { sequence: `\x1b[<0;3;${y + 1}M` }); await wait();
      expect(test.screen.display().match(/unique_query/g)).toHaveLength(1);
    } finally { test.close(); }
  });
  it('keeps repeated queries as separate calls when one tree branch expands', async () => {
    const test = harness([
      message('a', 'agent', 'Searching memory: unique_query', 'tool_use'),
      message('b', 'agent', 'Searching memory: unique_query', 'tool_use'),
    ]);
    try {
      await wait();
      expect(test.screen.display().match(/unique_query/g)).toHaveLength(2);
      const y = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('├─'));
      key('mouseclick', { sequence: `\x1b[<0;6;${y + 1}M` }); await wait();
      expect(test.screen.display().match(/unique_query/g)).toHaveLength(2);
      expect(test.screen.display()).toContain('Search memory');
    } finally { test.close(); }
  });
  it.each(['thinking', 'tool_use'])('limits %s hover and clicks to the visible heading row and columns', async subtype => {
    const content = subtype === 'thinking' ? 'Reasoning body' :
      'Read the file `src/example.ts` from line 1 to line 10';
    const test = harness([message('u', 'user', 'Question'), message('t', 'agent', content, subtype)]);
    try {
      await wait();
      let lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes(subtype === 'thinking' ? 'Reasoning body' : 'Read file'));
      const title = lines[y].trimEnd();
      const right = stringWidth(title);
      expect(right).toBeLessThan(70);
      for (const point of [{ x: right + 1, y: y + 1 }, { x: 70, y: y + 1 },
        { x: 3, y }, { x: 3, y: y + 2 }]) {
        key('mousemove', { sequence: `\x1b[<35;${point.x};${point.y}M` }); await wait();
        expect(test.frames.at(-1)).not.toContain('点击');
        key('mouseclick', { sequence: `\x1b[<0;${point.x};${point.y}M` }); await wait();
        lines = test.frames.at(-1)!.split('\n');
        expect(lines[y]).toContain(title);
        expect(lines[y]).not.toContain('⌄');
      }
      for (const x of [3, right]) {
        key('mousemove', { sequence: `\x1b[<35;${x};${y + 1}M` }); await wait();
        expect(test.frames.at(-1)).toContain('点击展开');
      }
      key('mouseclick', { sequence: `\x1b[<0;3;${y + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击收起');
      expect(test.frames.at(-1)!.split('\n')[y]).toContain('⌄');
    } finally { test.close(); }
  });
  it('excludes tree indentation and title padding while keeping whitespace drag selection', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('u', 'user', 'Question'),
      message('a', 'agent', 'Read the file `src/中文.ts` from line 1 to line 10', 'tool_use'),
      message('b', 'agent', 'Read the file `src/second.ts` from line 1 to line 10', 'tool_use')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('├─ 中文.ts'));
      const x = lines[y].indexOf('├─') + 1;
      const right = stringWidth(lines[y].trimEnd());
      for (const column of [x - 1, right + 1, 70]) {
        key('mousemove', { sequence: `\x1b[<35;${column};${y + 1}M` }); await wait();
        expect(test.frames.at(-1)).not.toContain('点击');
        key('mouseclick', { sequence: `\x1b[<0;${column};${y + 1}M` }); await wait();
        expect(test.frames.at(-1)!.split('\n')[y]).toContain('›');
      }
      key('mousemove', { sequence: `\x1b[<35;${right};${y + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开工具详情');
      mouse('mouseclick', 70, y + 1);
      mouse('mousemove', x + 3, y + 1); await wait();
      mouse('mouserelease', x + 3, y + 1); await wait();
      expect(clipboard.copy).toHaveBeenCalledOnce();
      expect(clipboard.copy.mock.calls[0][0]).toContain('中文.ts');
      expect(test.frames.at(-1)!.split('\n')[y]).not.toContain('⌄');
    } finally { test.close(); }
  });
  it.each([40, 41, 79, 80])('matches clipped Chinese heading columns at %i columns', async columns => {
    const test = harness([message('u', 'user', 'Question'),
      message('tool', 'agent', `Read the file \`src/${'中文文件'.repeat(15)}.ts\``, 'tool_use')], 24, columns);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('Read file'));
      const title = lines[y].trimEnd();
      const right = stringWidth(title);
      expect(title).toContain('…');
      expect(right).toBeLessThan(columns);
      key('mousemove', { sequence: `\x1b[<35;${right};${y + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开工具');
      for (const x of [right + 1, columns]) {
        key('mousemove', { sequence: `\x1b[<35;${x};${y + 1}M` }); await wait();
        expect(test.frames.at(-1)).not.toContain('点击');
        key('mouseclick', { sequence: `\x1b[<0;${x};${y + 1}M` }); await wait();
        expect(test.frames.at(-1)!.split('\n')[y].trimEnd()).toBe(title);
      }
    } finally { test.close(); }
  });
  it('reaches the final history line after original Markdown and command examples', async () => {
    const state = createInitialDemoState();
    const test = harness(state.messages, 43, 100, true);
    try {
      await wait();
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('/demo reset');
      const messages = [...state.messages, message('input-received', 'system', '交互输入已收到：yes', 'process')];
      test.rerender(messages, false); await wait();
      test.rerender(messages, true); await wait();
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('交互输入已收到：yes');
      expect(test.screen.display()).toContain('交互输入已收到：yes');
      expect(test.frames.at(-1)!.split('\n').length).toBeLessThanOrEqual(42);
    } finally { test.close(); }
  });
  it('renders a structured goal result even when its message body is empty', async () => {
    const test = harness([message('u', 'user', 'Goal question'), goalResultMessage('goal', '检查 UI 展示')]);
    try {
      await wait();
      expect(test.frames.at(-1)).toContain('Goal');
      expect(test.frames.at(-1)).toContain('achieved');
      expect(test.frames.at(-1)).toContain('检查 UI 展示');
    } finally { test.close(); }
  });
  it('keeps a single click empty in both cells of a Chinese glyph and does not count adjacent clicks as a double click', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('a', 'agent', '中文内容', 'answer')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('中文内容'));
      const x = lines[y].indexOf('中文') + 1;
      for (const column of [x, x + 1, x + 2, x + 3]) {
        mouse('mouseclick', column, y + 1); await wait();
        expect(test.app.getSelection().isCollapsed).toBe(true);
        mouse('mouserelease', column, y + 1); await wait();
        expect(test.app.getSelection().isCollapsed).toBe(true);
        expect(clipboard.copy).not.toHaveBeenCalled();
      }
    } finally { test.close(); }
  });
  it.each([false, true])('selects one Chinese glyph between boundaries, reverse=%s', async reverse => {
    clipboard.copy.mockClear();
    const test = harness([message('a', 'agent', '中文内容', 'answer')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('中文内容'));
      const x = lines[y].indexOf('中文') + 1;
      const start = reverse ? x + 2 : x;
      const end = reverse ? x : x + 2;
      mouse('mouseclick', start, y + 1);
      mouse('mousemove', start + 1, y + 1); await wait();
      expect(test.app.getSelection().isCollapsed).toBe(true);
      mouse('mousemove', end, y + 1); await wait();
      const ranges = test.app.getSelection().textRanges!;
      expect([...ranges.values()]).toEqual([{ start: 0, end: 1 }]);
      mouse('mouserelease', end, y + 1); await wait();
      expect(clipboard.copy).toHaveBeenCalledTimes(1);
      expect(clipboard.copy.mock.calls[0][0]).toBe('中');
    } finally { test.close(); }
  });
  it.each(['indent', 'line end', 'between lines', 'below text'])(
    'starts selection from %s whitespace and copies only source text',
    async origin => {
      clipboard.copy.mockClear();
      const test = harness([message('a', 'agent', 'alpha first\n\nbeta second', 'answer')], 30, 80);
      try {
        await wait();
        const lines = test.frames.at(-1)!.split('\n');
        const first = lines.findIndex(line => line.includes('alpha first'));
        const second = lines.findIndex(line => line.includes('beta second'));
        const firstX = lines[first].indexOf('alpha first') + 1;
        const secondX = lines[second].indexOf('beta second') + 1;
        const start = origin === 'indent' ? { x: firstX - 1, y: first + 1 } :
          origin === 'line end' ? { x: 75, y: first + 1 } :
          origin === 'between lines' ? { x: 40, y: first + 2 } : { x: 75, y: second + 3 };
        const end = origin === 'indent' ? { x: firstX + 5, y: first + 1 } :
          origin === 'line end' ? { x: firstX, y: first + 1 } :
          origin === 'between lines' ? { x: secondX + 4, y: second + 1 } :
          { x: secondX, y: second + 1 };
        mouse('mouseclick', start.x, start.y); await wait();
        expect(clipboard.copy).not.toHaveBeenCalled();
        mouse('mousemove', end.x, end.y); await wait();
        expect(test.app.getSelection().isCollapsed).toBe(false);
        expect(clipboard.copy).not.toHaveBeenCalled();
        mouse('mouserelease', end.x, end.y); await wait();
        expect(clipboard.copy).toHaveBeenCalledTimes(1);
        const expected = origin === 'indent' ? 'alpha' : origin === 'line end' ? 'alpha first' :
          origin === 'between lines' ? 'beta' : 'beta second';
        expect(clipboard.copy.mock.calls[0][0].trim()).toBe(expected);
        expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      } finally { test.close(); }
    },
  );
  it('leaves repeated clicks on padding and blank lines empty', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('a', 'agent', 'alpha first\n\nbeta second', 'answer')], 30, 80);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const first = lines.findIndex(line => line.includes('alpha first'));
      const second = lines.findIndex(line => line.includes('beta second'));
      for (const point of [{ x: 75, y: first + 1 }, { x: 40, y: first + 2 },
        { x: 75, y: second + 3 }]) {
        for (let count = 0; count < 3; count++) {
          key('mouseclick', { sequence: `\x1b[<0;${point.x};${point.y}M` }); await wait();
          expect(test.app.getSelection().isCollapsed).toBe(true);
          expect(clipboard.copy).not.toHaveBeenCalled();
        }
      }
    } finally { test.close(); }
  });
  it('does not start a history selection from the composer, outside columns, or a pinned question', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('u', 'user', 'Pinned question'),
      message('a', 'agent', 'alpha line\n'.repeat(50), 'answer')], 24, 80);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const answer = lines.findIndex(line => line.includes('alpha line'));
      const input = lines.findIndex(line => line.includes('INPUT DRAFT'));
      for (const start of [{ x: 1, y: input + 1 }, { x: 81, y: answer + 1 }, { x: 3, y: 1 }]) {
        mouse('mouseclick', start.x, start.y);
        mouse('mousemove', 7, answer + 1); await wait();
        mouse('mouserelease', 7, answer + 1); await wait();
        expect(test.app.getSelection().isCollapsed).toBe(true);
        expect(clipboard.copy).not.toHaveBeenCalled();
        expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      }
    } finally { test.close(); }
  });
  it('coalesces motion and ignores repeated positions within the same grapheme', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('a', 'agent', 'hello world 中文', 'answer')], 24, 80);
    let notifications = 0;
    const unsubscribe = test.app.getSelection().onChange(() => { notifications++; });
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('hello world'));
      const x = lines[y].indexOf('hello') + 1;
      mouse('mouseclick', x, y + 1); await wait();
      const before = notifications;
      for (let index = 0; index < 1000; index++) mouse('mousemove', x + 7 + index % 4, y + 1);
      await wait();
      expect(notifications - before).toBe(1);
      const rendered = test.rawFrames.length;
      for (let index = 0; index < 100; index++) mouse('mousemove', x + 10, y + 1);
      await wait();
      expect(notifications - before).toBe(1);
      expect(test.rawFrames.length).toBe(rendered);
      mouse('mouserelease', x + 10, y + 1); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('hello worl');
    } finally { unsubscribe(); test.close(); }
  });
  it('holds the selected content revision while replies stream or a new user turn arrives', async () => {
    clipboard.copy.mockClear();
    const items = [message('u', 'user', 'Question'), message('a', 'agent', 'hello world', 'answer')];
    const test = harness(items);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('hello world'));
      const x = lines[y].indexOf('hello') + 1;
      mouse('mouseclick', x, y + 1); await wait();
      mouse('mousemove', x + 5, y + 1); await wait();
      test.rerender([items[0], { ...items[1], content: 'REPLACED streamed revision' },
        message('u2', 'user', 'New question')]); await wait();
      expect(test.frames.at(-1)).toContain('hello world');
      expect(test.frames.at(-1)).not.toContain('REPLACED');
      mouse('mouserelease', x + 5, y + 1); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('hello');
      key('escape'); await wait();
      expect(test.frames.at(-1)).toContain('REPLACED streamed revision');
      expect(test.frames.at(-1)).toContain('New question');
    } finally { test.close(); }
  });
  it('keeps selection offsets and copied text stable when a paragraph rewraps', async () => {
    clipboard.copy.mockClear();
    const content = 'alpha beta gamma delta '.repeat(7).trimEnd();
    const test = harness([message('a', 'agent', content, 'answer')], 30, 80);
    try {
      await wait();
      let lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('alpha beta'));
      const x = lines[y].indexOf('alpha') + 1;
      mouse('mouseclick', x, y + 1); await wait();
      mouse('mousemove', x + 10, y + 1); await wait();
      mouse('mouserelease', x + 10, y + 1); await wait();
      const copied = clipboard.copy.mock.calls.at(-1)?.[0];
      expect(copied).toBe('alpha beta');
      test.resize(24, 38); await wait();
      expect(test.app.getSelection().isCollapsed).toBe(false);
      expect(test.frames.at(-1)).toContain('alpha beta');
      key('c', { ctrl: true }); await wait();
      expect(clipboard.copy).toHaveBeenCalledTimes(1);
      expect(clipboard.copy.mock.calls[0][0]).toBe(copied);
      expect(test.app.getSelection().rangeCount).toBe(0);
    } finally { test.close(); }
  });
  it('keeps selection available for retry when explicit clipboard delivery fails', async () => {
    clipboard.copy.mockClear();
    clipboard.copy.mockResolvedValueOnce('failed');
    const test = harness([message('a', 'agent', 'hello world', 'answer')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('hello world'));
      const x = lines[y].indexOf('hello') + 1;
      mouse('mouseclick', x, y + 1);
      mouse('mousemove', x + 5, y + 1); await wait();
      mouse('mouserelease', x + 5, y + 1); await wait();
      expect(test.app.getSelection().isCollapsed).toBe(false);
      expect(test.frames.at(-1)).toContain('复制失败');
      key('c', { ctrl: true }); await wait();
      expect(clipboard.copy).toHaveBeenCalledTimes(2);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('hello');
      expect(test.app.getSelection().rangeCount).toBe(0);
    } finally { test.close(); }
  });
  it('keeps source anchors when the selected start scrolls out of mounted history', async () => {
    clipboard.copy.mockClear();
    const items = Array.from({ length: 90 }, (_, index) => message(`a${index}`, 'agent', `entry-${index} content`, 'answer'));
    const test = harness(items, 20, 80);
    try {
      await wait(); key('home', { ctrl: true }); await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('entry-0 content'));
      const x = lines[y].indexOf('entry-0') + 1;
      mouse('mouseclick', x, y + 1); await wait();
      for (let page = 0; page < 7; page++) { key('pagedown'); await wait(); }
      const lastLines = test.frames.at(-1)!.split('\n');
      const lastY = lastLines.findIndex(line => line.includes('entry-'));
      const lastX = lastLines[lastY].indexOf('entry-') + 1;
      const id = /entry-(\d+)/.exec(lastLines[lastY])![1];
      mouse('mousemove', lastX + 8, lastY + 1); await wait();
      mouse('mouserelease', lastX + 8, lastY + 1); await wait();
      const copied = clipboard.copy.mock.calls.at(-1)?.[0] as string;
      expect(Number(id)).toBeGreaterThan(30);
      expect(copied.startsWith('entry-0 content')).toBe(true);
      expect(copied).toContain('entry-20 content');
      expect(copied).toContain(`entry-${id}`);
      expect(test.frames.at(-1)).not.toContain('entry-0 content');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });
  it('autoscrolls only vertical drags at an edge and lets wheel scrolling stop it', async () => {
    clipboard.copy.mockClear();
    const content = Array.from({ length: 90 }, (_, index) => `line-${index} alpha beta`).join('\n');
    const test = harness([message('a', 'agent', content, 'answer')], 24, 80);
    try {
      await wait(); key('home', { ctrl: true }); await wait();
      let lines = test.frames.at(-1)!.split('\n');
      let y = lines.findIndex(line => line.includes('line-0'));
      const x = lines[y].indexOf('line-0') + 1;
      mouse('mouseclick', x, y + 1); await wait();
      mouse('mousemove', x + 8, y + 1); await wait(); await wait();
      expect(test.frames.at(-1)).toContain('line-0');
      mouse('mousemove', x + 8, 19); await wait(); await wait(); await wait();
      expect(test.frames.at(-1)).not.toContain('line-0 alpha');
      key('wheelup'); await wait();
      const stopped = test.frames.at(-1);
      await wait(); await wait();
      expect(test.frames.at(-1)).toBe(stopped);
      lines = test.frames.at(-1)!.split('\n');
      y = lines.findIndex(line => line.includes('line-'));
      mouse('mouserelease', x + 8, y + 1); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toContain('line-0');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });
  it('retains word selection units while dragging and Shift-clicking', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('a', 'agent', 'alpha beta gamma delta', 'answer')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const y = lines.findIndex(line => line.includes('alpha beta'));
      const x = lines[y].indexOf('alpha') + 1;
      key('mouseclick', { sequence: `\x1b[<0;${x + 2};${y + 1}M` }); await wait();
      mouse('mouseclick', x + 2, y + 1);
      mouse('mousemove', x + 13, y + 1); await wait();
      mouse('mouserelease', x + 13, y + 1); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('alpha beta gamma');
      mouse('mouseclick', x + 20, y + 1, true);
      mouse('mouserelease', x + 20, y + 1, true); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('alpha beta gamma delta');
    } finally { test.close(); }
  });
  it('highlights dragged text and copies it once on release without activating a tool', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('u', 'user', 'Question'),
      message('t', 'agent', 'Run the following command:\n```bash\nprintf demo\n```', 'tool_use')]);
    try {
      await wait();
      const row = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('printf demo'));
      const deliver = (name: string, button: number, x: number) => {
        const event: Key = { name, alt: false, ctrl: false, cmd: false, shift: false,
          insertable: false, sequence: `\x1b[<${button};${x};${row + 1}${name === 'mouserelease' ? 'm' : 'M'}` };
        [...handlers].forEach(handler => handler(event));
      };
      deliver('mouseclick', 0, 3);
      deliver('mousemove', 32, 9); await wait();
      expect(test.app.getSelection().rangeCount).toBe(1);
      expect(clipboard.copy).not.toHaveBeenCalled();
      deliver('mouserelease', 0, 9); await wait();
      expect(clipboard.copy).toHaveBeenCalledTimes(1);
      expect(clipboard.copy.mock.calls[0][0]).toBe('printf');
      expect(test.frames.at(-1)).toContain('已复制选中内容');
      expect(test.frames.at(-1)!.split('\n')[row]).toContain('printf demo ›');
      expect(test.app.getSelection().rangeCount).toBe(1);
      key('mouseclick', { sequence: `\x1b[<0;3;${row + 1}M` }); await wait();
      expect(test.frames.at(-1)!.split('\n')[row]).toMatch(/printf demo\s+⌄/);
    } finally { test.close(); }
  });
  it('copies multiline Chinese text in either drag direction', async () => {
    const test = harness([message('u', 'user', 'Question'),
      message('a', 'agent', '中文第一行\n中文第二行', 'answer')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const first = lines.findIndex(line => line.includes('中文第一行'));
      const second = lines.findIndex(line => line.includes('中文第二行'));
      const x1 = lines[first].indexOf('中文第一行') + 1;
      const x2 = lines[second].indexOf('中文第二行') + 1;
      const deliver = (name: string, x: number, y: number) => {
        const event: Key = { name, alt: false, ctrl: false, cmd: false, shift: false, insertable: false,
          sequence: `\x1b[<${name === 'mousemove' ? 32 : 0};${x};${y}${name === 'mouserelease' ? 'm' : 'M'}` };
        [...handlers].forEach(handler => handler(event));
      };
      for (const reverse of [false, true]) {
        clipboard.copy.mockClear();
        deliver('mouseclick', reverse ? x2 + 10 : x1, reverse ? second + 1 : first + 1);
        deliver('mousemove', reverse ? x1 : x2 + 10, reverse ? first + 1 : second + 1);
        await wait();
        deliver('mouserelease', reverse ? x1 : x2 + 10, reverse ? first + 1 : second + 1);
        await wait();
        expect(clipboard.copy).toHaveBeenCalledTimes(1);
        expect(clipboard.copy.mock.calls[0][0]).toContain('中文第一行');
        expect(clipboard.copy.mock.calls[0][0]).toContain('中文第二行');
        expect(clipboard.copy.mock.calls[0][0]).toContain('\n');
      }
    } finally { test.close(); }
  });
  it('double-clicks words and triple-clicks lines without copying plain clicks', async () => {
    clipboard.copy.mockClear();
    const test = harness([message('u', 'user', 'Question'), message('a', 'agent', 'hello world', 'answer')]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const row = lines.findIndex(line => line.includes('hello world'));
      const x = lines[row].indexOf('hello') + 2;
      key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` }); await wait();
      expect(clipboard.copy).not.toHaveBeenCalled();
      key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` }); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('hello');
      key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` }); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('hello world');
      const count = clipboard.copy.mock.calls.length;
      key('c', { ctrl: true }); await wait();
      expect(clipboard.copy).toHaveBeenCalledTimes(count);
      expect(test.app.getSelection().rangeCount).toBe(0);
    } finally { test.close(); }
  });
  it('preserves soft-wrapped text and excludes navigation controls from selection', async () => {
    clipboard.copy.mockClear();
    const text = 'abcdefghij'.repeat(9);
    const test = harness([message('u', 'user', 'Question'),
      message('t', 'agent', text, 'thinking')], 30, 40);
    try {
      await wait();
      const heading = test.frames.at(-1)!.split('\n').findIndex(line => line.startsWith('› abcdefghij'));
      key('mouseclick', { sequence: `\x1b[<0;2;${heading + 1}M` }); await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const first = lines.findIndex(line => line.includes('abcdefghij'));
      const last = lines.findLastIndex(line => line.includes('abcdefghij'));
      const deliver = (name: string, x: number, y: number) => {
        const event: Key = { name, ctrl: false, alt: false, cmd: false, shift: false, insertable: false,
          sequence: `\x1b[<${name === 'mousemove' ? 32 : 0};${x};${y}${name === 'mouserelease' ? 'm' : 'M'}` };
        [...handlers].forEach(handler => handler(event));
      };
      deliver('mouseclick', 3, first + 1);
      deliver('mousemove', 40, last + 1); await wait();
      deliver('mouserelease', 40, last + 1); await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe(text);
      clipboard.copy.mockClear();
      const footer = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('已复制选中内容'));
      deliver('mouseclick', 3, footer + 1);
      deliver('mousemove', 15, footer + 1);
      deliver('mouserelease', 15, footer + 1); await wait();
      expect(clipboard.copy).not.toHaveBeenCalled();
    } finally { test.close(); }
  });
  it('cancels an unfinished copy on view close and reports failed writes truthfully', async () => {
    clipboard.copy.mockClear();
    clipboard.copy.mockResolvedValueOnce('failed');
    const test = harness([message('u', 'user', 'Question'), message('a', 'agent', 'hello world', 'answer')]);
    await wait();
    const lines = test.frames.at(-1)!.split('\n');
    const row = lines.findIndex(line => line.includes('hello world'));
    const x = lines[row].indexOf('hello') + 2;
    key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` }); await wait();
    key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` }); await wait();
    expect(test.frames.at(-1)).toContain('复制失败');
    let resolve: (value: string) => void;
    clipboard.copy.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    key('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` }); await wait();
    const signal = clipboard.copy.mock.calls.at(-1)![2] as AbortSignal;
    test.close();
    expect(signal.aborted).toBe(true);
    resolve!('native'); await wait();
    clipboard.copy.mockResolvedValue('native');
  });
  it('shows consecutive tools as a default tree and expands each tool independently', async () => {
    const read = message('read', 'agent', 'Read the file `src/example.ts` from line 1 to line 20', 'tool_use');
    const edit = message('edit', 'agent', `Edit file src/example.ts\n<!-- siada-file-edit:start -->\n${JSON.stringify({
      callId: 'tree-edit', action: 'update', path: 'src/example.ts', status: 'completed',
      oldString: 'const oldValue = 1;', newString: 'const newValue = 2;',
    })}\n<!-- siada-file-edit:end -->`, 'tool_use');
    const run = message('run', 'agent', 'Run the following command:\n```bash\nnpm test -- --run\n```', 'tool_use');
    const test = harness([message('u', 'user', 'Question'), read, edit, run,
      message('a', 'agent', 'Answer after tools', 'answer')], 43, 100);
    try {
      await wait();
      expect(test.frames.at(-1)).toContain('Read 1 file, Update 1 file, Run 1 command');
      expect(test.frames.at(-1)).toContain('├─ example.ts:1-20 ›');
      expect(test.frames.at(-1)).toContain('├─ example.ts ›');
      expect(test.frames.at(-1)).toContain('└─ npm test -- --run ›');
      expect(test.frames.at(-1)).not.toContain('const newValue');
      const editRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('├─ example.ts ›'));
      key('mousemove', { sequence: `\x1b[<35;6;${editRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开工具详情');
      key('mouseclick', { sequence: `\x1b[<0;6;${editRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('const newValue = 2;');
      expect(test.frames.at(-1)).toContain('├─ example.ts:1-20 ›');
      expect(test.frames.at(-1)).toContain('└─ npm test -- --run ›');
      const runRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('└─ npm test'));
      key('mouseclick', { sequence: `\x1b[<0;6;${runRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toMatch(/└─ npm test -- --run\s+⌄/);
      expect(test.frames.at(-1)).toContain('const newValue = 2;');
      key('mouseclick', { sequence: `\x1b[<0;6;${editRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).not.toContain('const newValue');
      expect(test.frames.at(-1)).toMatch(/└─ npm test -- --run\s+⌄/);
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });
  it.each([false, true])('copies adjacent tool rows with one newline, reverse=%s', async reverse => {
    clipboard.copy.mockClear();
    const run = message('run', 'agent', 'Run the following command:\n```bash\nnpm test -- --run\n```', 'tool_use');
    const edit = message('edit', 'agent', `Edit file src/example.ts\n<!-- siada-file-edit:start -->\n${JSON.stringify({
      callId: 'copy-edit', action: 'update', path: 'src/example.ts', status: 'completed',
      oldString: 'const value = 1;', newString: 'const value = 2;',
    })}\n<!-- siada-file-edit:end -->`, 'tool_use');
    const test = harness([run, edit], 24, 80);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const runRow = lines.findIndex(line => line.includes('├─ npm test -- --run'));
      const editRow = lines.findIndex(line => line.includes('└─ example.ts'));
      expect(runRow).toBeGreaterThanOrEqual(0);
      expect(editRow).toBe(runRow + 1);
      const first = { x: lines[runRow].indexOf('├─') + 1, y: runRow + 1 };
      const last = { x: lines[editRow].indexOf('└─') + '└─ example.ts'.length + 1, y: editRow + 1 };
      const start = reverse ? last : first, end = reverse ? first : last;
      mouse('mouseclick', start.x, start.y);
      mouse('mousemove', end.x, end.y);
      await wait();
      mouse('mouserelease', end.x, end.y);
      await wait();
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('├─ npm test -- --run ›\n└─ example.ts');
    } finally { test.close(); }
  });
  it('ends tool trees at reasoning, answers and new user turns without reusing stale tree positions', () => {
    const tool = (id: string) => message(id, 'agent', `Read the file \`src/${id}.ts\``, 'tool_use');
    const first = tool('one'), second = tool('two');
    const grouped = conversationBlocks([first, second]);
    expect(grouped[0].toolTree?.first).toBe(true);
    expect(grouped[1].toolTree?.last).toBe(true);
    for (const boundary of [message('t', 'agent', 'Reasoning', 'thinking'),
      message('a', 'agent', 'Answer', 'answer'), message('u', 'user', 'Question')]) {
      const separated = conversationBlocks([first, boundary, second]);
      expect(separated[0].toolTree).toBeUndefined();
      expect(separated[2].toolTree).toBeUndefined();
    }
    const extended = conversationBlocks([first, second, tool('three')]);
    expect(extended[1].toolTree?.last).toBe(false);
    expect(grouped[1].toolTree?.last).toBe(true);
  });
  it('shows Banner, sticks q1 over a1-a4, then q2 over a5-a7 and reverses on scroll', async () => {
    const test = harness([
      message('q1', 'user', 'q1 first question'),
      message('a1', 'agent', 'a1-a4 reply\n'.repeat(50), 'answer'),
      message('q2', 'user', 'q2 second question'),
      message('a5', 'agent', 'a5-a7 reply\n'.repeat(50), 'answer'),
    ], 30, 80, true);
    try {
      await wait();
      expect(test.frames.at(-1)).toContain('Siada CLI');
      key('g', { ctrl: true }); await wait();
      key('up'); await wait(); key('return'); await wait();
      key('wheeldown', { sequence: '\x1b[<65;40;10M' }); await wait();
      expect(test.frames.at(-1)!.split('\n')[0]).toContain('q1 first question');
      key('g', { ctrl: true }); await wait();
      key('return'); await wait();
      key('wheeldown', { sequence: '\x1b[<65;40;10M' }); await wait();
      expect(test.frames.at(-1)!.split('\n')[0]).toContain('q2 second question');
      key('up', { alt: true }); await wait();
      key('wheeldown', { sequence: '\x1b[<65;40;10M' }); await wait();
      expect(test.frames.at(-1)!.split('\n')[0]).toContain('q1 first question');
      key('home', { ctrl: true }); await wait();
      expect(test.frames.at(-1)!.split('\n')[0]).toContain('Siada CLI');
      expect(test.screen.display()).toContain('Siada CLI');
    } finally { test.close(); }
  });
  it('keeps stable fragments and does not split surrogate pairs', () => {
    const original = message('long', 'agent', '中文😀'.repeat(4000), 'answer');
    const first = conversationBlocks([original]);
    const second = conversationBlocks([original]);
    expect(first.map(block => block.message.content).join('')).toBe(original.content);
    expect(first[0]).toBe(second[0]);
    expect(first.every(block => block.message.content.length <= 3000)).toBe(true);
    expect(first.every(block => !/[\uD800-\uDBFF]$/.test(block.message.content))).toBe(true);
  });
  it.each([20, 24, 30, 43, 50, 60])('keeps the latest prompt and input visible at %i rows', async rows => {
    const messages = Array.from({ length: 100 }, (_, i) => [
      message(`u${i}`, 'user', `Prompt ${i}`),
      message(`a${i}`, 'agent', `Answer ${i}\n${'中文内容 '.repeat(25)}`, 'answer'),
    ]).flat();
    const test = harness(messages, rows, 48);
    try {
      await wait();
      const frame = test.frames.at(-1)!;
      expect(frame).toContain('Prompt 99');
      expect(frame).toContain('INPUT DRAFT');
      expect(test.screen.display()).toContain('Prompt');
      expect(test.screen.display()).toContain('INPUT DRAFT');
      expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
      key('pageup'); await wait();
      expect(test.frames.at(-1)).toContain('Prompt');
      expect(test.frames.at(-1)).toContain('回到底部');
      const footerRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('回到底部'));
      key('mousemove', { sequence: `\x1b[<35;2;${footerRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击回到最新回复');
      expect(test.screen.display()).toContain('点击回到最新回复');
      expect(test.frames.at(-1)!.split('\n').length).toBeLessThanOrEqual(rows - 1);
      key('mouseclick', { sequence: `\x1b[<0;2;${footerRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('Answer 99');
      expect(test.frames.at(-1)).not.toContain('回到底部');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });
  it('preserves browsing position when a reply grows and restores following explicitly', async () => {
    const messages = Array.from({ length: 15 }, (_, i) => [
      message(`u${i}`, 'user', `Prompt ${i}`),
      message(`a${i}`, 'agent', `Answer ${i}\nline\nline\nline`, 'answer'),
    ]).flat();
    const test = harness(messages);
    try {
      await wait(); key('pageup'); await wait();
      const updated = [...messages];
      updated[updated.length - 1] = { ...updated.at(-1)!, content: 'Growing reply\n'.repeat(40) };
      test.rerender(updated); await wait();
      expect(test.frames.at(-1)).toContain('有新回复');
      expect(test.frames.at(-1)).toContain('Prompt');
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('Growing reply');
      expect(test.frames.at(-1)).not.toContain('有新回复');
    } finally { test.close(); }
  });
  it('opens the user directory and jumps without replacing the pinned prompt', async () => {
    const test = harness([message('u1', 'user', 'First question'), message('a1', 'agent', 'First answer'),
      message('u2', 'user', 'Latest question'), message('a2', 'agent', 'Latest answer')]);
    try {
      await wait(); key('g', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('对话目录');
      key('up'); key('return'); await wait();
      expect(test.frames.at(-1)).toContain('First question');
      expect(test.frames.at(-1)).toContain('First answer');
    } finally { test.close(); }
  });
  it('expands only the clicked Thinking block and restores it independently', async () => {
    const test = harness([
      message('u', 'user', 'Pinned question'),
      message('t1', 'agent', 'Private reasoning one\nsecond line', 'thinking'),
      message('t2', 'agent', 'Private reasoning two\nsecond line', 'thinking'),
    ]);
    try {
      await wait();
      const lines = test.frames.at(-1)!.split('\n');
      const thinkingRow = lines.findIndex(line => line.includes('Private reasoning one'));
      expect(thinkingRow).toBeGreaterThan(0);
      key('mouseclick', { sequence: `\x1b[<0;2;${thinkingRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('Private reasoning one');
      expect(test.frames.at(-1)!.split('\n').filter(line => line.includes('second line'))).toHaveLength(1);
      key('mouseclick', { sequence: `\x1b[<0;2;${thinkingRow + 1}M` }); await wait();
      expect(test.frames.at(-1)!.split('\n').filter(line => line.includes('second line'))).toHaveLength(0);
    } finally { test.close(); }
  });
  it('expands all Thought lines when there is room and collapses them with a second click', async () => {
    const lines = Array.from({ length: 25 }, (_, index) => `Reasoning ${index + 1}: 中文推理内容`);
    const test = harness([
      message('u', 'user', 'Question'),
      message('t', 'agent', lines.join('\n'), 'thinking'),
      message('a', 'agent', 'Answer after reasoning', 'answer'),
    ], 60, 100);
    try {
      await wait();
      const row = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('Reasoning 1:'));
      key('mouseclick', { sequence: `\x1b[<0;2;${row + 1}M` }); await wait();
      for (const line of lines) expect(test.frames.at(-1)).toContain(line);
      expect(test.frames.at(-1)).toContain('Answer after reasoning');
      expect(test.screen.display()).toContain('Reasoning 25: 中文推理内容');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      key('mouseclick', { sequence: `\x1b[<0;2;${row + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('› Reasoning 1:');
      expect(test.frames.at(-1)).not.toContain('Reasoning 25:');
    } finally { test.close(); }
  });
  it.each([20, 24, 30])('scrolls the conversation over fully expanded Thought at %i rows', async rows => {
    const test = harness([
      message('u', 'user', 'Question'),
      message('t', 'agent', Array.from({ length: 40 }, (_, index) => `Reasoning line ${index + 1}`).join('\n'), 'thinking'),
      message('a', 'agent', 'Answer after reasoning', 'answer'),
    ], rows, 48);
    try {
      await wait();
      const row = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('Reasoning line 1'));
      key('mouseclick', { sequence: `\x1b[<0;2;${row + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('› Reasoning line 1');
      expect(test.frames.at(-1)).toContain('Reasoning line 1');
      expect(test.frames.at(-1)).not.toContain('Reasoning line 40');
      const firstReasoningRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('Reasoning line 1'));
      key('wheeldown', { sequence: `\x1b[<65;3;${firstReasoningRow + 1}M` }); await wait();
      const shiftedRow = test.frames.at(-1)!.split('\n').findIndex(line => line.startsWith('› Reasoning line 1'));
      expect(shiftedRow).toBeLessThan(row);
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('Reasoning line 40');
      expect(test.frames.at(-1)).toContain('Answer after reasoning');
      expect(test.screen.display()).toContain('Reasoning line 40');
      expect(test.frames.at(-1)!.split('\n').length).toBeLessThanOrEqual(rows - 1);
    } finally { test.close(); }
  });
  it.each(['dark', 'light'] as const)('highlights headings on hover without repeated redraws in %s mode', async theme => {
    const originalColorLevel = chalk.level;
    chalk.level = 3;
    setActiveTheme(theme);
    const test = harness([
      message('u', 'user', 'Question'),
      message('t', 'agent', 'Reasoning body\nsecond line', 'thinking'),
      message('tool', 'agent', 'Run the following command:\n```bash\nprintf synthetic\n```', 'tool_use'),
    ]);
    try {
      await wait();
      const thinkingRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('Reasoning body'));
      const accent = colors.info.slice(1).match(/../g)!.map(value => parseInt(value, 16)).join(';');
      // The affordance is already in the tool accent before the pointer arrives
      // so the row reads as clickable; only the bold weight waits for the hover.
      const resting = test.rawFrames.at(-1)!.split('\n')[thinkingRow];
      expect(resting.match(new RegExp(`38;2;${accent}m[›⌄]`, 'g'))).toHaveLength(2);
      expect(resting).not.toContain('\x1b[1m');
      key('mousemove', { sequence: `\x1b[<35;2;${thinkingRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开思考内容');
      expect(test.frames.at(-1)).not.toContain('second line');
      expect(test.rawFrames.at(-1)!.split('\n')[thinkingRow]).toMatch(/\x1b\[(?:\d+;)*4(?:;\d+)*m/);
      const emphasized = test.rawFrames.at(-1)!.split('\n')[thinkingRow];
      const hint = test.rawFrames.at(-1)!.split('\n').find(line => line.includes('点击展开思考内容'))!;
      const neutral = theme === 'dark' ? colors.white : colors.gray[900];
      const rgb = neutral.slice(1).match(/../g)!.map(value => parseInt(value, 16)).join(';');
      expect(emphasized).toContain(`38;2;${rgb}m`);
      expect(hint).toContain(`38;2;${rgb}m`);
      // The disclosure glyphs are the only cells in the tool accent: they
      // advertise the clickable row, while the label keeps the neutral tone.
      expect(emphasized.split(`38;2;${accent}m`)).toHaveLength(3);
      expect(emphasized.match(new RegExp(`38;2;${accent}m[›⌄]`, 'g'))).toHaveLength(2);
      expect(hint).not.toContain(`38;2;${accent}m`);
      const count = test.frames.length;
      key('mousemove', { sequence: `\x1b[<35;10;${thinkingRow + 1}M` }); await wait();
      expect(test.frames).toHaveLength(count);
      key('mouseclick', { sequence: `\x1b[<0;2;${thinkingRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('Reasoning body');
      expect(test.frames.at(-1)).toContain('点击收起思考内容');
      // Expanded rows swap the disclosure glyph to `⌄` and keep the hover tint.
      expect(test.rawFrames.at(-1)!.split('\n')[thinkingRow]).toContain(`38;2;${accent}m⌄`);
      const toolRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('printf synthetic'));
      expect(toolRow).toBeGreaterThan(thinkingRow);
      key('mousemove', { sequence: `\x1b[<35;2;${toolRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开工具详情');
      expect(test.rawFrames.at(-1)!.split('\n')[thinkingRow]).not.toMatch(/\x1b\[(?:\d+;)*4(?:;\d+)*m/);
      const inputRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('INPUT DRAFT'));
      key('mousemove', { sequence: `\x1b[<35;2;${inputRow + 1}M` }); await wait();
      expect(test.frames.at(-1)).not.toContain('点击');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      expect(test.frames.at(-1)).not.toContain('最新回复');
    } finally { test.close(); chalk.level = originalColorLevel; setActiveTheme('dark'); }
  });
  it('clears hover when scrolling moves a heading away and restores it under a stationary pointer', async () => {
    const test = harness([
      message('u', 'user', 'Question'),
      message('a', 'agent', 'Answer line\n'.repeat(50), 'answer'),
      message('t', 'agent', 'Reasoning body', 'thinking'),
    ]);
    try {
      await wait();
      const row = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('Reasoning body'));
      key('mousemove', { sequence: `\x1b[<35;2;${row + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开思考内容');
      key('pageup'); await wait();
      expect(test.frames.at(-1)).not.toContain('点击展开思考内容');
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('点击展开思考内容');
    } finally { test.close(); }
  });
  it('previews directory entries without changing keyboard selection and ignores clicks outside its width', async () => {
    const test = harness([
      message('u1', 'user', 'First question'), message('a1', 'agent', 'First answer'),
      message('u2', 'user', 'Latest question'), message('a2', 'agent', 'Latest answer'),
    ]);
    try {
      await wait(); key('g', { ctrl: true }); await wait();
      key('mousemove', { sequence: '\x1b[<35;2;2M' }); await wait();
      expect(test.frames.at(-1)).toContain('点击查看第 1 轮对话');
      expect(test.frames.at(-1)).toContain('› 2. Latest question');
      key('mousemove', { sequence: '\x1b[<35;81;2M' }); await wait();
      expect(test.frames.at(-1)).not.toContain('点击查看');
      key('mouseclick', { sequence: '\x1b[<0;81;2M' }); await wait();
      expect(test.frames.at(-1)).toContain('对话目录');
      key('mouseclick', { sequence: '\x1b[<0;2;2M' }); await wait();
      expect(test.frames.at(-1)).toContain('First answer');
      expect(test.frames.at(-1)).not.toContain('对话目录');
    } finally { test.close(); }
  });
  it('prioritizes the pinned question over clipped headings and clears hover while inactive', async () => {
    const messages = [
      message('u', 'user', 'Pinned question\n'.repeat(10)),
      message('t', 'agent', 'Reasoning body', 'thinking'),
      message('a', 'agent', 'Answer line\n'.repeat(40), 'answer'),
    ];
    const test = harness(messages);
    try {
      await wait();
      expect(test.chunks.join('')).toContain('\x1b[?1007l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h');
      expect(test.chunks.join('')).toContain('\x1b]22;default\x1b\\');
      key('mousemove', { sequence: '\x1b[<35;2;1M' }); await wait();
      expect(test.frames.at(-1)).toContain('点击查看完整问题');
      key('mouseclick', { sequence: '\x1b[<0;2;1M' }); await wait();
      expect(test.frames.at(-1)).toContain('Pinned question');
      expect(test.frames.at(-1)).toContain('Reasoning body ›');
      test.rerender(messages, false); await wait();
      expect(test.frames.at(-1)).not.toContain('点击查看完整问题');
      expect(test.chunks.join('')).toContain('\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?1006l\x1b[?1007l');
      expect(test.chunks.join('')).toContain('\x1b]22;\x1b\\');
    } finally { test.close(); }
  });
  it('does not pin pending or failed sends', async () => {
    const original = message('u1', 'user', 'Confirmed question');
    const pending = { ...message('u2', 'user', 'Pending question'), metadata: { sendPending: true } };
    const test = harness([original, pending]);
    try {
      await wait();
      expect(test.frames.at(-1)).toContain('Confirmed question');
      test.rerender([original, { ...pending, metadata: { sendFailed: true } }]); await wait();
      expect(test.frames.at(-1)).toContain('Confirmed question');
      test.rerender([original, { ...pending, metadata: { sendPending: false } }]); await wait();
      expect(test.frames.at(-1)).toContain('Pending question');
    } finally { test.close(); }
  });
  it('opens the full pinned question in history and uses conversation scrolling', async () => {
    const prompt = Array.from({ length: 40 }, (_, i) => `Pinned line ${i}`).join('\n');
    const test = harness([message('u', 'user', prompt), message('a', 'agent', 'Answer body', 'answer')], 20, 48);
    try {
      await wait();
      key('mouseclick', { sequence: '\x1b[<0;2;1M' }); await wait();
      const expanded = test.frames.at(-1)!;
      expect(expanded).toContain('Pinned line 2');
      key('wheeldown', { sequence: '\x1b[<65;2;2M' }); await wait();
      expect(test.frames.at(-1)).toContain('Pinned line 4');
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('Pinned line 39');
      expect(test.frames.at(-1)).toContain('Answer body');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      expect(test.frames.at(-1)!.split('\n').length).toBeLessThanOrEqual(19);
    } finally { test.close(); }
  });
  it.each([24, 60])('expands file-edit diffs fully and scrolls history over them at %i rows', async rows => {
    const content = `Edit file example.ts\n<!-- siada-file-edit:start -->\n${JSON.stringify({
      callId: 'edit-example', action: 'update', path: 'example.ts', status: 'completed',
      oldString: '', newString: Array.from({ length: 25 }, (_, index) => `const value${index + 1} = ${index + 1};`).join('\n'),
    })}\n<!-- siada-file-edit:end -->`;
    const test = harness([
      message('u', 'user', 'Question'),
      message('edit', 'agent', content, 'tool_use'),
      message('a', 'agent', 'Answer after edit', 'answer'),
    ], rows, 100);
    try {
      await wait();
      const row = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('Edit file example.ts'));
      key('mouseclick', { sequence: `\x1b[<0;2;${row + 1}M` }); await wait();
      expect(test.frames.at(-1)).toContain('const value1 = 1;');
      if (rows === 60) expect(test.frames.at(-1)).toContain('const value25 = 25;');
      const before = test.frames.at(-1);
      const diffRow = test.frames.at(-1)!.split('\n').findIndex(line => line.includes('const value1 = 1;'));
      key('wheeldown', { sequence: `\x1b[<65;4;${diffRow + 1}M` }); await wait();
      if (rows === 24) expect(test.frames.at(-1)).not.toBe(before);
      key('end', { ctrl: true }); await wait();
      expect(test.frames.at(-1)).toContain('const value25 = 25;');
      expect(test.frames.at(-1)).toContain('Answer after edit');
      expect(test.frames.at(-1)).toContain('INPUT DRAFT');
      expect(test.frames.at(-1)!.split('\n').length).toBeLessThanOrEqual(rows - 1);
    } finally { test.close(); }
  });
});