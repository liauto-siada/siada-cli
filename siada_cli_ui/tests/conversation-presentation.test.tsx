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
import { setActiveTheme } from '../src/themes/index.js';
import { colors } from '../src/utils/colors.js';
import { setUiLanguage } from '../src/i18n/index.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import { renderConversationToText } from '../src/utils/conversationExport.js';
import { isErrorMessage } from '../src/utils/errorMessage.js';
import { MessageList } from '../src/components/Chat/MessageList.js';

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
vi.mock('../src/utils/clipboard.js', () => ({
  copySelectionToClipboard: vi.fn().mockResolvedValue('native'),
}));
const pause = () => new Promise(resolve => setTimeout(resolve, 70));
const message = (id: string, content: string, subtype: string, metadata = {}): Message => ({
  id, type: 'agent', content, author: 'Synthetic', timestamp: '2026-01-01T00:00:00Z',
  metadata: { subtype, ...metadata },
});
const command = (id: string, body: string) => message(id,
  `Run the following command:\n\`\`\`bash\n${body}\n\`\`\`\ntimeout:60s`, 'tool_use');
const point = (name: string, x: number, y: number) => {
  const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false, insertable: false,
    sequence: `\x1b[<${name === 'mousemove' ? 35 : 0};${x};${y}${name === 'mouserelease' ? 'm' : 'M'}` };
  [...handlers].forEach(handler => handler(event));
};
function harness(messages: Message[], columns = 80, presentation = false, rows = 43, inputTip?: string) {
  const stdout = Object.assign(new PassThrough(), { rows, columns });
  const screen = new TerminalScreen(rows, columns);
  let frame = '', raw = '';
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  const app = render(<Box height={rows - 1} width={columns} flexDirection="column">
    <ConversationViewport messages={messages} width={columns} height={rows - 4} isCollapsed
      presentation={presentation} inputTip={inputTip} />
    <Text>INPUT DRAFT</Text>
  </Box>, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { raw = output; frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  return {
    get frame() { return frame; }, get raw() { return raw; }, screen,
    async click(text: string) {
      const lines = frame.split('\n');
      const row = lines.findIndex(line => line.includes(text));
      expect(row).toBeGreaterThanOrEqual(0);
      const x = lines[row].indexOf(lines[row].trimStart()) + 2;
      point('mouseclick', x, row + 1);
      point('mouserelease', x, row + 1);
      await pause();
    },
    close() { app.unmount(); app.cleanup(); },
  };
}

function activityHarness(messages: Message[] = [], columns = 100, rows = 24) {
  const stdout = Object.assign(new PassThrough(), { rows, columns });
  const screen = new TerminalScreen(rows, columns);
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  let frame = '';
  const view = (activityLabel?: string, interruptNotice?: string, externalHoverTip?: string) =>
    <Box height={rows - 1} width={columns}>
      <ConversationViewport messages={messages} width={columns} height={rows - 4} isCollapsed
        presentation activityLabel={activityLabel} interruptNotice={interruptNotice}
        externalHoverTip={externalHoverTip} />
    </Box>;
  const app = render(view('Thinking…'), {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  return {
    get frame() { return frame; }, screen,
    update(label?: string, notice?: string, hoverTip?: string) { app.rerender(view(label, notice, hoverTip)); },
    close() { app.unmount(); app.cleanup(); },
  };
}

describe('conversation summaries and detail surfaces', () => {
  it('keeps legacy hook and error notices out of compact tool aggregation', async () => {
    const messages = [
      command('before', 'npm run build'),
      message('hook', 'Read the file `hook.txt` from line 1 to line 2', 'tool_use',
        { eventType: 'hook', hookEvent: 'PreToolUse', hookStatus: 'notification' }),
      message('error', 'Read the file `error.txt` from line 1 to line 2', 'tool_use',
        { eventType: 'error' }),
      command('after', 'npm test'),
    ];
    const stdout = Object.assign(new PassThrough(), { rows: 43, columns: 80 });
    let frame = '';
    setUiLanguage('en');
    const app = render(<MessageList messages={messages} noStatic isCollapsed terminalWidth={80} />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await pause();
      expect(frame).toContain('Hook · PreToolUse · Notice');
      expect(frame).toContain('● Error');
      expect(frame).toContain('Read the file `hook.txt` from line 1 to line 2');
      expect(frame).toContain('Read the file `error.txt` from line 1 to line 2');
    } finally {
      app.unmount(); app.cleanup(); setUiLanguage('zh-CN');
    }
  });

  it.each(['notification', 'blocked', 'stopped'])('renders %s hooks separately in both modes and exports their identity', async status => {
    const hook = message('hook', 'Synthetic hook notice\nSecond line', 'hook',
      { hookEvent: 'PreToolUse', hookStatus: status, eventType: 'hook' });
    const label = status === 'blocked' ? 'Blocked' : status === 'stopped' ? 'Stopped' : 'Notice';
    const messages = [command('before', 'npm run build'), hook, command('after', 'npm test')];
    setUiLanguage('en');
    try {
      expect(isErrorMessage({ ...hook, type: 'error' })).toBe(false);
      expect(await renderConversationToText(messages)).toContain(`Hook · PreToolUse · ${label}`);
      for (const presentation of [false, true]) {
        const blocks = conversationBlocks(messages, presentation);
        expect(blocks).toHaveLength(3);
        expect(blocks.every(block => !block.toolTree)).toBe(true);
        const test = harness(messages, 48, presentation, 24);
        try {
          await pause();
          expect(test.frame).toContain(`Hook · PreToolUse · ${label}`);
          expect(test.frame).toContain('Synthetic hook notice');
          expect(test.frame).toContain('Second line');
          expect(test.frame).not.toContain('● Error');
          expect(test.frame.split('\n').every(line => stringWidth(line) <= 48)).toBe(true);
        } finally { test.close(); }
      }
    } finally { setUiLanguage('zh-CN'); }
  });

  it('leaves the default footer empty in both languages while retaining contextual tips', async () => {
    try {
      for (const language of ['en', 'zh-CN'] as const) {
        setUiLanguage(language);
        for (const presentation of [false, true]) {
          const test = harness([], 80, presentation, 24);
          try {
            await pause();
            expect(test.frame).not.toMatch(/Ctrl\+G|Ctrl\+Home|Latest reply|最新回复/);
            expect(test.frame).toContain('INPUT DRAFT');
          } finally { test.close(); }
        }
        const test = harness([], 80, true, 24, 'Clipboard reading notice');
        try {
          await pause();
          expect(test.frame).toContain('Clipboard reading notice');
        } finally { test.close(); }
      }
    } finally { setUiLanguage('zh-CN'); }
  });

  it.each(['error', 'legacy'])('renders %s errors separately from adjacent tools in both transcript modes', async kind => {
    const error = message('error', 'The system is currently experiencing high demand.\nPlease retry later.',
      kind === 'legacy' ? 'tool_use' : 'error', kind === 'legacy' ? { eventType: 'error' } : {});
    const messages = [command('run', 'npm run build'),
      message('read', 'Read the file `src/app.ts` from line 1 to line 20', 'tool_use'),
      error, command('after-error', 'npm test')];
    const originalLevel = chalk.level;
    chalk.level = 3;
    setUiLanguage('en');
    try {
      for (const presentation of [false, true]) {
        const blocks = conversationBlocks(messages, presentation);
        expect(blocks[1].toolTree?.last).toBe(true);
        expect(blocks[2].toolTree).toBeUndefined();
        expect(blocks[3].toolTree).toBeUndefined();
        const test = harness(messages, 80, presentation);
        try {
          await pause();
          expect(test.screen.display()).toContain('● Error');
          expect(test.screen.display()).toContain('The system is currently experiencing high demand.');
          expect(test.screen.display()).toContain('Please retry later.');
          expect(test.screen.display()).not.toMatch(/[└├]─ The system/);
          expect(test.raw).toContain(chalk.hex(colors.error)('●').replace(/\x1b\[39m$/, ''));
          await test.click('Error');
          expect(test.screen.display()).toContain('Please retry later.');
        } finally { test.close(); }
      }
    } finally { chalk.level = originalLevel; setUiLanguage('zh-CN'); }
  });

  it.each([[20, 48], [24, 80], [43, 100]])(
    'preserves activity and elapsed time across changing hover hints at %i×%i',
    async (rows, columns) => {
      const test = activityHarness([message('thought', 'Inspect the project.', 'thinking')], columns, rows);
      try {
        await new Promise(resolve => setTimeout(resolve, 1150));
        const row = test.frame.split('\n').findIndex(line => line.includes('Inspect the project.'));
        point('mousemove', 2, row + 1); await pause();
        expect(test.screen.display()).toContain('◉ Thinking… (1s)');
        expect(test.screen.display()).toMatch(/expand Thought|展开思考内容/);
        point('mousemove', columns, rows); await pause();
        for (const [label, tip] of [
          ['Thinking…', 'Click to view Goal'],
          ['Executing tools…', 'Click to view Todo'],
          ['Compacting context…', 'Click to view Agents'],
        ]) {
          test.update(label, undefined, tip); await pause();
          const footer = test.screen.display().split('\n').find(line => line.includes(label));
          expect(footer).toContain(`${label} (1s)`);
          expect(footer).toContain('Click to');
        }
        test.update('Thinking…'); await pause();
        expect(test.screen.display()).toContain('◉ Thinking… (1s)');
        expect(test.screen.display()).not.toContain('Click to view Agents');
      } finally { test.close(); }
    },
  );
  it.each([[20, 48], [24, 80], [43, 100]])(
    'keeps the hover action beside the centered bottom button at %i×%i',
    async (rows, columns) => {
      const test = harness([
        message('thought', 'Inspect the project.', 'thinking'),
        message('answer', 'History line\n'.repeat(80), 'answer'),
      ], columns, true, rows);
      try {
        await pause();
        const event: Key = { name: 'home', ctrl: true, cmd: false, alt: false,
          shift: false, insertable: false, sequence: '\x1b[1;5H' };
        [...handlers].forEach(handler => handler(event));
        await pause();
        const row = test.frame.split('\n').findIndex(line => line.includes('Inspect the project.'));
        point('mousemove', 2, row + 1); await pause();
        const lines = test.screen.display().split('\n');
        const tip = '点击展开思考内容';
        const footer = lines.find(line => line.includes(tip))!;
        expect(footer).toBeDefined();
        const button = columns < 100 ? '↓ 底部' : '↓ 回到底部 · Esc';
        expect(footer).toContain(button);
        expect(stringWidth(footer.slice(0, footer.indexOf(tip)))).toBeGreaterThanOrEqual(
          stringWidth(footer.slice(0, footer.indexOf(button))) + stringWidth(button));
      } finally { test.close(); }
    },
  );
  it('shows the hovered action ahead of an input hint and restores that hint on mouse leave', async () => {
    const test = harness([message('thought', 'Inspect the project.', 'thinking')], 80, true, 24, 'Text pasted');
    try {
      await pause();
      expect(test.frame).toContain('Text pasted');
      const row = test.frame.split('\n').findIndex(line => line.includes('Inspect the project.'));
      point('mousemove', 2, row + 1); await pause();
      expect(test.frame).toContain('点击展开思考内容');
      expect(test.frame).not.toContain('Text pasted');
      point('mousemove', 80, 24); await pause();
      expect(test.frame).not.toContain('点击展开思考内容');
      expect(test.frame).toContain('Text pasted');
    } finally { test.close(); }
  });
  it('keeps parent mouse reporting enabled after an embedded detail viewport closes', async () => {
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 80 });
    let output = '';
    stdout.on('data', chunk => { output += chunk.toString(); });
    const view = (detail: boolean) => <Box flexDirection="column">
      <ConversationViewport messages={[]} width={80} height={10} isCollapsed
        active={false} composerActive={false} keepMouseTracking />
      {detail && <ConversationViewport messages={[]} width={80} height={8} isCollapsed />}
    </Box>;
    const app = render(view(false), {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });
    try {
      await pause();
      app.rerender(view(true)); await pause();
      app.rerender(view(false)); await pause();
      expect(output.lastIndexOf('\x1b[?1006h'))
        .toBeGreaterThan(output.lastIndexOf('\x1b[?1006l'));
    } finally { app.unmount(); app.cleanup(); }
    expect(output).toContain('\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?1006l\x1b[?1007l');
    expect(output).toContain('\x1b]22;\x1b\\');
  });
  it('separates agent updates while keeping commands in the same tool tree together', async () => {
    const messages: Message[] = [
      { ...message('user', '分析当前项目', 'answer'), type: 'user' },
      message('thinking', 'Inspect the project.', 'thinking'),
      message('progress', '我会先看项目结构。', 'process'),
      command('run', 'pwd'),
      command('run-next', 'git status --short'),
      message('read', 'Read the file `README.md`', 'tool_use'),
      message('answer', '分析完成。', 'answer'),
      { ...message('next-user', '再看测试', 'answer'), type: 'user' },
    ];
    expect(conversationBlocks(messages, true).map(block => block.gapAfter))
      .toEqual([1, 1, 1, 0, 0, 1, 1, 1]);
    const test = harness(messages, 100, true);
    try {
      await pause();
      const lines = test.frame.split('\n');
      const progressRow = lines.findIndex(line => line.includes('我会先看项目结构。'));
      const thoughtRow = lines.findIndex(line => line.includes('Inspect the project.'));
      const toolRow = lines.findIndex(line => line.includes('Run 2 commands'));
      const firstCommandRow = lines.findIndex(line => line.includes('├─ pwd'));
      const secondCommandRow = lines.findIndex(line => line.includes('├─ git status --short'));
      const readRow = lines.findIndex(line => line.includes('README.md'));
      const answerRow = lines.findIndex(line => line.includes('分析完成。'));
      expect(progressRow).toBeGreaterThanOrEqual(0);
      // Process messages include a status heading before their content.
      expect(progressRow).toBe(thoughtRow + 3);
      expect(lines[progressRow - 2].trim()).toBe('');
      expect(toolRow).toBe(progressRow + 2);
      expect(lines[toolRow - 1].trim()).toBe('');
      expect(firstCommandRow).toBe(toolRow + 1);
      expect(secondCommandRow).toBe(firstCommandRow + 1);
      expect(readRow).toBe(secondCommandRow + 1);
      expect(answerRow).toBe(readRow + 2);
      expect(lines[answerRow - 1].trim()).toBe('');
    } finally { test.close(); }
  });

  it('keeps the elapsed turn time across activity changes and temporary notices, then resets', async () => {
    const test = activityHarness();
    try {
      await new Promise(resolve => setTimeout(resolve, 1150));
      expect(test.frame).toMatch(/◉ Thinking… \(1s\)/);
      test.update('Executing tools…');
      await pause();
      expect(test.frame).toMatch(/◉ Executing tools… \(1s\)/);
      test.update('Executing tools…', 'Interrupted');
      await pause();
      expect(test.frame).not.toContain('Executing tools…');
      test.update('Thinking…');
      await pause();
      expect(test.frame).toMatch(/◉ Thinking… \(1s\)/);
      test.update();
      await pause();
      test.update('Thinking…');
      await pause();
      expect(test.frame).toContain('◉ Thinking…');
      expect(test.frame).not.toMatch(/Thinking… \([1-9]\d*s\)/);
    } finally { test.close(); }
  });

  it.each(['Thinking…', 'Executing tools…', 'Compacting context…'])(
    'keeps %s and elapsed time visible while hovering the return-to-bottom control',
    async label => {
      const test = activityHarness([message('answer', 'History line\n'.repeat(60), 'answer')]);
      try {
        test.update(label);
        await new Promise(resolve => setTimeout(resolve, 1150));
        const event: Key = { name: 'pageup', ctrl: false, cmd: false, alt: false, shift: false,
          insertable: false, sequence: '\x1b[5~' };
        [...handlers].forEach(handler => handler(event));
        await pause();
        const lines = test.frame.split('\n');
        const row = lines.findIndex(line => line.includes('回到底部'));
        expect(row).toBeGreaterThanOrEqual(0);
        const x = stringWidth(lines[row].slice(0, lines[row].indexOf('回到底部'))) + 1;
        expect(lines[row]).toContain(`${label} (1s)`);
        point('mousemove', x, row + 1);
        await pause();
        expect(test.frame.split('\n')[row]).toContain(`${label} (1s)`);
        expect(test.frame.split('\n')[row]).toContain('回到底部');
        point('mouseclick', x, row + 1);
        point('mouserelease', x, row + 1);
        await pause();
        expect(test.frame).not.toContain('回到底部');
        expect(test.frame).toContain(label);
      } finally { test.close(); }
    },
  );

  it.each([
    ['read', 'Read the file `src/a.ts` from line 1 to line 80', 'src/a.ts'],
    ['directory', 'View the directory `src`', 'src'],
    ['create', 'Create the file `src/new.ts` with the following content:\nhello', 'src/new.ts'],
    ['update', 'In the file `src/a.ts`, replace old with new', 'src/a.ts'],
    ['undo', 'Undo the last edit for the file `src/a.ts`', 'src/a.ts'],
    ['command', 'Run the following command:\n```bash\nprintf ok\n```', 'printf ok'],
    ['powershell', 'Run the following PowerShell command:\n```powershell\nWrite-Output ok\n```', 'Write-Output'],
    ['search', 'Search for: needle in src with file pattern *.ts', 'needle'],
    ['analyze', 'Analyze definitions in `src/a.ts`', 'src/a.ts'],
    ['web', 'Web search: synthetic query', 'synthetic'],
    ['browser', '> Siada will open synthetic page', 'synthetic'],
    ['memory-search', 'Searching memory: needle', 'needle'],
    ['memory-write', 'Save to memory: FactA', 'FactA'],
    ['fact-store', 'Fact memory search project', 'project'],
    ['fact-feedback', 'Fact feedback helpful', 'helpful'],
    ['subagent', 'Sub-agent task: inspect project', 'inspect'],
    ['patch', 'Apply patch: 1 file changed\nsrc/a.ts', 'Patch(1 file)'],
    ['lark', 'Send Lark synthetic message', 'synthetic'],
    ['plan', '✓  Done task\n\n[1/1 completed]', 'Plan completed'],
    ['unknown', 'Unknown synthetic tool content', 'Unknown synthetic'],
  ])('renders production presentation tool %s without breaking the composer', async (name, content, expected) => {
    const test = harness([message(name, content, 'tool_use', { streamEnd: true })], 100, true);
    try {
      await pause();
      expect(test.frame).toContain(expected);
      expect(test.frame).toContain('INPUT DRAFT');
      expect(test.frame.split('\n').length).toBeLessThanOrEqual(42);
      expect(test.frame).not.toContain('TypeError');
    } finally { test.close(); }
  });
  it('shows a single-line MCP notice once while retaining tool details', async () => {
    const notice = 'MCP: Configuration validated with 1 servers';
    const test = harness([
      message('mcp', notice, 'tool_use', { streamEnd: true }),
      message('progress', 'Ready to run tools.', 'process'),
      command('run', 'pwd'),
    ], 100, true);
    try {
      await pause();
      expect(test.frame.match(/MCP: Configuration validated with 1 servers/g)).toHaveLength(1);
      expect(test.frame).toContain('● ' + notice);
      expect(test.frame).toContain('● Run pwd');
      expect(test.frame).not.toContain('timeout:60s');
      expect(test.frame).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });
  it.each([[20, 48], [24, 80], [43, 100]])(
    'folds patch sets and opens their diffs on click at %i rows and %i columns', async (rows, columns) => {
    const patch = (path: string, oldLine: string, newLine: string) =>
      `Apply patch: 1 file changed\n\n<!-- siada-apply-patch:start -->\n### Update \`${path}\`\n` +
      `\`\`\`diff\n--- a/${path}\n+++ b/${path}\n@@ -1 +1 @@\n-${oldLine}\n+${newLine}\n\`\`\`\n` +
      '<!-- siada-apply-patch:end -->';
    const test = harness([
      message('first-patch', patch('src/a.ts', 'first-old', 'first-new'), 'tool_use', { streamEnd: true }),
      message('second-patch', patch('src/b.ts', 'second-old', 'second-new'), 'tool_use', { streamEnd: true }),
    ], columns, true, rows);
    try {
      await pause();
      expect(test.frame).toContain('Update 2 files');
      expect(test.frame).toContain('├─ Update src/a.ts (+1 -1) ›');
      expect(test.frame).toContain('└─ Update src/b.ts (+1 -1) ›');
      expect(test.frame).not.toContain('first-old');
      expect(test.frame).not.toContain('second-old');
      await test.click('Update src/a.ts');
      expect(test.frame).toContain('first-old');
      expect(test.frame).toContain('first-new');
      expect(test.frame).not.toContain('second-old');
      await test.click('Update src/a.ts');
      expect(test.frame).not.toContain('first-old');
      expect(test.frame).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });

  it('folds each file in a multi-file patch independently', async () => {
    const patch = `Apply patch: 2 files changed

<!-- siada-apply-patch:start -->
### Update \`src/a.ts\`
\`\`\`diff
--- a/src/a.ts
+++ b/src/a.ts
@@ -1 +1 @@
-before-a
+after-a
\`\`\`
### Update \`src/b.ts\`
\`\`\`diff
--- a/src/b.ts
+++ b/src/b.ts
@@ -1 +1 @@
-before-b
+after-b
\`\`\`
<!-- siada-apply-patch:end -->`;
    const test = harness([message('patch', patch, 'tool_use', { streamEnd: true })], 100, true);
    try {
      await pause();
      expect(test.frame).toContain('Update 2 files');
      expect(test.frame).toContain('├─ Update src/a.ts (+1 -1) ›');
      expect(test.frame).toContain('└─ Update src/b.ts (+1 -1) ›');
      expect(test.frame).not.toContain('before-a');
      await test.click('Update src/a.ts');
      expect(test.frame).toContain('Update src/a.ts (+1 -1)');
      expect(test.frame).toContain('Update src/b.ts (+1 -1)');
      expect(test.frame).toContain('before-a');
      expect(test.frame).not.toContain('after-b');
      await test.click('Update src/b.ts');
      expect(test.frame).toContain('after-b');
    } finally { test.close(); }
  });

  it('shows the line count for a single update file before opening its diff', async () => {
    const edit = 'In the file `src/a.ts``, replace the string:\n```ts\nold-value\n```\nwith:\n```ts\nnew-value\n```';
    const test = harness([message('edit', edit, 'tool_use', { streamEnd: true })], 100, true);
    try {
      await pause();
      expect(test.frame).toContain('● Update src/a.ts (+1 -1) ›');
      expect(test.frame).not.toContain('old-value');
      await test.click('Update src/a.ts');
      expect(test.frame).toContain('old-value');
      expect(test.frame).toContain('new-value');
    } finally { test.close(); }
  });

  it('keeps intermediate plan snapshots out of the conversation until completion', async () => {
    const test = harness([
      message('read', 'Read the file `src/example.ts`', 'tool_use'),
      message('first', '◐  First task\n○  Second task\n\n[0/2 completed]', 'tool_use'),
      message('middle', '✓  First task\n◐  Second task\n\n[1/2 completed]', 'tool_use'),
      message('clear', 'Clearing todo list', 'tool_use'),
      message('done', '✓  First task\n✓  Second task\n\n[2/2 completed]', 'tool_use'),
    ], 100, true);
    try {
      await pause();
      expect(test.frame).toContain('src/example.ts');
      expect(test.frame).toContain('Plan completed (2/2)');
      expect(test.frame).not.toContain('Todo List');
      expect(test.frame).not.toContain('0/2 completed');
      expect(test.frame).not.toContain('1/2 completed');
      await test.click('Plan completed');
      expect(test.frame).toContain('First task');
      expect(test.frame).toContain('Second task');
    } finally { test.close(); }
  });
  it.each([
    ['markdown', 'answer', '# Heading\n\n**Body**\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n```ts\nconst code = true;\n```', 'Heading'],
    ['reasoning', 'thinking', 'Thought summary\nThought detail', 'Thought summary'],
    ['process', 'process', 'Synthetic process progress', 'Synthetic process'],
    ['shell', 'shell', 'Synthetic shell output', 'Synthetic shell'],
  ])('renders production %s messages', async (id, subtype, content, expected) => {
    const test = harness([message(id, content, subtype, subtype === 'shell' ? {
      shellExecution: { command: 'synthetic', executing: false, stdout: content, stderr: '', exitCode: 0 },
    } : {})], 100, true);
    try { await pause(); expect(test.frame).toContain(expected); expect(test.frame).toContain('INPUT DRAFT'); }
    finally { test.close(); }
  });
  it('shows the original circle before a model reply in presentation mode', async () => {
    const test = harness([message('answer', 'A model reply.', 'answer')], 80, true);
    try {
      await pause();
      const lines = test.frame.split('\n');
      const replyRow = lines.findIndex(line => line.includes('A model reply.'));
      expect(replyRow).toBeGreaterThanOrEqual(0);
      expect(lines[replyRow]).toMatch(/^●\s+A model reply\./);
    } finally { test.close(); }
  });
  it.each(['printf "中文" && npm test', 'pwd'])('shows a standalone command directly: %s', async body => {
    const test = harness([command('run', body)], 80, true);
    try {
      await pause();
      expect(test.frame).toContain(`● Run ${body}`);
      expect(test.frame).not.toContain('Run command');
      expect(test.frame).not.toContain('timeout:60s');
      expect(test.frame).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });

  it('does not fold a fitting command because of hidden timeout metadata', async () => {
    const body = 'printf "fits in one line"';
    const test = harness([command('run', body)], 40, true);
    try {
      await pause();
      const line = test.frame.split('\n').find(row => row.includes('printf'));
      expect(line).toContain(`● Run ${body}`);
      expect(line).not.toContain('›');
      expect(test.screen.display()).not.toContain('timeout:60s');
    } finally { test.close(); }
  });

  it('uses the full row for a grouped command without timeout metadata at narrow width', async () => {
    const test = harness([command('run', 'find prototypes -type f | head -50'),
      message('read', 'Read the file `src/example.ts`', 'tool_use')], 40, true);
    try {
      await pause();
      const line = test.frame.split('\n').find(row => row.includes('find prototypes'));
      expect(line).toContain('find prototypes -type f | head -50');
      expect(test.frame.split('\n').every(row => stringWidth(row) < 40)).toBe(true);
      expect(test.frame).not.toContain('timeout:60s');
    } finally { test.close(); }
  });

  it.each(['dark', 'light'] as const)('uses the shared blue action color for standalone commands in %s mode', async theme => {
    const original = chalk.level;
    chalk.level = 3;
    setActiveTheme(theme);
    const test = harness([command('run', 'pwd'), message('note', 'Command complete.', 'process'),
      command('long-run', 'git status --short src/components/Chat/ConversationViewport.tsx')], 48, true);
    try {
      await pause();
      const assertAccent = () => {
        const lines = test.raw.split('\n').filter(row => row.includes('Run'));
        const runAccent = chalk.hex(colors.info)('Run').replace(/\x1b\[39m$/, '');
        const bulletAccent = chalk.hex(colors.info)('● ').replace(/\x1b\[39m$/, '');
        expect(lines).toHaveLength(2);
        for (const line of lines) {
          // Inline headings re-emit the color before "Run"; an expanded heading
          // inherits the bullet's code because Ink minimises escape output.
          expect(line.includes(runAccent) || line.includes(`${bulletAccent}\x1b[1mRun`)).toBe(true);
          expect(line).toContain('\x1b[1m');
        }
      };
      assertAccent();
      await test.click('git status');
      assertAccent();
    } finally { test.close(); chalk.level = original; setActiveTheme('dark'); }
  });

  it.each([false, true])('folds a long single-line command in a %s tool tree', async grouped => {
    const body = 'git status --short src/components/Chat/Message.tsx src/components/Chat/ConversationViewport.tsx';
    const messages = grouped ? [command('run', body), message('read', 'Read the file `src/example.ts`', 'tool_use')]
      : [command('run', body)];
    const test = harness(messages, 48, true);
    try {
      await pause();
      const preview = test.frame.split('\n').find(row => row.includes('git status'));
      if (!grouped) expect(preview).toContain('● Run git status');
      expect(preview).toContain('›');
      expect(preview).not.toContain('timeout:60s');
      expect(test.frame).not.toContain('ConversationViewport.tsx');
      expect(test.frame.split('\n').every(row => stringWidth(row) < 48)).toBe(true);
      await test.click('git status');
      // The heading shows the opening command line once; soft wrapping may
      // split the long trailing path, so assert on the path components.
      expect(test.frame).toContain('git status --short');
      expect(test.frame).toContain('src/components/Chat/Message.tsx');
      expect(test.frame).toContain('ConversationViewport');
      expect(test.frame.match(/git status --short/g)).toHaveLength(1);
      expect(test.frame).not.toContain('timeout:60s');
      expect(test.frame.split('\n').find(row => row.includes('git status'))).toContain('⌄');
      if (!grouped) expect(test.frame.split('\n').find(row => row.includes('git status'))).toContain('● Run git status');
      await test.click('git status');
      expect(test.frame).not.toContain('src/components/Chat/ConversationViewport');
      expect(test.frame).toContain('INPUT DRAFT');
    } finally { test.close(); }
  });

  it.each([40, 80, 100])('aligns all lines of one command tool at %i columns', async columns => {
    for (const last of [false, true]) {
      const run = command('run', 'printf first-command\nprintf second-command\nprintf third-command');
      const read = message('read', 'Read the file `src/example.ts`', 'tool_use');
      const test = harness(last ? [read, run] : [run, read], columns, true);
      try {
        await pause();
        const openingRow = test.frame.split('\n').findIndex(line => line.includes('printf first-command'));
        const preview = test.frame.split('\n')[openingRow].trimEnd();
        await test.click('printf first-command');
        const lines = test.frame.split('\n');
        const opening = lines[openingRow];
        expect(opening).toContain(`${last ? '└─' : '├─'} printf first-command`);
        const column = opening.indexOf('printf');
        for (const [index, label] of ['first-command', 'second-command', 'third-command'].entries()) {
          expect(lines[openingRow + index].indexOf(`printf ${label}`)).toBe(column);
          expect(test.screen.display().match(new RegExp(label, 'g'))).toHaveLength(1);
        }
        expect(test.frame.split('\n').every(line => stringWidth(line) < columns)).toBe(true);
        await test.click('printf first-command');
        expect(test.frame.split('\n')[openingRow].trimEnd()).toBe(preview);
        expect(test.frame.split('\n').filter(line => line.includes('printf'))).toHaveLength(1);
      } finally { test.close(); }
    }
  });

  it('shows command text while its fence is still being streamed', async () => {
    const test = harness([message('run', 'Run the following command:\n```bash\nprintf partial', 'tool_use')]);
    try {
      await pause();
      expect(test.frame).toContain('● printf partial ›');
      expect(test.frame).not.toContain('Run command');
    } finally { test.close(); }
  });

  it.each([false, true])('shows the beginning of reasoning with isStreaming=%s', async isStreaming => {
    const test = harness([message('reasoning', 'THINKING:\n先核对当前布局。\n再检查命令与间距。', 'thinking', { isStreaming })]);
    try {
      await pause();
      expect(test.frame).toContain('› 先核对当前布局。… ›');
      expect(test.frame).not.toContain('Thinking');
      expect(test.frame).not.toContain('Thought');
      expect(test.frame).not.toContain('再检查命令与间距。');
      await test.click('先核对当前布局');
      expect(test.frame.match(/先核对当前布局。/g)).toHaveLength(1);
      expect(test.frame).toContain('再检查命令与间距。');
    } finally { test.close(); }
  });

  it.each([false, true])('keeps reasoning previews compact and expands in place in presentation=%s', async presentation => {
    const opening = 'Opening reasoning sentence. ' + 'More detail about the current layout. '.repeat(4);
    const test = harness([message('reasoning', `THINKING:\n${opening}\n\nFinal reasoning line.`, 'thinking')], 160, presentation);
    try {
      await pause();
      const previewRow = test.frame.split('\n').findIndex(line => line.includes('Opening reasoning'));
      const preview = test.frame.split('\n')[previewRow].trimEnd();
      expect(stringWidth(preview)).toBeLessThanOrEqual(64);
      expect(preview).toContain('… ›');
      expect(test.frame).not.toContain('Final reasoning line.');
      await test.click('Opening reasoning');
      const lines = test.frame.split('\n');
      expect(lines.findIndex(line => line.includes('Opening reasoning'))).toBe(previewRow);
      expect(test.frame.match(/Opening reasoning sentence\./g)).toHaveLength(1);
      expect(test.frame).toContain('Final reasoning line.');
      expect(test.screen.display().match(/Opening reasoning sentence\./g)).toHaveLength(1);
      await test.click('Opening reasoning');
      expect(test.frame).not.toContain('Final reasoning line.');
      expect(test.frame.split('\n')[previewRow].trimEnd()).toBe(preview);
    } finally { test.close(); }
  });

  it.each([[20, 48], [24, 80], [43, 100]])('keeps the first reasoning line visible when long content expands at %i×%i', async (rows, columns) => {
    const content = '开头只显示一次。\n' + Array.from({ length: 70 }, (_, index) => `推理步骤 ${index}：检查布局与显示内容。`).join('\n');
    const test = harness([message('reasoning', content, 'thinking')], columns, true, rows);
    try {
      await pause();
      await test.click('开头只显示一次');
      expect(test.screen.display()).toContain('开头只显示一次。');
      expect(test.screen.display().match(/开头只显示一次。/g)).toHaveLength(1);
      expect(test.screen.display()).toContain('推理步骤 0');
      expect(test.screen.display()).toContain('INPUT DRAFT');
      expect(test.frame.split('\n')).toHaveLength(rows - 1);
      expect(test.frame.split('\n').every(line => stringWidth(line) <= columns)).toBe(true);
      await test.click('开头只显示一次');
      expect(test.screen.display()).not.toContain('推理步骤 0');
    } finally { test.close(); }
  });

  it.each(['dark', 'light'] as const)('paints expanded reasoning on a surface in %s mode', async theme => {
    const original = chalk.level;
    chalk.level = 3;
    setActiveTheme(theme);
    const test = harness([message('reasoning', 'Reasoning opening.\nSecond line.\n\nLast line.', 'thinking')], 48);
    try {
      await pause();
      await test.click('Reasoning opening');
      const color = (theme === 'light' ? '#e9edf2' : '#333333').slice(1).match(/../g)!
        .map(value => parseInt(value, 16)).join(';');
      const lines = test.raw.split('\n');
      for (const text of ['Second line.', 'Last line.']) {
        expect(lines.find(line => line.includes(text))).toContain(`48;2;${color}m`);
      }
      expect(test.screen.display()).toContain('Last line.');
      expect(test.frame.split('\n').every(line => stringWidth(line) <= 48)).toBe(true);
    } finally { test.close(); chalk.level = original; setActiveTheme('dark'); }
  });

  it.each([40, 80])('expands a grouped command without a second action heading at %i columns', async columns => {
    const body = 'find prototypes -type f | head -50';
    const test = harness([command('run', body),
      message('read', 'Read the file `src/example.ts` from line 1 to line 20', 'tool_use')], columns);
    try {
      await pause();
      expect(test.frame).toContain('Run 1 command, Read 1 file');
      await test.click('find prototypes');
      expect(test.frame).not.toContain('Run command');
      expect(test.frame).not.toContain('timeout:60s');
      expect(test.frame).toContain('└─ example.ts:1-20 ›');
      expect(test.frame.split('\n').every(line => stringWidth(line) < columns)).toBe(true);
    } finally { test.close(); }
  });

  it('uses one blank row between blocks and no blank rows inside a collapsed tool tree', async () => {
    const test = harness([
      { ...message('question', 'Question', ''), type: 'user' },
      message('reasoning', 'Reasoning opening.\nSecond line.', 'thinking'),
      command('run', 'printf synthetic'),
      message('read', 'Read the file `src/example.ts`', 'tool_use'),
      message('answer', 'Answer after tools.', 'answer'),
      { ...message('notice', 'Finished.', 'process'), type: 'system' },
    ]);
    try {
      await pause();
      const lines = test.frame.split('\n').map(line => line.trimEnd());
      const row = (text: string) => lines.findIndex(line => line.includes(text));
      expect(row('Reasoning opening.') - row('> Question')).toBe(2);
      expect(row('Run 1 command') - row('Reasoning opening.')).toBe(2);
      expect(row('├─ printf synthetic') - row('Run 1 command')).toBe(1);
      expect(row('└─ example.ts') - row('├─ printf synthetic')).toBe(1);
      expect(row('Answer after tools.') - row('└─ example.ts')).toBe(2);
      expect(row('Finished.') - row('Answer after tools.')).toBe(2);
    } finally { test.close(); }
  });
});