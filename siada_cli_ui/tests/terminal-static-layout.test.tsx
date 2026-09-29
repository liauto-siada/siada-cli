import React from 'react';
import { PassThrough } from 'node:stream';
import ansiEscapes from 'ansi-escapes';
import chalk from 'chalk';
import { Box, Static, Text, render } from '@jrichman/ink';
import { describe, expect, it } from 'vitest';
import stringWidth from 'string-width';
import type { Message as ChatMessage } from '../src/types/index.js';
import { MessageList } from '../src/components/Chat/MessageList.js';
import { DiffView } from '../src/components/diff/DiffView.js';
import { setActiveTheme } from '../src/themes/index.js';

const columns = 80;

function toolMessage(content: string): ChatMessage {
  return {
    id: 'tool', type: 'agent', content, author: 'Siada',
    timestamp: '2026-01-01T00:00:00.000Z',
    metadata: { subtype: 'tool_use', streamEnd: true },
  };
}

describe('real Ink static layout', () => {
  it('nests each file heading and its diff under a multi-file tool tree', async () => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 48 });
    const frames: string[] = [];
    const patch = `Apply patch: 2 files changed\n\n<!-- siada-apply-patch:start -->\n### Update \`src/a.ts\`\n\`\`\`diff\n--- a/src/a.ts\n+++ b/src/a.ts\n@@ -9 +9 @@\n-old\n+new\n\`\`\`\n### Create \`src/b.ts\`\n\`\`\`diff\n--- /dev/null\n+++ b/src/b.ts\n@@ -0,0 +1 @@\n+created\n\`\`\`\n<!-- siada-apply-patch:end -->`;
    const app = render(
      <Box width={columns} flexDirection="column">
        <MessageList messages={[toolMessage(patch)]} terminalWidth={columns} isCollapsed />
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );

    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const lines = frames.join('').replace(/\x1b\[[0-9;]*m/g, '').split('\n');
      expect(lines.find(line => line.includes('Edited 2 files'))?.startsWith('● ')).toBe(true);
      expect(lines.find(line => line.includes('Update src/a.ts'))?.startsWith('  ├─ ')).toBe(true);
      expect(lines.find(line => line.includes('Create src/b.ts'))?.startsWith('  └─ ')).toBe(true);
      expect(lines.find(line => line.includes('-old'))?.startsWith('    ')).toBe(true);
      expect(lines.find(line => line.includes('+created'))?.startsWith('    ')).toBe(true);
      expect(Math.max(...lines.map(stringWidth))).toBeLessThan(columns);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it('repaints completed tool headings after /theme switches between dark and light', async () => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 48 });
    const writes: string[] = [];
    stdout.on('data', chunk => writes.push(chunk.toString()));
    const originalColorLevel = chalk.level;
    chalk.level = 3;
    setActiveTheme('dark');
    const patch = `Apply patch: 1 file changed\n\n<!-- siada-apply-patch:start -->\n### Update \`src/a.ts\`\n\`\`\`diff\n--- a/src/a.ts\n+++ b/src/a.ts\n@@ -1 +1 @@\n-old\n+new\n\`\`\`\n<!-- siada-apply-patch:end -->`;
    const app = render(
      <Box width={columns} flexDirection="column">
        <MessageList messages={[toolMessage(patch)]} terminalWidth={columns} isCollapsed />
        <Text>input</Text>
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0 },
    );

    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const initial = writes.join('');
      expect(initial).toContain('\x1b[38;2;6;182;212m');
      expect(initial).toContain('Update');

      setActiveTheme('light');
      await new Promise(resolve => setTimeout(resolve, 200));
      const transition = writes.join('').slice(initial.length);
      expect(transition).toContain(ansiEscapes.clearTerminal);
      const lastScreen = transition.slice(transition.lastIndexOf(ansiEscapes.clearTerminal));
      expect(lastScreen).toContain('\x1b[38;2;5;80;174m');
      expect(lastScreen).toContain('Update');
      expect(lastScreen).toContain('input');
    } finally {
      app.unmount();
      app.cleanup();
      setActiveTheme('dark');
      chalk.level = originalColorLevel;
    }
  });

  it('renders bright +/- signs on their original diff backgrounds', async () => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 24 });
    const frames: string[] = [];
    const originalColorLevel = chalk.level;
    chalk.level = 3;
    const app = render(
      <Box width={columns}>
        <Static items={[{ id: 'diff' }]}>
          {() => <DiffView key="diff" filePath="src/a.ts" showFrame={false} width={72} hunks={[{
            oldStart: 1, oldLines: 2, newStart: 1, newLines: 2,
            lines: ['-old value', '+new value', ' context'],
          }]} />}
        </Static>
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );

    try {
      await new Promise(resolve => setTimeout(resolve, 50));
      const lines = frames.join('').split('\n');
      const removed = lines.find(line => line.replace(/\x1b\[[0-9;]*m/g, '').includes('old value'));
      const added = lines.find(line => line.replace(/\x1b\[[0-9;]*m/g, '').includes('new value'));
      expect(removed).toContain('\x1b[48;2;74;26;26m');
      expect(removed).toContain('\x1b[38;2;248;113;113m-');
      expect(added).toContain('\x1b[48;2;26;74;26m');
      expect(added).toContain('\x1b[38;2;74;222;128m+');
    } finally {
      app.unmount();
      app.cleanup();
      chalk.level = originalColorLevel;
    }
  });

  it.each([80, 48])('keeps resumed CJK diff rows within %i terminal columns', async (terminalColumns) => {
    const stdout = Object.assign(new PassThrough(), { columns: terminalColumns, rows: 24, isTTY: true });
    const frames: string[] = [];
    // Synthetic V4A history preview with the same shape as a resumed session:
    // context, replaced CJK text, and a long near-identical (word-diff) pair.
    const original = `${'相同 内容 '.repeat(9)}旧版`;
    const updated = `${'相同 内容 '.repeat(9)}新版`;
    const patch = `Apply patch: 1 file changed

<!-- siada-apply-patch:history-preview -->
<!-- siada-apply-patch:start -->
### Update \`README.md\`
\`\`\`diff
--- a/README.md
+++ b/README.md
@@ -1,3 +1,4 @@
 现有环境与测试数据保持完整，复核中文宽度与背景颜色。\t\t\t
  下一行含有混合符号 abc 🙂 é 和中文内容。
-${original}
+${updated}
+新增一行中文说明并保持其余内容不变。
\`\`\`
<!-- siada-apply-patch:end -->`;
    const previousColumns = process.stdout.columns;
    Object.defineProperty(process.stdout, 'columns', { value: terminalColumns, configurable: true });
    const app = render(
      <Box width={terminalColumns} flexDirection="column">
        <MessageList messages={[toolMessage(patch)]} terminalWidth={terminalColumns} isCollapsed={false} />
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );

    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const lines = frames.join('').replace(/\x1b\[[0-9;]*m/g, '').split('\n');
      expect(frames.length).toBeGreaterThan(0);
      expect(Math.max(...lines.map(stringWidth))).toBeLessThan(terminalColumns);
      expect(lines.join('\n')).toContain('下一行含有混合符号 abc 🙂 é');
      expect(lines.join('\n')).toContain('新版');
      const diffRows = lines.slice(lines.findIndex(line => line.includes('现有环境')), lines.findIndex(line => line.includes('新增一行')) + 1);
      expect(diffRows.length).toBeGreaterThanOrEqual(5);
      expect(diffRows.every(line => line.trim().length > 0)).toBe(true);
    } finally {
      app.unmount();
      app.cleanup();
      Object.defineProperty(process.stdout, 'columns', { value: previousColumns, configurable: true });
    }
  });

  it('keeps a long expanded tool box inside the terminal width', async () => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 24 });
    const stdin = new PassThrough();
    const frames: string[] = [];
    const command = 'Run the following command:\n' + Array.from({ length: 35 }, (_, index) =>
      `line ${index}: ${'sample code '.repeat(7)}`,
    ).join('\n');
    const app = render(
      <Box width={columns} flexDirection="column">
        <MessageList messages={[toolMessage(command)]} terminalWidth={columns} isCollapsed={false} />
        <Text>input</Text>
      </Box>,
      { stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );

    try {
      await new Promise(resolve => setTimeout(resolve, 50));
      expect(frames.length).toBeGreaterThan(0);
      const lines = frames.join('').replace(/\x1b\[[0-9;]*m/g, '').split('\n');
      expect(Math.max(...lines.map(stringWidth))).toBeLessThan(columns);
      expect(lines.join('\n')).toContain('line 0: sample code');
      expect(lines.join('\n')).not.toContain('Run the following command:');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it.each([
    { theme: 'dark', background: '\x1b[48;2;38;42;48m' },
    { theme: 'light', background: '\x1b[48;2;240;241;243m' },
  ] as const)('renders a real formatted command as borderless plain text on a subtle $theme background', async ({ theme, background }) => {
    const terminalColumns = 48;
    const stdout = Object.assign(new PassThrough(), { columns: terminalColumns, rows: 12 });
    const frames: string[] = [];
    const originalColorLevel = chalk.level;
    chalk.level = 3;
    setActiveTheme(theme);
    // The spaces after ':' and 'bash' and the trailing timeout are generated
    // by CommandFormatter, not hand-written Markdown.
    const command = `Run the following command: \n\`\`\`bash \npython3 -B - <<'PY'\nprint('*literal* 中🙂')\nPY\nprintf '${'long line '.repeat(10)}'\n\`\`\`\ntimeout: \`110s\``;
    const app = render(
      <Box width={terminalColumns} flexDirection="column">
        <MessageList messages={[toolMessage(command)]} terminalWidth={terminalColumns} isCollapsed={false} />
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );

    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const output = frames.join('');
      const lines = output.replace(/\x1b\[[0-9;]*m/g, '').split('\n');
      expect(lines.join('\n')).toContain('● Run command (timeout:110s)');
      expect(lines.join('\n')).toContain("print('*literal* 中🙂')");
      expect(lines.filter(line => line.includes('timeout:')).length).toBe(1);
      expect(lines.join('\n')).not.toContain('Run the following command:');
      expect(lines.join('\n')).not.toContain('```');
      expect(lines.join('\n')).not.toMatch(/[╭╮╰╯│]/);
      expect(Math.max(...lines.map(stringWidth))).toBeLessThan(terminalColumns);
      for (const line of output.split('\n').filter(row => /python3 -B|print\(/.test(row))) {
        // The band tints itself and nothing else: the command text keeps the
        // terminal's own foreground, like every other body text.
        expect(line).toContain(background);
        expect(line).not.toMatch(/\x1b\[38;2;/);
      }
    } finally {
      app.unmount();
      app.cleanup();
      setActiveTheme('dark');
      chalk.level = originalColorLevel;
    }
  });

  it.each([48, 80])('wraps expanded read, search, fetch and inline web search prompts without borders at %i columns', async (terminalColumns) => {
    const stdout = Object.assign(new PassThrough(), { columns: terminalColumns, rows: 32 });
    const frames: string[] = [];
    const path = `/very/long/project/${'nested/'.repeat(7)}stream_repetition.py`;
    const regex = `${'repetition|RetryError|'.repeat(6)}中文🙂`;
    const url = `https://example.org/docs/${'nested/'.repeat(12)}?query=中🙂`;
    const webQuery = `${'repetition stream retry '.repeat(8)}中文🙂`;
    const messages = [
      { ...toolMessage(`Read the file \`${path}\` from line 46 to line 620.\ncwd: \`/very/long/project\``), id: 'read' },
      { ...toolMessage(`Search for: ${regex} in ${path} with file pattern *.py in /very/long/project`), id: 'search' },
      { ...toolMessage(`Fetch URL: ${url}`), id: 'fetch' },
      { ...toolMessage(`Web search: search: ${webQuery}`), id: 'web-search' },
      { id: 'end', type: 'agent' as const, content: 'done', author: 'Siada',
        timestamp: '2026-01-01T00:00:00.000Z', metadata: { subtype: 'answer', streamEnd: true } },
    ];
    const originalColumns = process.stdout.columns;
    Object.defineProperty(process.stdout, 'columns', { value: terminalColumns, configurable: true });
    const app = render(
      <Box width={terminalColumns} flexDirection="column">
        <MessageList messages={messages} terminalWidth={terminalColumns} isCollapsed={false} />
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );
    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const lines = frames.join('').replace(/\x1b\[[0-9;]*m/g, '').split('\n');
      expect(frames.length).toBeGreaterThan(0);
      expect(Math.max(...lines.map(stringWidth))).toBeLessThan(terminalColumns);
      expect(lines.join('\n')).not.toMatch(/[╭╮╰╯│]/);
      expect(lines.join('\n')).toContain('● Read file');
      expect(lines.join('\n')).toContain('● Search');
      expect(lines.join('\n')).toContain('● Fetch');
      expect(lines.join('\n')).toContain('● Web Search');
      expect(lines.join('\n')).not.toContain('├─ path:');
      expect(lines.join('\n')).not.toContain('├─ regex:');
      expect(lines.join('\n')).not.toContain('└─ url:');
      expect(lines.join('\n')).not.toContain('└─ query:');
      const treeLines = lines.filter(line => /^  (?:[├└]─ |   )/.test(line))
        .map(line => line.slice(5));
      const restored = treeLines.join('');
      expect(restored).toContain('cwd: /very/long/project');
      expect(restored).not.toContain('directory: ');
      expect(restored).toContain('file pattern: *.py');
      // Terminal lines are separated by newlines, and Ink removes trailing
      // whitespace at a wrap boundary; compare words without those separators.
      const readHeadingIndex = lines.findIndex(line => line.startsWith('● Read file '));
      const searchHeadingIndex = lines.findIndex(line => line.startsWith('● Search '));
      const fetchHeadingIndex = lines.findIndex(line => line.startsWith('● Fetch '));
      const webHeadingIndex = lines.findIndex(line => line.startsWith('● Web Search '));
      expect(lines.slice(readHeadingIndex, searchHeadingIndex).join('').replace(/\s+/g, '')).toContain(`${path} · lines 46-620`.replace(/\s+/g, ''));
      expect(lines.slice(searchHeadingIndex, fetchHeadingIndex).join('').replace(/\s+/g, '')).toContain(`${regex} in ${path}`.replace(/\s+/g, ''));
      expect(lines.slice(fetchHeadingIndex, webHeadingIndex).join('').replace(/\s+/g, '')).toContain(url.replace(/\s+/g, ''));
      const webLines = lines.slice(webHeadingIndex, lines.findIndex((line, index) => index > webHeadingIndex && line.includes('done')));
      expect(webLines.length).toBeGreaterThan(1);
      expect(webLines.slice(1).filter(Boolean).every(line => line.startsWith('  '))).toBe(true);
      expect(webLines.join('').replace(/\s+/g, '')).toContain(`Web Search ${webQuery}`.replace(/\s+/g, ''));
    } finally {
      app.unmount();
      app.cleanup();
      Object.defineProperty(process.stdout, 'columns', { value: originalColumns, configurable: true });
    }
  });

  it.each([48, 80])('wraps plan steps and keeps the Search heading within %i columns', async (terminalColumns) => {
    const stdout = Object.assign(new PassThrough(), { columns: terminalColumns, rows: 32 });
    const frames: string[] = [];
    const task = `验证中文路径/${'long-component/'.repeat(5)}以及🙂最后一行`;
    const query = `todo_write|${'PlanUpdate|'.repeat(9)}匹配`;
    const directory = `/very/long/${'directory/'.repeat(5)}project`;
    const messages = [
      { ...toolMessage(`✓  Identify issue\n◐  ${task}\n○  Verify tests\n\n[1/3 completed]`), id: 'todo' },
      { ...toolMessage(`Search for: ${query} in ${directory} with file pattern *.ts in /workspace`), id: 'search' },
      { ...toolMessage('Run the following command:\n```bash\nprintf ok\n```'), id: 'after' },
    ];
    const originalColumns = process.stdout.columns;
    Object.defineProperty(process.stdout, 'columns', { value: terminalColumns, configurable: true });
    const app = render(
      <Box width={terminalColumns} flexDirection="column">
        <MessageList messages={messages} terminalWidth={terminalColumns} isCollapsed={false} />
      </Box>,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
        onRender: ({ staticOutput }) => { if (staticOutput) frames.push(staticOutput); } },
    );
    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const lines = frames.join('').replace(/\x1b\[[0-9;]*m/g, '').split('\n');
      expect(frames.length).toBeGreaterThan(0);
      expect(Math.max(...lines.map(stringWidth))).toBeLessThan(terminalColumns);
      expect(lines.join('\n')).toContain('● Updated Plan (1/3)');
      expect(lines.join('\n')).toContain('◐ ');
      expect(lines.join('\n')).not.toMatch(/[╭╮╰╯│]/);
      expect(lines.join('').replace(/\s+/g, '')).toContain(task.replace(/\s+/g, ''));
      const headingIndex = lines.findIndex(line => line.startsWith('● Search '));
      const headingLines = lines.slice(headingIndex, lines.findIndex((line, index) => index > headingIndex && line.includes('file pattern:')));
      expect(headingIndex).toBeGreaterThanOrEqual(0);
      expect(headingLines.slice(1).filter(Boolean).every(line => line.startsWith('  '))).toBe(true);
      expect(headingLines.join('').replace(/\s+/g, '')).toContain(`${query} in ${directory}`.replace(/\s+/g, ''));
      expect(lines.join('\n')).not.toContain('directory:');
    } finally {
      app.unmount();
      app.cleanup();
      Object.defineProperty(process.stdout, 'columns', { value: originalColumns, configurable: true });
    }
  });

  it('redraws static history once when expanded tool grouping changes', async () => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 24 });
    const stdin = new PassThrough();
    const writes: string[] = [];
    stdout.on('data', chunk => writes.push(chunk.toString()));
    const messages: ChatMessage[] = [
      { ...toolMessage('Read the file `src/a.ts`'), id: 'read-1' },
      { ...toolMessage('Read the file `src/b.ts`'), id: 'read-2' },
      { id: 'user', type: 'user', content: 'Next', author: 'User', timestamp: '2026-01-01T00:00:00.000Z' },
      { ...toolMessage('Read the file `src/c.ts`'), id: 'read-3' },
      { ...toolMessage('Run the following command:\n```bash\necho ok\n```'), id: 'run' },
    ];
    const view = (isCollapsed: boolean) => (
      <Box width={columns} flexDirection="column">
        <MessageList messages={messages} terminalWidth={columns} isCollapsed={isCollapsed} />
        <Text>input</Text>
      </Box>
    );
    const app = render(view(true), {
      stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });

    try {
      await new Promise(resolve => setTimeout(resolve, 50));
      const initialClears = writes.join('').split(ansiEscapes.clearTerminal).length - 1;
      app.rerender(view(false));
      await new Promise(resolve => setTimeout(resolve, 400));
      const redrawClears = writes.join('').split(ansiEscapes.clearTerminal).length - 1 - initialClears;
      expect(redrawClears).toBe(1);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it('replaces the startup banner when resume changes the session key', async () => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 48 });
    const stdin = new PassThrough();
    const writes: string[] = [];
    stdout.on('data', chunk => writes.push(chunk.toString()));
    const view = (sessionId: string) => (
      <Box width={columns} flexDirection="column">
        <MessageList
          key={sessionId}
          messages={[]}
          headerProps={{ workingDir: '/sample/project', version: '1.0.0', model: 'example-model' }}
          terminalWidth={columns}
          isCollapsed
        />
        <Text>input</Text>
      </Box>
    );
    const app = render(view('startup-session'), {
      stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });

    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      const initialOutput = writes.join('');
      expect(initialOutput).toContain('Siada CLI v1.0.0');
      expect(initialOutput).not.toContain(ansiEscapes.clearTerminal);

      app.rerender(view('resumed-session'));
      await new Promise(resolve => setTimeout(resolve, 80));
      const transitionOutput = writes.join('').slice(initialOutput.length);
      expect(transitionOutput.split(ansiEscapes.clearTerminal)).toHaveLength(2);
      const lastScreen = transitionOutput.slice(transitionOutput.lastIndexOf(ansiEscapes.clearTerminal));
      expect(lastScreen.match(/Siada CLI v1\.0\.0/g)).toHaveLength(1);
      expect(lastScreen).toContain('input');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it('does not replay superseded static history after a keyed remount and a full-screen redraw', async () => {
    const stdout = Object.assign(new PassThrough(), { columns: 40, rows: 6 });
    const stdin = new PassThrough();
    const writes: string[] = [];
    stdout.on('data', chunk => writes.push(chunk.toString()));
    const view = (label: string) => (
      <Box width={40} flexDirection="column">
        <Static key={label} items={[label]}>
          {item => <Text key={item}>{item}</Text>}
        </Static>
        {Array.from({ length: 8 }, (_, index) => <Text key={index}>line {index}</Text>)}
      </Box>
    );
    const app = render(view('old static history'), {
      stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });

    try {
      await new Promise(resolve => setTimeout(resolve, 50));
      app.rerender(view('new static history'));
      await new Promise(resolve => setTimeout(resolve, 50));
      const output = writes.join('');
      const lastScreen = output.slice(output.lastIndexOf(ansiEscapes.clearTerminal));
      expect(lastScreen).toContain('new static history');
      expect(lastScreen).not.toContain('old static history');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it('retains earlier history when new items are appended to the same Static', async () => {
    const stdout = Object.assign(new PassThrough(), { columns: 40, rows: 6 });
    const stdin = new PassThrough();
    const writes: string[] = [];
    stdout.on('data', chunk => writes.push(chunk.toString()));
    const view = (items: string[]) => (
      <Box width={40} flexDirection="column">
        <Static items={items}>
          {item => <Text key={item}>{item}</Text>}
        </Static>
        {Array.from({ length: 8 }, (_, index) => <Text key={index}>line {index}</Text>)}
      </Box>
    );
    const app = render(view(['first history item']), {
      stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });

    try {
      await new Promise(resolve => setTimeout(resolve, 50));
      app.rerender(view(['first history item', 'second history item']));
      await new Promise(resolve => setTimeout(resolve, 50));
      const output = writes.join('');
      const lastScreen = output.slice(output.lastIndexOf(ansiEscapes.clearTerminal));
      expect(lastScreen).toContain('first history item');
      expect(lastScreen).toContain('second history item');
      expect(lastScreen.match(/first history item/g)).toHaveLength(1);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});
