import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { Box, render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BannerHeader } from '../src/components/Banner/BannerHeader.js';
import { setUiLanguage } from '../src/i18n/index.js';
import { setActiveTheme } from '../src/themes/index.js';

vi.mock('../src/utils/openExternalUrl.js', () => ({ openExternalUrl: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../src/utils/logger.js', () => ({ logger: { warn: vi.fn() } }));
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: () => React.useEffect(() => {}, []) };
});

const LIT = '38;2;244;252;255';
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const plain = (frame: string) => frame.replace(/\x1b\[[0-9;]*m/g, '');

function harness(interactive = true, columns = 120) {
  chalk.level = 3;
  const stdout = Object.assign(new PassThrough(), { columns, rows: 30, isTTY: true });
  const frames: string[] = [];
  const app = render(
    <Box flexDirection="column" width={columns}>
      <BannerHeader columns={columns} version="9.9.9" interactive={interactive} />
    </Box>,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => frames.push(output) });
  return { frames, close: () => { app.unmount(); app.cleanup(); } };
}

afterEach(() => { setUiLanguage('en'); setActiveTheme('dark'); vi.clearAllMocks(); });

describe('banner star hint frames', () => {
  it('lights the star once, then settles without further redraws', async () => {
    const test = harness();
    try {
      await wait(2200);
      expect(test.frames.some(frame => frame.includes(LIT))).toBe(true);
      // Lighting only recolors the row: text and column positions never move.
      const baseline = plain(test.frames[0]);
      for (const frame of test.frames) expect(plain(frame)).toBe(baseline);

      await wait(1500);
      const settled = test.frames.at(-1)!;
      expect(settled).not.toContain(LIT);
      const count = test.frames.length;
      await wait(220);
      expect(test.frames).toHaveLength(count);
      expect(plain(settled)).toContain('☆ Star');
    } finally { test.close(); }
  });

  it('stays static on a non-interactive banner', async () => {
    const test = harness(false);
    try {
      await wait(150);
      const count = test.frames.length;
      await wait(900);
      expect(test.frames).toHaveLength(count);
      expect(test.frames.join('')).not.toContain(LIT);
    } finally { test.close(); }
  });
});
