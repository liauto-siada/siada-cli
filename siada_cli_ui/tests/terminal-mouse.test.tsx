import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, render } from '@jrichman/ink';
import { describe, expect, it } from 'vitest';
import { useMouseTracking } from '../src/hooks/useMouseTracking.js';
import { withEditorTerminal } from '../src/utils/editorTerminal.js';

// Model terminals that apply only the first parameter of each DEC mode command.
function terminal() {
  const modes = new Set([1007]);
  const writes: string[] = [];
  const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 80, isTTY: true });
  stdout.on('data', chunk => {
    const text = chunk.toString();
    writes.push(text);
    for (const match of text.matchAll(/\x1b\[\?(\d+)(?:;\d+)*([hl])/g)) {
      const mode = Number(match[1]);
      if (![1000, 1002, 1003, 1006, 1007].includes(mode)) continue;
      if (match[2] === 'h') modes.add(mode);
      else modes.delete(mode);
    }
  });
  return { stdout, modes, writes };
}

function Owner() {
  useMouseTracking();
  return null;
}

const wait = () => new Promise(resolve => setTimeout(resolve, 60));

describe('terminal pointer mode ownership', () => {
  it('enables SGR and motion without synthetic arrows and keeps nested ownership', async () => {
    const test = terminal();
    const view = (nested: boolean) => <Box><Owner />{nested && <Owner />}</Box>;
    const app = render(view(false), {
      stdout: test.stdout, stdin: new PassThrough(), patchConsole: false,
      exitOnCtrlC: false, maxFps: 0,
    });
    try {
      await wait();
      expect([...test.modes].sort()).toEqual([1000, 1002, 1003, 1006]);
      const modeWrites = test.writes.filter(text => text.includes('\x1b[?1006h')).length;
      app.rerender(view(true)); await wait();
      app.rerender(view(false)); await wait();
      expect(test.modes.has(1006)).toBe(true);
      expect(test.modes.has(1007)).toBe(false);
      expect(test.writes.filter(text => text.includes('\x1b[?1006h'))).toHaveLength(modeWrites);
    } finally { app.unmount(); app.cleanup(); }
    expect([...test.modes]).toEqual([]);
  });

  it.each([false, true])('releases and restores editor modes, failure=%s', async failure => {
    const test = terminal();
    const app = render(<Owner />, {
      stdout: test.stdout, stdin: new PassThrough(), patchConsole: false,
      exitOnCtrlC: false, maxFps: 0,
    });
    const stdin = {
      isRaw: true, readableFlowing: true,
      pause() {}, resume() {}, setRawMode() {},
    } as unknown as NodeJS.ReadStream;
    try {
      await wait();
      const edit = () => withEditorTerminal(() => {
        expect([1000, 1002, 1003, 1006, 1007].some(mode => test.modes.has(mode))).toBe(false);
        // Editors can alter pointer encoding and alternate scrolling.
        test.stdout.write('\x1b[?1007h\x1b[?1006l');
        if (failure) throw Error('synthetic editor failure');
      }, {
        stdin, stdout: test.stdout, alternateBuffer: true, kittyKeyboard: false,
        mouseTracking: true, repaint() {},
      });
      if (failure) expect(edit).toThrow('synthetic editor failure');
      else edit();
      for (const mode of [1000, 1002, 1003, 1006]) expect(test.modes.has(mode)).toBe(true);
      expect(test.modes.has(1007)).toBe(false);
    } finally { app.unmount(); app.cleanup(); }
    for (const mode of [1000, 1002, 1003, 1006, 1007]) expect(test.modes.has(mode)).toBe(false);
  });
});