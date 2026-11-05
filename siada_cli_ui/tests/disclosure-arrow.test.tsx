import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DisclosureArrow } from '../src/components/common/DisclosureArrow.js';
import { DemoWorkStatus } from '../src/components/layouts/DemoWorkStatus.js';
import { setActiveTheme } from '../src/themes/index.js';
import { colors } from '../src/utils/colors.js';

const handlers = new Set<(key: { name: string; sequence: string }) => void>();
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: { name: string; sequence: string }) => void,
    options: { isActive?: boolean } = {}) => {
    React.useEffect(() => {
      if (options.isActive === false) return;
      handlers.add(handler);
      return () => { handlers.delete(handler); };
    }, [handler, options.isActive]);
  }};
});

const originalColorLevel = chalk.level;
const wait = () => new Promise(resolve => setTimeout(resolve, 80));
const rgb = (hex: string) => hex.slice(1).match(/../g)!.map(value => parseInt(value, 16)).join(';');

function harness(node: React.ReactNode) {
  chalk.level = 3;
  const stdout = Object.assign(new PassThrough(), { columns: 40, rows: 4, isTTY: true });
  let frame = '';
  const app = render(<Box width={40}>{node}</Box>, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { frame = output; },
  });
  return { frame: () => frame, close: () => { app.unmount(); app.cleanup(); } };
}

describe('disclosure arrow', () => {
  afterEach(() => { chalk.level = originalColorLevel; setActiveTheme('dark'); });

  it.each(['dark', 'light'] as const)('paints the hovered glyph in the tool accent and bold in %s mode', async theme => {
    setActiveTheme(theme);
    const test = harness(<Text color={colors.content.secondary}>
      <DisclosureArrow glyph="›" hovered />
    </Text>);
    try {
      await wait();
      const frame = test.frame();
      expect(frame).toContain(`38;2;${rgb(colors.info)}m›`);
      expect(frame).toContain('\x1b[1m');
    } finally { test.close(); }
  });

  it('keeps the resting glyph in the same accent without bold so the row reads as clickable', async () => {
    const test = harness(<Text color={colors.content.secondary}>
      <DisclosureArrow glyph="⌄" />
    </Text>);
    try {
      await wait();
      const frame = test.frame();
      expect(frame).toContain(`38;2;${rgb(colors.info)}m⌄`);
      expect(frame).not.toContain('\x1b[1m');
    } finally { test.close(); }
  });

  it('paints the preview section arrow in the tool accent at rest and bolds it while hovered', async () => {
    chalk.level = 3;
    let frame = '';
    const stdout = Object.assign(new PassThrough(), { columns: 40, rows: 8, isTTY: true });
    const app = render(<Box width={40} flexDirection="column">
      <DemoWorkStatus tasks={[]} agents={[{ id: 'agent-1', title: 'Probe agent', status: 'running' }]}
        width={40} rows={8} expanded={null} onTask={() => {}} onAgent={() => {}}
        onExpandedChange={() => {}} />
    </Box>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output; },
    });
    try {
      await wait();
      const accent = `38;2;${rgb(colors.info)}m`;
      expect(frame.replace(/\x1b\[[0-9;]*m/g, '')).toContain('› Agents');
      expect(frame).toContain(`${accent}›`);
      [...handlers].forEach(handler => handler({ name: 'mousemove', sequence: '\x1b[<35;1;1M' }));
      await wait();
      expect(frame).toContain(`${accent}›`);
    } finally { app.unmount(); app.cleanup(); }
  });
});
