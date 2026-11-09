import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import stringWidth from 'string-width';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BannerHeader, BANNER_LINKS } from '../src/components/Banner/BannerHeader.js';
import { createKeypressProcessor, type Key } from '../src/contexts/KeypressContext.js';
import { setUiLanguage } from '../src/i18n/index.js';
import { setActiveTheme } from '../src/themes/index.js';
import { openExternalUrl } from '../src/utils/openExternalUrl.js';

vi.mock('../src/utils/openExternalUrl.js', () => ({ openExternalUrl: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../src/utils/logger.js', () => ({ logger: { warn: vi.fn() } }));
const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void) => {
    React.useEffect(() => { handlers.add(handler); return () => { handlers.delete(handler); }; }, [handler]);
  }};
});
const dispatch = createKeypressProcessor(key => [...handlers].forEach(handler => handler(key)));
function mouse(button: number, x: number, y: number, release = false) {
  dispatch({ sequence: `\x1b[<${button};${x};${y}${release ? 'm' : 'M'}`,
    name: '', alt: false, ctrl: false, cmd: false, shift: false, insertable: false });
}
const plain = (frame: string) => frame.replace(/\x1b\[[0-9;]*m/g, '');
const wait = () => new Promise(resolve => setTimeout(resolve, 60));
function harness(columns = 120, interactive = true, clipped = false) {
  chalk.level = 3;
  const stdout = Object.assign(new PassThrough(), { columns, rows: 30, isTTY: true });
  let frame = '';
  const view = (active: boolean, hidden: boolean) => <Box flexDirection="column" width={columns}>
    <Text>ABOVE</Text>
    <Box paddingLeft={2} height={hidden ? 0 : undefined} overflowY="hidden" flexDirection="column">
      <BannerHeader columns={columns - 2} version="9.9.9" interactive={active} />
    </Box>
    <Text>BELOW</Text>
  </Box>;
  const app = render(view(interactive, clipped), { stdout, stdin: new PassThrough(),
    patchConsole: false, exitOnCtrlC: false, maxFps: 0, onRender: ({ output }) => { frame = output; } });
  return {
    frame: () => frame,
    point: (text: string) => {
      const lines = plain(frame).split('\n');
      const row = lines.findIndex(line => line.includes(text));
      expect(row).toBeGreaterThanOrEqual(0);
      return { x: stringWidth(lines[row].slice(0, lines[row].indexOf(text))) + 1, y: row + 1 };
    },
    rerender: (active: boolean, hidden = false) => app.rerender(view(active, hidden)),
    close: () => { app.unmount(); app.cleanup(); },
  };
}
afterEach(() => { setUiLanguage('en'); setActiveTheme('dark'); vi.clearAllMocks(); });

describe('banner navigation', () => {
  it.each([20, 40, 48, 80, 120])('keeps all four links and version within %i columns', async columns => {
    setUiLanguage('zh-CN');
    const test = harness(columns, false);
    try {
      await wait();
      const frame = plain(test.frame());
      expect(frame).toContain('Siada CLI v9.9.9');
      expect(frame.split('\n')[1]).toMatch(/^\s*─ Siada CLI/);
      expect(frame).toContain('☆ Star');
      for (const label of ['Doc', 'Help', 'News']) expect(frame).toContain(label);
      for (const line of frame.split('\n')) expect(stringWidth(line)).toBeLessThanOrEqual(columns);
      if (columns === 120) {
        expect(frame).toContain('使用手册(Doc)');
        expect(frame).toContain('新闻(News)');
        const header = frame.split('\n')[1];
        expect(header.indexOf('Star')).toBeLessThan(header.indexOf('Doc'));
        expect(header).toMatch(/News\) ──$/);
        expect(header).not.toMatch(/Star.*─.*Doc/);
      }
      expect(test.frame()).not.toMatch(/\x1b\[48;/);
    } finally { test.close(); }
  });

  it('opens each exact URL once after a left-button press and release', async () => {
    const test = harness();
    try {
      await wait();
      for (const link of BANNER_LINKS) {
        const point = test.point(link.en);
        mouse(0, point.x, point.y); mouse(0, point.x, point.y, true);
        await wait();
        expect(openExternalUrl).toHaveBeenLastCalledWith(link.url, expect.any(AbortSignal));
      }
      expect(openExternalUrl).toHaveBeenCalledTimes(4);
    } finally { test.close(); }
  });

  it('opens the version title anchor while leaving its leading rule inert', async () => {
    const test = harness();
    try {
      await wait();
      const point = test.point('Siada CLI v9.9.9');
      mouse(0, point.x - 2, point.y); mouse(0, point.x - 2, point.y, true);
      expect(openExternalUrl).not.toHaveBeenCalled();
      mouse(0, point.x, point.y); mouse(0, point.x, point.y, true);
      await wait();
      expect(openExternalUrl).toHaveBeenCalledTimes(1);
      expect(openExternalUrl).toHaveBeenLastCalledWith(
        'https://github.com/liauto-siada/siada-cli',
        expect.any(AbortSignal),
      );
    } finally { test.close(); }
  });

  it('highlights the whole padded block without changing its text or position', async () => {
    const test = harness();
    try {
      await wait();
      const baseline = plain(test.frame());
      const point = test.point('Help');
      mouse(35, point.x - 1, point.y); await wait();
      expect(plain(test.frame())).toBe(baseline);
      expect(test.frame()).toMatch(/\x1b\[48;2;48;56;67m/);
      mouse(35, 1, 1); await wait();
      expect(test.frame()).not.toMatch(/\x1b\[48;/);
      setActiveTheme('light');
      mouse(35, point.x, point.y); await wait();
      expect(test.frame()).toMatch(/\x1b\[48;2;231;234;238m/);
    } finally { test.close(); }
  });

  it('ignores dragging, modifiers, unmatched releases, line clicks and disabled controls', async () => {
    const test = harness();
    try {
      await wait();
      const point = test.point('Help');
      mouse(0, point.x, point.y, true);
      mouse(0, point.x, point.y); mouse(32, point.x + 1, point.y);
      mouse(32, point.x, point.y); mouse(0, point.x, point.y, true);
      mouse(4, point.x, point.y); mouse(4, point.x, point.y, true);
      mouse(0, 25, point.y); mouse(0, 25, point.y, true);
      test.rerender(false); await wait();
      mouse(0, point.x, point.y); mouse(0, point.x, point.y, true);
      expect(openExternalUrl).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('clears hover on clipping and never activates a header hidden behind another row', async () => {
    const test = harness();
    try {
      await wait();
      const point = test.point('Star');
      mouse(35, point.x, point.y); await wait();
      test.rerender(true, true); await wait();
      mouse(0, point.x, point.y); mouse(0, point.x, point.y, true);
      expect(openExternalUrl).not.toHaveBeenCalled();
      expect(plain(test.frame())).not.toContain('Star');
      mouse(35, 1, 1);
      test.rerender(true); await wait();
      expect(test.frame()).not.toMatch(/\x1b\[48;/);
    } finally { test.close(); }
  });

  it('shows an opening error and aborts the owned process when unmounted', async () => {
    vi.mocked(openExternalUrl).mockRejectedValueOnce(new Error('handler unavailable'));
    const test = harness();
    let signal: AbortSignal | undefined;
    try {
      await wait();
      const point = test.point('Star');
      mouse(0, point.x, point.y); mouse(0, point.x, point.y, true);
      await wait();
      expect(plain(test.frame())).toContain('Could not open link');
      signal = vi.mocked(openExternalUrl).mock.calls[0][1];
    } finally { test.close(); }
    expect(signal?.aborted).toBe(true);
    expect(handlers.size).toBe(0);
  });
});