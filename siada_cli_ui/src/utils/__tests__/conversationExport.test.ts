import { describe, it, expect, afterEach, vi } from 'vitest';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { join, basename } from 'node:path';
import { tmpdir } from 'node:os';
import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import stripAnsi from 'strip-ansi';
import stringWidth from '../terminalWidth.js';
import { ConversationViewport } from '../../components/Chat/ConversationViewport.js';
import { setUiLanguage } from '../../i18n/index.js';
import type { Message } from '../../types/index.js';
import {
  buildDefaultExportFilename, exportConversation, extractFirstPrompt,
  renderBannerBlock, renderConversationToText, sanitizeFilename,
} from '../conversationExport.js';

vi.mock('../../hooks/useKeypress.js', () => ({ useKeypress: () => {} }));

let nextId = 0;
function msg(partial: Partial<Message> & Pick<Message, 'type'>): Message {
  return { id: `synthetic-${nextId++}`, content: '', timestamp: '2026-02-06T10:00:00Z',
    author: 'Synthetic', ...partial };
}
const command = (body: string) => msg({ type: 'agent',
  content: `Run the following command:\n\`\`\`bash\n${body}\n\`\`\`\ntimeout:60s`,
  metadata: { subtype: 'tool_use' } });
const normalize = (text: string) => stripAnsi(text).split('\n').map(line => line.trimEnd()).join('\n').trimEnd();
afterEach(() => setUiLanguage('zh-CN'));

describe('export filenames', () => {
  it('uses the first prompt, preserves CJK and strips path characters', () => {
    const messages = [msg({ type: 'system', content: 'notice' }),
      msg({ type: 'user', content: '修复登录 bug\nsecond line' })];
    expect(extractFirstPrompt(messages)).toBe('修复登录 bug');
    expect(sanitizeFilename(extractFirstPrompt(messages))).toBe('修复登录-bug');
    expect(sanitizeFilename('fix the  bug: /tmp?')).toBe('fix-the-bug-tmp');
    expect(buildDefaultExportFilename(messages, new Date(2026, 1, 6, 15, 4, 32)))
      .toBe('2026-02-06-150432-修复登录-bug.txt');
  });
  it('caps prompts and falls back when there is no user message', () => {
    expect(extractFirstPrompt([msg({ type: 'user', content: 'x'.repeat(80) })])).toHaveLength(50);
    expect(sanitizeFilename('啊'.repeat(80))).toHaveLength(50);
    expect(extractFirstPrompt([])).toBe('');
    expect(buildDefaultExportFilename([], new Date(2026, 1, 6, 15, 4, 32)))
      .toBe('conversation-2026-02-06-150432.txt');
  });
});

describe('TUI transcript export', () => {
  it.each([48, 80, 100])('matches the actual viewport at %i columns in both layouts and collapse modes', async columns => {
    setUiLanguage('en');
    const messages = [
      msg({ type: 'user', content: 'Please check the project' }),
      msg({ type: 'agent', content: 'THINKING: First thought\nSecond thought', metadata: { subtype: 'thinking' } }),
      command('npm test'),
      command('npm run build'),
      msg({ type: 'agent', content: 'Hook text', metadata: { subtype: 'hook', hookEvent: 'PreToolUse', hookStatus: 'blocked' } }),
      msg({ type: 'error', content: 'Synthetic error' }),
      msg({ type: 'agent', content: '**Done**\n\n| Name | Value |\n| --- | --- |\n| a | 1 |\n\n```ts\nconst x = 1;\n```',
        metadata: { subtype: 'answer' } }),
    ];
    for (const presentation of [false, true]) {
      for (const isCollapsed of [false, true]) {
        const stdout = Object.assign(new PassThrough(), { columns, rows: 160 });
        let output = '';
        const app = render(React.createElement(ConversationViewport, {
          messages, width: columns, height: 160, isCollapsed, presentation, active: true,
        }), { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
          onRender: metrics => { output = metrics.output; } });
        try {
          await new Promise(resolve => setTimeout(resolve, 100));
          const text = await renderConversationToText(messages, { columns, presentation, isCollapsed });
          expect(normalize(text)).toBe(normalize(output));
          expect(text).not.toMatch(/\x1b|Siada CLI Conversation Export|Messages:|──{59}/);
          expect(text.split('\n').every(line => stringWidth(line) <= columns)).toBe(true);
        } finally { app.unmount(); app.cleanup(); }
      }
    }
  });

  it('renders the current banner without the old box and directory metadata', async () => {
    const info = { version: '1.7.37', workingDir: '/synthetic/project' };
    const banner = await renderBannerBlock(info, 80);
    const text = await renderConversationToText([msg({ type: 'user', content: 'Hello' })],
      { columns: 80, bannerInfo: info });
    expect(text.startsWith(banner)).toBe(true);
    expect(text).toContain('1.7.37');
    expect(text).not.toContain('Working Directory:');
    expect(text).not.toContain('╭');
  });

  it('retains individually expanded blocks while other blocks remain compact', async () => {
    const first = msg({ type: 'agent', content: 'First thought\nExpanded detail', metadata: { subtype: 'thinking' } });
    const second = msg({ type: 'agent', content: 'Other thought\nHidden detail', metadata: { subtype: 'thinking' } });
    const text = await renderConversationToText([first, second], {
      isCollapsed: true, collapsedOverrides: new Map([[first.id, false]]),
    });
    expect(text).toContain('Expanded detail');
    expect(text).not.toContain('Hidden detail');
    expect(text).toContain('Other thought');
  });

  it('exports full history and long answers beyond the viewport and skips empty placeholders', async () => {
    const messages = Array.from({ length: 60 }, (_, index) => msg({ type: 'user', content: `Turn ${index}` }));
    messages.push(msg({ type: 'agent', content: Array.from({ length: 300 }, (_, index) => `Answer line ${index}`).join('\n'),
      metadata: { subtype: 'answer' } }));
    messages.push(msg({ type: 'agent', content: '', metadata: { streamEnd: true, isStreaming: false } }));
    const text = await renderConversationToText(messages);
    expect(text).toContain('Turn 0');
    expect(text).toContain('Turn 59');
    expect(text).toContain('Answer line 299');
    expect(text).not.toContain('truncated');
  });

  it('includes structured shell output even when content is empty', async () => {
    const text = await renderConversationToText([msg({ type: 'tool', metadata: { subtype: 'shell',
      shellExecution: { command: 'ls', executing: false, stdout: 'file-a\nfile-b', stderr: '', exitCode: 0 } } })]);
    expect(text).toContain('ls');
    expect(text).toContain('file-a');
    expect(text).toContain('file-b');
  });

  it('renders file diffs and Mermaid diagrams instead of exporting their source markers', async () => {
    const patch = msg({ type: 'agent', metadata: { subtype: 'tool_use', streamEnd: true },
      content: 'Apply patch: 1 file changed\n<!-- siada-apply-patch:start -->\n' +
        '### Update `src/a.ts`\n```diff\n--- a/src/a.ts\n+++ b/src/a.ts\n' +
        '@@ -1 +1 @@\n-before-value\n+after-value\n```\n<!-- siada-apply-patch:end -->' });
    const diagram = msg({ type: 'agent', metadata: { subtype: 'answer' },
      content: '```mermaid\nflowchart LR\n A[Received] --> B[Execute]\n```' });
    const text = await renderConversationToText([patch, diagram], { presentation: true, columns: 100 });
    expect(text).toContain('src/a.ts');
    expect(text).toContain('before-value');
    expect(text).toContain('after-value');
    expect(text).toContain('Received');
    expect(text).toContain('Execute');
    expect(text).not.toContain('siada-apply-patch');
    expect(text).not.toContain('flowchart LR');
  });

  it('renders structured goal results even when the text content is empty', async () => {
    const goal = msg({ type: 'system', metadata: { subtype: 'goal_result',
      goalResult: { achieved: true, turns: 3, elapsedSeconds: 20, tokensUsed: 0,
        objective: 'Verify the project', reason: 'All checks passed.' } } });
    const text = await renderConversationToText([goal], { presentation: true, isCollapsed: true });
    expect(text).toContain('Goal Achieved');
  });
});

describe('exportConversation', () => {
  it('writes the TUI transcript using default and explicit filenames', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'siada-export-'));
    try {
      const messages = [msg({ type: 'user', content: 'hello world' })];
      const result = await exportConversation(messages, dir, '');
      expect(result.success).toBe(true);
      const files = readdirSync(dir).filter(file => file.endsWith('.txt'));
      expect(files).toHaveLength(1);
      expect(readFileSync(join(dir, files[0]), 'utf8')).toBe(await renderConversationToText(messages));
      const named = await exportConversation(messages, dir, 'session-notes.md');
      expect(named.success).toBe(true);
      expect(basename(named.message)).toBe('session-notes.txt');
      expect(readFileSync(join(dir, 'session-notes.txt'), 'utf8')).toContain('hello world');
    } finally { rmSync(dir, { recursive: true, force: true }); }
  });
  it('reports write failure', async () => {
    const result = await exportConversation([msg({ type: 'user', content: 'data' })],
      '/nonexistent-dir-xyz', '');
    expect(result.success).toBe(false);
    expect(result.message).toContain('Failed to export conversation');
  });
});