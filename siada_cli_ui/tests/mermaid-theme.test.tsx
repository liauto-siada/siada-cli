import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import chalk from 'chalk';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MermaidDiagram, renderMermaidDiagram } from '../src/components/markdown/MermaidDiagram.js';
import { applyMarkdownTheme, theme } from '../src/components/markdown/theme.js';

const originalColorLevel = chalk.level;
afterEach(() => {
  applyMarkdownTheme('dark');
  chalk.level = originalColorLevel;
});

describe('Mermaid theme rendering', () => {
  it.each(['dark', 'light'] as const)('uses the %s palette for borders, labels and edges', async palette => {
    applyMarkdownTheme(palette);
    chalk.level = 3;
    const art = renderMermaidDiagram('flowchart LR\n A[开始] --> B[完成]', 80);
    expect(art).not.toBeNull();
    const stdout = Object.assign(new PassThrough(), { columns: 80, rows: 24 });
    let output = '';
    const app = render(<MermaidDiagram art={art!} />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: frame => { output = frame.output; },
    });
    try {
      await vi.waitFor(() => expect(output).toContain('开始'));
      for (const color of [theme.border.default, theme.text.accent, theme.text.response]) {
        const channels = color.slice(1).match(/.{2}/g)!.map(channel => parseInt(channel, 16));
        expect(output).toContain(`\x1b[38;2;${channels.join(';')}m`);
      }
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});