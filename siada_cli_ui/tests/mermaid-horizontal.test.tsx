import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, render, useApp } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import stringWidth from 'string-width';
import { KeypressProvider } from '../src/contexts/KeypressContext.js';
import { MermaidDiagram, renderMermaidDiagram, sliceMermaidRow } from '../src/components/markdown/MermaidDiagram.js';
import { MarkdownText } from '../src/components/common/MarkdownText.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import { ConversationViewport } from '../src/components/Chat/ConversationViewport.js';
import { isMermaidControlAt } from '../src/utils/mermaidControls.js';

vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const source = `flowchart LR
  subgraph INPUT["① 输入"]
    direction TB
    A["工单编号"] ~~~ B["时间 + 现象"]
  end
  subgraph EVIDENCE["② 证据"]
    direction TB
    C["日志下载"] ~~~ D["日志解压"] ~~~ E["异常解析"]
  end
  subgraph ANALYSIS["③ 分析"]
    direction TB
    F["主线程分析"] ~~~ G["锁与等待链"] ~~~ H["资源分析"]
  end
  subgraph RESULT["④ 结论"]
    direction TB
    I["根因机制"] ~~~ J["模块定位"] ~~~ K["归档"]
  end
  INPUT --> EVIDENCE --> ANALYSIS --> RESULT`;
const fenced = `\`\`\`mermaid\n${source}\n\`\`\``;
const clean = (value: string) => value.replace(/\x1b\[[0-9;]*m/g, '');
const apps: ReturnType<typeof render>[] = [];
afterEach(() => { for (const app of apps.splice(0)) { app.unmount(); app.cleanup(); } });

async function mount(content: React.ReactNode, columns = 42) {
  const stdout = Object.assign(new PassThrough(), { columns, rows: 40 });
  const stdin = Object.assign(new PassThrough(), { isTTY: false, isRaw: undefined });
  const terminal = new TerminalScreen(40, columns);
  stdout.on('data', value => terminal.feed(String(value)));
  let output: string | undefined;
  const app = render(<KeypressProvider>{content}</KeypressProvider>, {
    stdout, stdin, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: value => { output = clean(value.output); },
  });
  apps.push(app);
  await vi.waitFor(() => expect(output).toBeDefined());
  // Provider effects register the real stdin parser asynchronously.
  await vi.waitFor(() => expect(process.stdin.listenerCount('data')).toBeGreaterThan(0));
  return {
    app, stdout, terminal,
    output: () => output!,
    click: async (direction: '◀' | '▶') => {
      const lines = output!.split('\n');
      const y = lines.findIndex(line => line.includes('◀') && line.includes('▶'));
      const x = stringWidth(lines[y].slice(0, lines[y].indexOf(direction))) + 1;
      process.stdin.emit('data', `\x1b[<0;${x};${y + 1}M\x1b[<0;${x};${y + 1}m`);
      await new Promise(resolve => setTimeout(resolve, 30));
    },
  };
}

describe('Mermaid column slicing', () => {
  it('pads both partial Chinese glyph boundaries and retains span classes', () => {
    const row = [{ text: '┌中', cls: 'border' as const }, { text: '文A┐', cls: 'text' as const }];
    expect(sliceMermaidRow(row, 2, 2)).toEqual([
      { text: ' ', cls: 'border' }, { text: ' ', cls: 'text' },
    ]);
    expect(sliceMermaidRow(row, 1, 4).map(span => span.text).join('')).toBe('中文');
  });

  it('keeps emoji graphemes intact and preserves columns after clipping', () => {
    const row = [{ text: 'A👩‍💻e\u0301中Z', cls: 'text' as const }];
    expect(sliceMermaidRow(row, 2, 4).map(span => span.text).join('')).toBe(' e\u0301中');
    for (let start = 0; start < 8; start++) {
      expect(stringWidth(sliceMermaidRow(row, start, 3).map(span => span.text).join(''))).toBeLessThanOrEqual(3);
    }
  });

  it('preserves invisible-link layout without drawing connectors', () => {
    const hidden = renderMermaidDiagram('flowchart LR\n A[Left] ~~~ B[Middle] ~~~ C[Right]', 20)!;
    const visible = renderMermaidDiagram('flowchart LR\n A[Left] --> B[Middle] --> C[Right]', 20)!;
    expect(hidden.warnings).toEqual([]);
    expect(hidden.width).toBe(visible.width);
    expect(hidden.plain.join('\n')).toContain('Middle');
    expect(hidden.styled.flat().some(span => span.cls === 'edge')).toBe(false);
    expect(visible.styled.flat().some(span => span.cls === 'edge')).toBe(true);
    // Literal tildes in labels must remain text.
    expect(renderMermaidDiagram('flowchart LR\n A["literal ~~~ label"] --> B', 80)!.plain.join('\n')).toContain('~~~');
  });
});

describe('Mermaid horizontal navigation in actual Ink output', () => {
  it.each([2, 3, 4, 5, 6])('keeps navigation inside a %i-column viewport', async width => {
    const view = await mount(<MarkdownText content={fenced} availableWidth={width} />, width);
    expect(view.output()).toContain('◀');
    expect(view.output()).toContain('▶');
    expect(view.output().split('\n').every(line => stringWidth(line) <= width)).toBe(true);
    const before = view.output();
    await view.click('▶');
    expect(view.output()).not.toBe(before);
  });

  it('keeps chat text selection collapsed when an arrow is clicked', async () => {
    let selection: ReturnType<typeof useApp>['selection'];
    function Probe() { selection = useApp().selection; return null; }
    const view = await mount(<><Probe /><ConversationViewport messages={[{
      id: 'diagram', type: 'agent', author: 'Synthetic', content: fenced,
      timestamp: '2026-01-01T00:00:00Z', metadata: { subtype: 'answer' },
    }]} width={42} height={30} isCollapsed active presentation /></>);
    await vi.waitFor(() => expect(view.output()).toContain('1–39'));
    const lines = view.output().split('\n');
    const y = lines.findIndex(line => line.includes('◀') && line.includes('▶'));
    const x = stringWidth(lines[y].slice(0, lines[y].indexOf('▶')));
    expect(isMermaidControlAt(view.stdout, { x, y })).toBe(true);
    await view.click('▶');
    expect(view.output()).toContain('36–74');
    expect(selection?.isCollapsed).toBe(true);
    view.app.unmount();
    expect(isMermaidControlAt(view.stdout, { x, y })).toBe(false);
  });

  it('uses real SGR clicks to reach both ends without wrapping or losing labels', async () => {
    const view = await mount(<Box paddingLeft={2}><MarkdownText content={fenced} availableWidth={40} /></Box>);
    const art = renderMermaidDiagram(source, 40)!;
    expect(view.output()).toContain('① 输入');
    expect(view.output()).not.toContain('flowchart LR');
    expect(view.terminal.display()).toContain('▶');
    const count = Math.ceil((art.width - 40) / 36);
    const seen = [view.output()];
    for (let index = 0; index < count; index++) {
      await view.click('▶');
      seen.push(view.output());
      expect(view.output().split('\n').every(line => stringWidth(line) <= 42)).toBe(true);
      expect(view.terminal.display()).toContain('▶');
    }
    expect(view.output()).toContain('归档');
    expect(view.output()).toContain(`${art.width - 39}–${art.width} / ${art.width}`);
    for (const label of ['日志下载', '主线程分析', '根因机制']) expect(seen.join('\n')).toContain(label);
    const last = view.output();
    await view.click('▶');
    expect(view.output()).toBe(last);
    for (let index = 0; index < count; index++) await view.click('◀');
    expect(view.output()).toContain('① 输入');
    expect(view.output()).toContain(`1–40 / ${art.width}`);
    const first = view.output();
    await view.click('◀');
    expect(view.output()).toBe(first);
  });

  it('ignores releases outside the arrow, drags and modifier clicks', async () => {
    const view = await mount(<MarkdownText content={fenced} availableWidth={40} />);
    const before = view.output();
    const y = before.split('\n').findIndex(line => line.includes('◀') && line.includes('▶')) + 1;
    for (const sequence of [
      `\x1b[<0;5;${y}M\x1b[<0;8;${y}m`,
      `\x1b[<0;5;${y}M\x1b[<32;8;${y}M\x1b[<0;5;${y}m`,
      `\x1b[<4;5;${y}M\x1b[<4;5;${y}m`,
    ]) {
      process.stdin.emit('data', sequence);
      await new Promise(resolve => setTimeout(resolve, 30));
      expect(view.output()).toBe(before);
    }
  });

  it('routes clicks independently for multiple diagrams', async () => {
    const view = await mount(<MarkdownText content={`${fenced}\n\n${fenced}`} availableWidth={40} />);
    const initial = view.output();
    await view.click('▶');
    const ranges = view.output().split('\n').filter(line => line.includes(' / '));
    expect(ranges).toHaveLength(2);
    expect(ranges[0]).toContain('37–76');
    expect(ranges[1]).toContain('1–40');
    expect(view.output()).not.toBe(initial);
  });

  it('clamps the offset on resize and resets it for a different diagram', async () => {
    const art = renderMermaidDiagram(source, 40)!;
    const view = await mount(<MermaidDiagram art={art} availableWidth={40} />, 400);
    for (let index = 0; index < 10; index++) await view.click('▶');
    view.app.rerender(<KeypressProvider><MermaidDiagram art={art} availableWidth={art.width - 10} /></KeypressProvider>);
    await vi.waitFor(() => expect(view.output()).toContain(`11–${art.width} / ${art.width}`));
    const other = renderMermaidDiagram('flowchart LR\n A["New input"] --> B["Different result"]', 10)!;
    view.app.rerender(<KeypressProvider><MermaidDiagram art={other} availableWidth={30} /></KeypressProvider>);
    await vi.waitFor(() => expect(view.output()).toContain(`1–30 / ${other.width}`));
  });

  it('does not activate arrows clipped by a vertical ancestor viewport', async () => {
    const art = renderMermaidDiagram(source, 40)!;
    const view = await mount(<Box height={3} overflowY="hidden"><MermaidDiagram art={art} availableWidth={40} /></Box>);
    expect(view.output()).not.toContain('◀');
    process.stdin.emit('data', `\x1b[<0;5;${art.plain.length + 1}M\x1b[<0;5;${art.plain.length + 1}m`);
    view.app.rerender(<KeypressProvider><MermaidDiagram art={art} availableWidth={40} /></KeypressProvider>);
    await vi.waitFor(() => expect(view.output()).toContain(`1–40 / ${art.width}`));
  });
});