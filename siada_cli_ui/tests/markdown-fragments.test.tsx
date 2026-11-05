import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { conversationBlocks } from '../src/components/Chat/ConversationViewport.js';
import { Message } from '../src/components/Chat/Message.js';
import type { Message as ChatMessage } from '../src/types/index.js';
import { advanceMarkdownFence, findEnclosingCodeBlockStart } from '../src/utils/markdownUtilities.js';

const message = (content: string): ChatMessage => ({
  id: 'synthetic-markdown', type: 'agent', author: 'Synthetic',
  timestamp: '2026-01-01T00:00:00Z', content, metadata: { subtype: 'answer' },
});
const prose = '\n## 修复结果\n**标题正常**，使用 `ToolHeading`。\n- **验证通过**';

async function frame(content: string, columns: number): Promise<string> {
  const blocks = conversationBlocks([message(content)], true);
  const stdout = Object.assign(new PassThrough(), { columns, rows: 500 });
  let output: string | undefined;
  const app = render(
    <Box flexDirection="column" width={columns}>
      {blocks.map(block => <Message key={block.id} message={block.message}
        initialCodeFence={block.initialCodeFence} compactSpacing disableTruncation
        terminalWidth={columns} />)}
    </Box>,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false,
      maxFps: 0, onRender: value => { output = value.output.replace(/\x1b\[[0-9;]*m/g, ''); } },
  );
  try {
    await vi.waitFor(() => expect(output).toBeDefined());
    return output!;
  } finally {
    app.unmount();
    app.cleanup();
  }
}

describe('Markdown continuation rendering', () => {
  it.each([32, 100])('keeps an oversized code block whole and restores prose at %i columns', async width => {
    const content = '```text\n' + 'literal **code** `value`\n'.repeat(270) + '```' + prose;
    const blocks = conversationBlocks([message(content)], true);
    expect(blocks).toHaveLength(2);
    expect(blocks.every(block => !block.initialCodeFence)).toBe(true);
    expect(blocks.map(block => block.message.content).join('')).toBe(content);
    expect(blocks[0].message.content).toBe(content.slice(0, content.indexOf(prose) + 1));
    const output = await frame(content, width);
    expect(output).toContain('literal **code** `value`');
    expect(output).toContain('修复结果');
    expect(output).toContain('标题正常');
    expect(output).toContain('ToolHeading');
    expect(output).not.toContain('## 修复结果');
    expect(output).not.toContain('**标题正常**');
    expect(output).not.toContain('`ToolHeading`');
    expect(output).not.toContain('**验证通过**');
  });

  it.each([
    ['~~~text', '~~~', '\n'],
    ['````text', '````', '\n'],
    ['  ```text', '  ```', '\r\n'],
  ])('preserves fence form %s across cuts', async (open, close, newline) => {
    const content = [open, ...Array(180).fill('literal **code**'), close,
      '## 修复结果', '**标题正常**'].join(newline);
    const output = await frame(content, 80);
    expect(output).toContain('literal **code**');
    expect(output).not.toContain('## 修复结果');
    expect(output).not.toContain('**标题正常**');
  });

  it('keeps mismatched delimiters inside code and restores the next independent fence', async () => {
    const content = '````text\n' + 'literal **code**\n'.repeat(200) +
      '```\n~~~\n## literal heading\n````' + prose +
      '\n```ts\nconst finalValue = 42;\n```\n## 最后标题';
    const output = await frame(content, 100);
    expect(output).toContain('## literal heading');
    expect(output).toContain('const finalValue = 42;');
    expect(output).not.toContain('## 修复结果');
    expect(output).not.toContain('## 最后标题');
  });

  it('keeps unfinished code as code while streaming, then restores prose when closed', async () => {
    const content = '```text\n' + 'literal **code**\n'.repeat(200) + '## literal heading';
    expect(await frame(content, 80)).toContain('## literal heading');
    const closed = await frame(content + '\n```' + prose, 80);
    expect(closed).toContain('## literal heading');
    expect(closed).not.toContain('## 修复结果');
  });

  it('does not carry fence state across independent messages', () => {
    const blocks = conversationBlocks([message('```text\nunfinished'),
      { ...message(prose), id: 'next-answer' }], true);
    expect(blocks[1].initialCodeFence).toBeUndefined();
  });

  it('keeps indented delimiters literal inside an oversized code block', async () => {
    const content = '```text\n' + 'x'.repeat(2990) + '\n' +
      '    ```\n## literal heading\n' + 'x'.repeat(1600) + '\n```' + prose;
    const blocks = conversationBlocks([message(content)], true);
    expect(blocks[0].message.content).toContain('\n    ```\n## literal heading');
    expect(blocks[0].message.content).toMatch(/\n```\n$/);
    const output = await frame(content, 100);
    expect(output).toContain('## literal heading');
    expect(output).not.toContain('## 修复结果');
  });

  it('renders all six diagrams when their code blocks cross the fragment budget', async () => {
    const diagrams = Array.from({ length: 6 }, (_, index) =>
      '```mermaid\nsequenceDiagram\n' +
      '%% padding to cross the presentation fragment boundary\n'.repeat(70) +
      `participant A as Parent${index}\nparticipant B as Child${index}\n` +
      `A->>B: Request${index}\nB-->>A: Result${index}\n\`\`\`\n`);
    const content = diagrams.map((diagram, index) => `## Diagram ${index}\n\n${diagram}`).join('\n');
    const blocks = conversationBlocks([message(content)], true);
    expect(blocks.map(block => block.message.content).join('')).toBe(content);
    for (const diagram of diagrams) {
      expect(blocks.filter(block => block.message.content.includes(diagram))).toHaveLength(1);
    }
    const output = await frame(content, 120);
    expect(output).not.toContain('sequenceDiagram');
    for (let index = 0; index < 6; index++) {
      expect(output).toContain(`Parent${index}`);
      expect(output).toContain(`Request${index}`);
      expect(output).toContain(`Result${index}`);
    }
  });

  it.each([
    ['```ts', '```', '\n'],
    ['~~~text', '~~~', '\n'],
    [' ````text', ' `````', '\r\n'],
  ])('moves a boundary before the entire %s code block', (open, close, newline) => {
    const prefix = ('Prose before the code block.' + newline).repeat(90);
    const code = [open, 'x'.repeat(4000), close, ''].join(newline);
    const content = prefix + code + 'Prose after the code block.';
    const blocks = conversationBlocks([message(content)], true);
    expect(blocks.map(block => block.message.content).join('')).toBe(content);
    expect(blocks.filter(block => block.message.content.includes(code))).toHaveLength(1);
    expect(blocks.every(block => !block.initialCodeFence)).toBe(true);
  });

  it('keeps an unfinished oversized block whole until it closes', () => {
    const prefix = 'Before\n'.repeat(400);
    const code = '```text\n' + 'literal **code**\n'.repeat(300);
    for (const suffix of ['', '```\nAfter']) {
      const content = prefix + code + suffix;
      const blocks = conversationBlocks([message(content)], true);
      expect(blocks.map(block => block.message.content).join('')).toBe(content);
      expect(blocks.filter(block => block.message.content.includes(code))).toHaveLength(1);
    }
  });

  it('still bounds prose fragments and preserves surrogate pairs', () => {
    const content = 'x'.repeat(2999) + '😀' + 'plain text '.repeat(1000);
    const blocks = conversationBlocks([message(content)], true);
    expect(blocks.map(block => block.message.content).join('')).toBe(content);
    expect(blocks.every(block => block.message.content.length <= 3000)).toBe(true);
    expect(blocks.every(block => !/[\uD800-\uDBFF]$/.test(block.message.content))).toBe(true);
  });
});

describe('shared Markdown fence rules', () => {
  it('does not close a fence with a different type, shorter marker or info string', () => {
    const fence = advanceMarkdownFence('````text', undefined)!;
    for (const line of ['```', '~~~~', '````ts', '    ````']) {
      expect(advanceMarkdownFence(line, fence)).toBe(fence);
      const content = '````text\nsource\n' + line + '\n';
      expect(findEnclosingCodeBlockStart(content, content.length)).toBe(0);
    }
    expect(advanceMarkdownFence(' ````` ', fence)).toBeUndefined();
  });

  it('rejects inline backtick runs as an opening fence', () => {
    expect(advanceMarkdownFence('```inline```', undefined)).toBeUndefined();
    expect(advanceMarkdownFence('    ```text', undefined)).toBeUndefined();
  });
});