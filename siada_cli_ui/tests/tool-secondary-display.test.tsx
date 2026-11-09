import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConversationViewport } from '../src/components/Chat/ConversationViewport.js';
import { parseToolCall } from '../src/utils/toolCallParser.js';
import { getSemanticToolCallDisplay } from '../src/utils/toolCallDisplay.js';
import { setActiveTheme } from '../src/themes/index.js';
import { colors } from '../src/utils/colors.js';
import type { Message } from '../src/types/index.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void) => {
    React.useEffect(() => {
      handlers.add(handler);
      return () => { handlers.delete(handler); };
    }, [handler]);
  }};
});
vi.mock('../src/utils/clipboard.js', () => ({ copySelectionToClipboard: vi.fn() }));
const pause = () => new Promise(resolve => setTimeout(resolve, 80));
const message = (id: string, content: string): Message => ({
  id, type: 'agent', content, author: 'Synthetic', timestamp: '2026-01-01T00:00:00Z',
  metadata: { subtype: 'tool_use', streamEnd: true },
});
function edit(action: string, status: string, extra = {}) {
  return message(action, `File edit: ${action} src/${action}.ts\n<!-- siada-file-edit:start -->\n${JSON.stringify({
    callId: action, action, path: `src/${action}.ts`, status, ...extra,
  })}\n<!-- siada-file-edit:end -->`);
}
function mount(messages: Message[], columns = 80, collapsed = true) {
  const stdout = Object.assign(new PassThrough(), { rows: 50, columns });
  const screen = new TerminalScreen(50, columns);
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  let raw = '';
  const app = render(<Box height={49} width={columns} flexDirection="column">
    <ConversationViewport messages={messages} width={columns} height={46}
      isCollapsed={collapsed} presentation />
    <Text>INPUT DRAFT</Text>
  </Box>, { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false,
    maxFps: 0, onRender: ({ output }) => { raw = output; } });
  return {
    text: () => screen.display(), raw: () => raw,
    async click(label: string) {
      const lines = screen.display().split('\n');
      const row = lines.findIndex(line => line.includes(label));
      expect(row).toBeGreaterThanOrEqual(0);
      const column = lines[row].indexOf(lines[row].trimStart()) + 2;
      for (const release of [false, true]) {
        const key: Key = { name: release ? 'mouserelease' : 'mouseclick', ctrl: false, cmd: false,
          alt: false, shift: false, insertable: false,
          sequence: `\x1b[<0;${column};${row + 1}${release ? 'm' : 'M'}` };
        [...handlers].forEach(handler => handler(key));
      }
      await pause();
    },
    close() { app.unmount(); app.cleanup(); },
  };
}
afterEach(() => { setActiveTheme('dark'); });

describe('secondary tool display regressions', () => {
  it.each(['dark', 'light'] as const)('uses secondary color for the Search branch and query in %s', async theme => {
    chalk.level = 3;
    setActiveTheme(theme);
    const scene = mount([
      message('read', 'Read the file `src/a.ts`'),
      message('search', 'Search for: needle in src with file pattern *.ts in /tmp/project'),
    ]);
    try {
      await pause();
      const line = scene.raw().split('\n').find(line => line.includes('Search "needle"'));
      expect(line).toContain(chalk.hex(colors.content.secondary)('X').split('X')[0]);
      // The muted tree row keeps its secondary tone everywhere except the
      // disclosure glyph, which stays in the tool accent so it reads clickable.
      const accentOpen = chalk.hex(colors.info)('X').split('X')[0];
      const withoutArrow = line.replace(`${accentOpen} ›`, '').replace(`${accentOpen}›`, '');
      expect(withoutArrow).not.toContain(accentOpen);
      expect(line).not.toContain('\x1b[1m');
      expect(scene.text()).toContain('Search "needle" in src');
    } finally { scene.close(); }
  });

  it.each(['create', 'undo', 'update'])('retains %s failure and pending status behind its disclosure', async action => {
    for (const [status, extra, text] of [
      ['failed', { error: 'REJECTED_OPERATION' }, 'REJECTED_OPERATION'],
      ['pending', {}, 'Waiting for tool result'],
      ['unverified', { details: 'RESULT_UNAVAILABLE' }, 'RESULT_UNAVAILABLE'],
      ['completed', { oldString: 'same', newString: 'same' }, 'Applied without text changes'],
    ] as const) {
      const scene = mount([edit(action, status, extra)], 40);
      try {
        await pause();
        expect(scene.text()).toContain('›');
        await scene.click(`${action}.ts`);
        expect(scene.text()).toContain(text);
        expect(scene.text()).not.toContain('siada-file-edit');
        await scene.click(`${action}.ts`);
        expect(scene.text()).not.toContain(text);
      } finally { scene.close(); }
    }
  });

  it.each(['create', 'undo', 'update'])('shows completed %s diff in the production viewport', async action => {
    const scene = mount([edit(action, 'completed', { oldString: 'old_value', newString: 'new_value' })], 40);
    try {
      await pause();
      expect(scene.text()).not.toContain('new_value');
      await scene.click(`${action}.ts`);
      expect(scene.text()).toContain('old_value');
      expect(scene.text()).toContain('new_value');
    } finally { scene.close(); }
  });

  it.each([
    'Save to memory [add/memory]: ',
    'Fact memory [add/project] ',
    'Fact memory [update] #7 ',
    'Fact feedback #7 correct: ',
  ])('preserves full multiline details once when expanding %s', async prefix => {
    const content = 'FIRST_LINE\n' + 'long_content_'.repeat(8) + '\nFINAL_TAIL';
    const parsed = parseToolCall(prefix + content)!;
    expect(parsed.details).toBe(content);
    expect(getSemanticToolCallDisplay(parsed)?.fields.at(-1)?.value).toBe(content);
    for (const grouped of [false, true]) {
      const items = [message('m', prefix + content)];
      if (grouped) items.unshift(message('read', 'Read the file `src/a.ts`'));
      const scene = mount(items, 40);
      try {
        await pause();
        expect(scene.text()).not.toContain('FINAL_TAIL');
        await scene.click('›');
        expect(scene.text().match(/FIRST_LINE/g)).toHaveLength(1);
        expect(scene.text()).toContain('FINAL_TAIL');
        expect(scene.text()).toContain('INPUT DRAFT');
        const lines = scene.text().split('\n');
        const first = lines.findIndex(line => line.includes('FIRST_LINE'));
        const last = lines.findIndex(line => line.includes('FINAL_TAIL'));
        expect(last).toBeGreaterThan(first);
      } finally { scene.close(); }
    }
  });

  it.each([
    'FIRST_QUERY\nSECOND_QUERY',
    'ToolPromptView|ConversationViewport|\nsecondary|expandable',
    '(?x)\nsecondary\n| expandable\n| memory\n',
  ])('recognizes multiline search expressions without a raw prompt fallback: %s', async query => {
    const content = `Search for: ${query} in src with file pattern *.ts in /tmp/project`;
    expect(parseToolCall(content)?.query?.trim()).toBe(query.trim());
    const scene = mount([message('s', content)], 40);
    try {
      await pause();
      expect(scene.text().replace(/\s/g, '').split(query.replace(/\s/g, '')).length - 1).toBe(1);
      expect(scene.text()).not.toContain('Search for:');
      expect(scene.text()).not.toMatch(/[╭╮╰╯]/);
      await scene.click('Search');
      expect(scene.text()).toContain('cwd: /tmp/project');
    } finally { scene.close(); }
  });
});