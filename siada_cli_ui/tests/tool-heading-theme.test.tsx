import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '../src/types/index.js';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children, marginLeft = 0, borderStyle }: { children?: React.ReactNode; marginLeft?: number; borderStyle?: string }) => (
      <div data-margin-left={marginLeft} {...(borderStyle ? { 'data-border-style': borderStyle } : {})}>{children}</div>
    ),
    Text: ({ children, color, bold, backgroundColor }: { children?: React.ReactNode; color?: string; bold?: boolean; backgroundColor?: string }) => (
      <span data-color={color} data-bold={bold} {...(backgroundColor ? { 'data-background': backgroundColor } : {})}>{children}</span>
    ),
    Static: ({ items, children }: { items: unknown[]; children: (item: unknown, index: number) => React.ReactNode }) => (
      <section>{items.map((item, index) => children(item, index))}</section>
    ),
    useStdout: () => ({ stdout: { rows: 48, columns: 80 } }),
  };
});

import { MessageList } from '../src/components/Chat/MessageList.js';
import { setActiveTheme } from '../src/themes/index.js';

const run = 'Run the following command:\n```bash\nprintf hello\n```';
const patch = `Apply patch: 3 files changed

<!-- siada-apply-patch:start -->
### Update \`src/a.ts\`
\`\`\`diff
--- a/src/a.ts
+++ b/src/a.ts
@@ -1 +1 @@
-old
+new
\`\`\`
### Create \`src/b.ts\`
\`\`\`diff
--- /dev/null
+++ b/src/b.ts
@@ -0,0 +1 @@
+created
\`\`\`
### Delete \`src/c.ts\`
\`\`\`diff
--- a/src/c.ts
+++ /dev/null
@@ -1 +0,0 @@
-deleted
\`\`\`
<!-- siada-apply-patch:end -->`;

function tool(id: string, content: string): Message {
  return {
    id, type: 'agent', content, author: 'Siada', timestamp: '2026-01-01T00:00:00.000Z',
    metadata: { subtype: 'tool_use', streamEnd: true },
  };
}

const visible = (html: string) => html.replace(/<[^>]*>/g, '');

afterEach(() => setActiveTheme('dark'));

describe('shared tool headings', () => {
  it.each(['dark', 'light'] as const)('keeps run and edit at the same level in %s mode', theme => {
    setActiveTheme(theme);
    const accent = theme === 'light' ? '#0550ae' : '#06B6D4';
    const messages = [tool('run-1', run), tool('run-2', run), tool('run-3', run), tool('patch', patch)];
    const oldRows = process.stdout.rows;
    Object.defineProperty(process.stdout, 'rows', { value: 48, configurable: true });
    let output: string;
    try {
      output = renderToStaticMarkup(<MessageList messages={messages} isCollapsed noStatic />);
    } finally {
      Object.defineProperty(process.stdout, 'rows', { value: oldRows, configurable: true });
    }
    const text = visible(output);

    expect(text).toContain('● Run 3 commands (ctrl+o to expand)');
    expect(text).toContain('● Edited 3 files (+2 -2)');
    expect(text).toContain('├─ Update src/a.ts (+1 -1)');
    expect(text).toContain('├─ Create src/b.ts (+1 -0)');
    expect(text).toContain('└─ Delete src/c.ts (+0 -1)');
    expect(output).toContain(`<span data-color="${accent}" data-bold="true">Run</span>`);
    for (const action of ['Edited', 'Update', 'Create', 'Delete']) {
      expect(output).toContain(`<span data-color="${accent}" data-bold="true">${action}</span>`);
    }
    // Both top-level headings are hosted by an unindented box; the tree
    // children and actual diff remain indented under their file header.
    expect(output).toMatch(/<div data-margin-left="0"><span><span data-color="[^"]+"[^>]*>●<\/span> <span/);
    expect(output.match(/<div data-margin-left="0"><span><span data-color="[^"]+"[^>]*>●<\/span> <span/g)).toHaveLength(2);
  });

  it('uses the same action heading for expanded commands and file edits', () => {
    const output = renderToStaticMarkup(<MessageList messages={[tool('run', run), tool('patch', patch)]} isCollapsed={false} noStatic />);
    expect(visible(output)).toContain('● Run command');
    expect(visible(output)).toContain('● Edited 3 files');
    expect(output).toContain('data-margin-left="0"');
  });

  it.each([
    { theme: 'dark', background: '#262a30' },
    { theme: 'light', background: '#f0f1f3' },
  ] as const)('keeps only expanded command bodies borderless and monochrome in $theme mode', ({ theme, background }) => {
    setActiveTheme(theme);
    const secondary = theme === 'light' ? '#4b5563' : '#b9c2cc';
    const powershell = 'Run the following PowerShell command: \n```powershell \nWrite-Host "*hello*"\n```\ntimeout: `10s`';
    const readFile = 'Read the file `src/a.ts`';
    const expanded = renderToStaticMarkup(<MessageList messages={[tool('powershell', powershell), tool('read', readFile), tool('directory', 'View the directory `src`')]} noStatic />);

    expect(visible(expanded)).toContain('● Run PowerShell command (timeout:10s)');
    expect(visible(expanded)).toContain('Write-Host &quot;*hello*&quot;');
    // The command text inherits the terminal foreground; the hint steps down a
    // tier so the heading still reads as a heading.
    expect(expanded).toContain(`data-color="${secondary}"> (timeout:10s)</span>`);
    expect(expanded).not.toContain(`data-background="${background}">timeout:`);
    expect(visible(expanded)).not.toContain('```');
    expect(expanded).toContain(`<span data-background="${background}">`);
    expect(expanded).not.toMatch(/data-color="#[0-9a-f]{6}" data-background="#[0-9a-f]{6}"/);
    expect(expanded.match(/data-border-style="round"/g)).toHaveLength(1); // directory tools are unchanged
    expect(visible(expanded)).toContain('● Read file src/a.ts');
    expect(visible(expanded)).not.toContain('└─ path: src/a.ts');

    const compact = renderToStaticMarkup(<MessageList messages={[tool('powershell', powershell)]} isCollapsed noStatic />);
    expect(visible(compact)).toContain('Run 1 PowerShell command');
    expect(compact).not.toContain(`data-background="${background}"`);
  });

  it('keeps timeout-like lines inside commands and only moves actual metadata into the heading', () => {
    const command = 'Run the following command: \n```bash \nprintf "timeout: `keep`"\n```';
    const output = renderToStaticMarkup(<MessageList messages={[tool('run', command)]} noStatic />);
    expect(visible(output)).toContain('● Run commandprintf &quot;timeout: `keep`&quot;');
    expect(visible(output)).not.toContain('(timeout:');
  });

  it.each(['dark', 'light'] as const)('renders expanded prompts without borders or redundant web search trees in %s mode', theme => {
    setActiveTheme(theme);
    const messages = [
      tool('read', 'Read the file `/tmp/project/src/entry.py` from line 46 to line 620.\ncwd: `/tmp/project`'),
      tool('search', 'Search for: stream_repetition|RetryError in /tmp/project with file pattern *.py in /tmp/project'),
      tool('fetch', 'Fetch URL: https://example.org/docs?q=stream'),
      tool('web-search', 'Web search: search: stream repetition python'),
    ];
    const output = renderToStaticMarkup(<MessageList messages={messages} noStatic />);
    const text = visible(output);
    expect(text).toContain('● Read file /tmp/project/src/entry.py · lines 46-620');
    expect(text).toContain('└─ cwd: /tmp/project');
    expect(text).not.toContain('path: /tmp/project/src/entry.py');
    expect(text).not.toContain('└─ lines:');
    expect(text).toContain('● Search stream_repetition|RetryError in /tmp/project');
    expect(text).not.toContain('regex: stream_repetition|RetryError');
    expect(text).toContain('├─ file pattern: *.py');
    expect(text).toContain('└─ cwd: /tmp/project');
    expect(text).not.toContain('directory: /tmp/project');
    expect(text).toContain('● Fetch https://example.org/docs?q=stream');
    expect(text).not.toContain('└─ url:');
    expect(text).toContain('● Web Search stream repetition python');
    expect(text).not.toContain('└─ query:');
    expect(text).not.toContain('Web search: search:');
    expect(output).not.toContain('data-border-style="round"');
    // Tool values read exactly like the plain text of a "Run N commands"
    // heading while the connectors around them step down one tier.
    const secondary = theme === 'light' ? '#4b5563' : '#b9c2cc';
    expect(output).toContain('<span>cwd: /tmp/project</span>');
    expect(output).toContain(`data-color="${secondary}">└─ </span>`);
    expect(output).toContain(`data-color="${secondary}"> in </span>`);
    expect(output).not.toMatch(/data-color="#(?:c4cbd3|39424c|9ca3af|57606a|9aa4b2|d0d7de|1f2328|7d8590)"/);
    expect(output).toContain(`<span data-color="${theme === 'light' ? '#0550ae' : '#06B6D4'}" data-bold="true">Web Search</span>`);
  });

  it('keeps older incomplete search prompts visible without restoring the border', () => {
    const output = renderToStaticMarkup(<MessageList messages={[
      tool('search', 'Search for: a|b in /tmp/project with file pattern *.ts'),
    ]} noStatic />);
    expect(visible(output)).toContain('● Search a|b in /tmp/project');
    expect(visible(output)).toContain('└─ file pattern: *.ts');
    expect(output).not.toContain('data-border-style="round"');
  });

  it('renders legacy web search prompts and preserves compact behavior', () => {
    const message = tool('web-search', 'Web search: python release notes');
    const expanded = renderToStaticMarkup(<MessageList messages={[message]} noStatic />);
    expect(visible(expanded)).toContain('● Web Search python release notes');
    expect(visible(expanded)).not.toContain('└─ query:');
    expect(expanded).not.toContain('data-border-style="round"');

    const compact = renderToStaticMarkup(<MessageList messages={[message]} isCollapsed noStatic />);
    expect(visible(compact)).toContain('Web 1 request');
    expect(visible(compact)).not.toContain('└─ query:');
  });

  it('keeps reads without cwd and fetches as heading-only calls', () => {
    const text = visible(renderToStaticMarkup(<MessageList messages={[
      tool('read', 'Read the file `local-sandbox/checks/test_local_sandbox.py` from line 205 to line 292.'),
      tool('fetch', 'Fetch URL: https://example.org/guide'),
    ]} noStatic />));
    expect(text).toContain('● Read file local-sandbox/checks/test_local_sandbox.py · lines 205-292');
    expect(text).toContain('● Fetch https://example.org/guide');
    expect(text).not.toContain('└─');
  });

  it('keeps compact Search aggregation unchanged', () => {
    const output = visible(renderToStaticMarkup(<MessageList messages={[
      tool('search', 'Search for: foo|bar in tasks/app with file pattern *.py in /workspace'),
    ]} isCollapsed noStatic />));
    expect(output).toContain('● Search 1 query (ctrl+o to expand)');
    expect(output).not.toContain('● Search foo|bar in tasks/app');
  });

  it.each(['dark', 'light'] as const)('renders a todo snapshot as a plain status list in %s', theme => {
    setActiveTheme(theme);
    const output = renderToStaticMarkup(<MessageList messages={[
      tool('plan', '✓  Inspect src/a.ts\n◐  Implement **fix**\n○  Add tests\n\n[1/3 completed]'),
    ]} noStatic />);
    const text = visible(output);
    expect(text).toContain('● Updated Plan (1/3)');
    expect(text).toContain('└ ✓ Inspect src/a.ts');
    expect(text).toContain('◐ Implement **fix**');
    expect(text).toContain('○ Add tests');
    expect(text).not.toContain('[1/3 completed]');
    expect(output).not.toContain('data-border-style="round"');
    expect(output).toContain(`data-color="${theme === 'light' ? '#0550ae' : '#06B6D4'}" data-bold="true">Implement **fix**</span>`);
  });

  it('keeps only the finished todo summary in compact history, separate from later tools', () => {
    const output = renderToStaticMarkup(<MessageList messages={[
      tool('in-progress', '◐  Build feature\n○  Run tests\n\n[0/2 completed]'),
      tool('completed', '✓  Build feature\n✓  Run tests\n\n[2/2 completed]'),
      tool('read', 'Read the file `src/a.ts`'),
    ]} isCollapsed noStatic />);
    const text = visible(output);
    expect(text).toContain('● Plan completed (2/2)');
    expect(text).not.toContain('Build feature');
    expect(text).not.toContain('Updated Plan');
    expect(text).toContain('Read 1 file');
    expect(text.indexOf('Plan completed')).toBeLessThan(text.indexOf('Read 1 file'));
    expect(output).not.toContain('data-border-style="round"');
  });

  it('renders a completed plan from resumed history and a cleared plan without an empty box', () => {
    const completed = tool('resumed', '✓  Investigate\n✓  Verify\n\n[2/2 completed]');
    const compact = renderToStaticMarkup(<MessageList messages={[completed]} isCollapsed />);
    expect(visible(compact)).toContain('● Plan completed (2/2)');
    expect(visible(compact)).not.toContain('Investigate');
    expect(compact).toContain('<section>');
    expect(compact.indexOf('Plan completed')).toBeLessThan(compact.indexOf('</section>'));

    const expanded = visible(renderToStaticMarkup(<MessageList messages={[completed]} noStatic />));
    expect(expanded).toContain('● Updated Plan (2/2)');
    expect(expanded).toContain('✓ Investigate');

    for (const isCollapsed of [true, false]) {
      const cleared = renderToStaticMarkup(<MessageList messages={[tool('clear', 'Clearing todo list')]} isCollapsed={isCollapsed} noStatic />);
      expect(visible(cleared)).toContain('● Plan cleared');
      expect(cleared).not.toContain('data-border-style="round"');
    }
  });

  it('does not turn an unrelated success notice into a plan', () => {
    const text = visible(renderToStaticMarkup(<MessageList messages={[
      tool('success', '✓  Created src/a.ts'),
    ]} noStatic />));
    expect(text).toContain('Created src/a.ts');
    expect(text).not.toContain('Updated Plan');
  });

  it('shows every completed step in expanded history even when the list exceeds the live-frame height', () => {
    const steps = Array.from({ length: 30 }, (_, index) => `✓  Task ${index + 1}`);
    const completed = tool('many', `${steps.join('\n')}\n\n[30/30 completed]`);
    const expanded = visible(renderToStaticMarkup(<MessageList messages={[completed]} noStatic />));
    expect(expanded).toContain('● Updated Plan (30/30)');
    expect(expanded).toContain('Task 1');
    expect(expanded).toContain('Task 30');
    expect(expanded).not.toContain('more lines');
    const compact = visible(renderToStaticMarkup(<MessageList messages={[completed]} isCollapsed noStatic />));
    expect(compact).toContain('● Plan completed (30/30)');
    expect(compact).not.toContain('Task 30');
  });
});
