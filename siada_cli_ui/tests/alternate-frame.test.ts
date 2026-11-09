import { PassThrough } from 'node:stream';
import { afterEach, describe, expect, it } from 'vitest';
import logUpdate from '../node_modules/@jrichman/ink/build/log-update.js';
import { configureTerminalWidths, displayWidth } from '../src/utils/terminalWidth.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

afterEach(() => configureTerminalWidths());

function fixture() {
  configureTerminalWidths({ '▆': 2, '●': 2 }, true);
  let columns = 11;
  let screen = new TerminalScreen(8, 12, displayWidth, true);
  const stdout = new PassThrough();
  const writes: string[] = [];
  stdout.on('data', chunk => { const text = chunk.toString(); writes.push(text); screen.feed(text); });
  const update = logUpdate.create(stdout, {
    alternateBuffer: true, incremental: true, showCursor: true,
    getRows: () => 8, getColumns: () => columns,
  });
  return {
    update: (text: string) => update(text, [], undefined, { row: 7, col: 0 }),
    screen: () => screen,
    writes,
    resize: () => { columns = 6; screen = new TerminalScreen(8, 7, displayWidth, true); },
    close: () => { update.done(); stdout.destroy(); },
  };
}

describe('bounded alternate-screen updates', () => {
  it('clips wide glyphs before the terminal can wrap them into the following row', () => {
    const test = fixture();
    try {
      test.update(`${'▆'.repeat(9)}\nSTATIC\nprogress\n\n\n\n\nINPUT`);
      const lines = test.screen().display().split('\n');
      expect(lines[0]).toBe('▆'.repeat(5));
      expect(lines[1]).toBe('STATIC');
      expect(lines[7]).toBe('INPUT');
      expect(test.writes.join('')).not.toContain('\n');
    } finally { test.close(); }
  });

  it('keeps unchanged rows fixed during repeated streaming and clears a shortened row', () => {
    const test = fixture();
    try {
      test.update('▆▆▆▆▆\nSTATIC\nold text\n\n\n\n\nINPUT');
      const initialWrites = test.writes.length;
      for (let index = 0; index < 50; index++) {
        test.update(`A\nSTATIC\n● ${index}\n\n\n\n\nINPUT`);
      }
      const text = test.screen().display();
      expect(text.split('\n')[0]).toBe('A');
      expect(text.split('\n')[2]).toBe('● 49');
      expect(text.match(/STATIC/g)).toHaveLength(1);
      expect(text.match(/INPUT/g)).toHaveLength(1);
      expect(text).not.toContain('old text');
      expect(test.writes.slice(initialWrites).join('')).not.toContain('STATIC');
    } finally { test.close(); }
  });

  it('clears rows removed from the frame without moving retained rows', () => {
    const test = fixture();
    try {
      test.update('one\ntwo\nobsolete');
      test.update('one\nshort');
      expect(test.screen().display().split('\n').slice(0, 3)).toEqual(['one', 'short', '']);
    } finally { test.close(); }
  });

  it('repaints at the new width after resize', () => {
    const test = fixture();
    try {
      const frame = `${'▆'.repeat(8)}\nSTATIC\n\n\n\n\n\nINPUT`;
      test.update(frame);
      test.resize();
      test.update(frame);
      const lines = test.screen().display().split('\n');
      expect(lines[0]).toBe('▆'.repeat(3));
      expect(lines[1]).toBe('STATIC');
      expect(lines[7]).toBe('INPUT');
    } finally { test.close(); }
  });

  it('clears the reserved bottom row even when it was not part of the cached frame', () => {
    const test = fixture();
    try {
      test.update('one\nstable');
      test.screen().feed('\x1b[8;1HSTALE_BOTTOM');
      expect(test.screen().display()).toContain('STALE_BOTTOM');
      test.update('changed\nstable');
      expect(test.screen().display()).not.toContain('STALE_BOTTOM');
      expect(test.screen().display().split('\n')[1]).toBe('stable');
    } finally { test.close(); }
  });

  it('retains color sequences when clipping at a wide glyph boundary', () => {
    const test = fixture();
    try {
      test.update(`\x1b[38;2;10;20;30m${'▆'.repeat(8)}\x1b[39m\nSTATIC`);
      expect(test.writes.join('')).toContain('\x1b[38;2;10;20;30m');
      expect(test.screen().display().split('\n')[0]).toBe('▆'.repeat(5));
    } finally { test.close(); }
  });

  it('preserves input and its cursor while a resized terminal still has the old frame height', () => {
    configureTerminalWidths();
    let rows = 8;
    let screen = new TerminalScreen(rows, 12);
    const stdout = Object.assign(new PassThrough(), { __siadaBottomAnchored: true });
    const writes: string[] = [];
    stdout.on('data', chunk => { const text = chunk.toString(); writes.push(text); screen.feed(text); });
    const update = logUpdate.create(stdout, {
      alternateBuffer: true, incremental: true, showCursor: true,
      getRows: () => rows, getColumns: () => 12,
    });
    const frame = 'history\nhistory\nhistory\nhistory\nhistory\nline\n─\nINPUT';
    try {
      update(frame, [], undefined, { row: 7, col: 5 });
      rows = 4;
      screen = new TerminalScreen(rows, 12);
      update(frame, [], undefined, { row: 7, col: 5 });
      expect(screen.display().split('\n')).toEqual(['line', '─', 'INPUT', '']);
      expect(writes.at(-1)).toContain('\x1b[3;6H');
    } finally { update.done(); stdout.destroy(); }
  });
});