import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, render } from '@jrichman/ink';
import stringWidth from 'string-width';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownText } from '../src/components/common/MarkdownText.js';
import { renderMermaidDiagram } from '../src/components/markdown/MermaidDiagram.js';

const source = 'flowchart LR\n A[收到请求] --> B[返回结果]';
const fenced = `\`\`\`mermaid\n${source}\n\`\`\``;

async function frame(content: string, columns = 80, maxDiagramHeight?: number): Promise<string> {
  const stdout = Object.assign(new PassThrough(), { columns, rows: 40 });
  let output: string | undefined;
  const app = render(
    <Box paddingLeft={2}>
      <MarkdownText content={content} availableWidth={columns - 2} maxDiagramHeight={maxDiagramHeight} />
    </Box>,
    {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: value => { output = value.output.replace(/\x1b\[[0-9;]*m/g, ''); },
    },
  );
  try {
    await vi.waitFor(() => expect(output).toBeDefined());
    return output!;
  } finally {
    app.unmount();
    app.cleanup();
  }
}

describe('Mermaid rendering boundaries', () => {
  it.each([
    ['graph TD\n A --> B', 'A'],
    ['stateDiagram-v2\n [*] --> Idle\n Idle --> Running', 'Idle'],
    ['classDiagram\n Animal <|-- Dog', 'Animal'],
    ['erDiagram\n CUSTOMER ||--o{ ORDER : places', 'CUSTOMER'],
    ['sequenceDiagram\n participant U as 用户\n participant S as 服务\n U->>S: 请求', '用户'],
  ])('renders supported diagram syntax: %s', (input, label) => {
    const art = renderMermaidDiagram(input, 120);
    expect(art).not.toBeNull();
    expect(art!.plain.join('\n')).toContain(label);
  });

  it('strips terminal escape sequences in diagram labels', () => {
    const art = renderMermaidDiagram('flowchart LR\n A["safe\u001b[2J"] --> B', 80);
    expect(art).not.toBeNull();
    expect(art!.plain.join('\n')).not.toContain('\u001b');
  });

  it('fits Chinese labels and preserves their border columns', () => {
    const art = renderMermaidDiagram(source, 80)!;
    expect(art).not.toBeNull();
    const rows = art.plain;
    expect(rows.join('\n')).toContain('收到请求');
    const endings = rows.map(row => stringWidth(row));
    expect(new Set(endings).size).toBe(1);
  });

  it('accepts the exact width and height and rejects one cell less', () => {
    const art = renderMermaidDiagram(source, 80)!;
    expect(renderMermaidDiagram(source, art.width, art.plain.length)).not.toBeNull();
    expect(renderMermaidDiagram(source, art.width - 1)).toBeNull();
    expect(renderMermaidDiagram(source, 80, art.plain.length - 1)).toBeNull();
  });

  it.each([
    '',
    'pie\n "Dogs" : 4',
    'flowchart LR\n A[Start] invalid',
    'stateDiagram-v2\n A --> B\n unreadable final line',
    'flowchart LR\n' + ' '.repeat(100001),
  ])('keeps unsupported, invalid and excessive source: %s', input => {
    expect(renderMermaidDiagram(input, 80)).toBeNull();
  });

  it('renders closed Mermaid fences in actual Ink output', async () => {
    const output = await frame(fenced);
    expect(output).toContain('┌');
    expect(output).toContain('收到请求');
    expect(output).not.toContain('flowchart LR');
    expect(output.split('\n').every(line => stringWidth(line) <= 80)).toBe(true);
  });

  it('retains source before the fence closes', async () => {
    const output = await frame(`\`\`\`mermaid\n${source}`);
    expect(output).toContain('flowchart LR');
    expect(output).not.toContain('┌');
  });

  it('retains source when the width or height does not fit', async () => {
    expect(await frame(fenced, 12)).not.toContain('┌');
    expect(await frame(fenced, 80, 2)).toContain('flowchart LR');
  });

  it.each([
    `~~~mmd\n${source}\n~~~`,
    `\`\`\`\`MERMAID\n${source}\n\`\`\`\``,
  ])('accepts alternative Mermaid fence forms', async content => {
    expect(await frame(content)).toContain('┌');
  });

  it('does not close a longer fence with a shorter delimiter', async () => {
    const output = await frame(`\`\`\`\`mermaid\n${source}\n\`\`\``);
    expect(output).toContain('flowchart LR');
    expect(output).not.toContain('┌');
  });

  it('preserves ordinary code content', async () => {
    const output = await frame('```ts\nconst value = 42;\n```');
    expect(output).toContain('const value = 42;');
    expect(output).not.toContain('┌');
  });

  it('preserves paragraph spacing on both sides of tables', async () => {
    const output = await frame('Before\n\n| Name | Value |\n| --- | --- |\n| item | 42 |\n\nAfter');
    expect(output).toMatch(/Before\n\s*\n/);
    expect(output).toMatch(/\n\s*\n\s*After/);
  });
});