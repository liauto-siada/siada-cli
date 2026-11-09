import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createKeypressProcessor, emitKeys, type Key } from '../src/contexts/KeypressContext.js';

vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

function input() {
  const events: Key[] = [];
  const parser = emitKeys(createKeypressProcessor(key => events.push(key)));
  parser.next();
  return { events, feed: (data: string) => { for (const character of data) parser.next(character); } };
}

beforeEach(() => {
  vi.stubEnv('TERM_PROGRAM', 'Apple_Terminal');
  vi.stubEnv('TERMINAL_EMULATOR', '');
  vi.stubEnv('TERM', 'xterm-256color');
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); });

describe('keyboard scrolling input', () => {
  it.each([
    ['\x1b[1;5A', 'up'],
    ['\x1b[1;5B', 'down'],
    ['\x1b[1;5A\x1b[1;5A', 'up'],
  ])('parses terminal Ctrl+arrow sequence %j', (sequence, name) => {
    const test = input();
    test.feed(sequence);
    expect(test.events).toHaveLength(sequence === '\x1b[1;5A\x1b[1;5A' ? 2 : 1);
    for (const event of test.events) {
      expect(event).toMatchObject({ name, ctrl: true, alt: false, shift: false,
        cmd: false, insertable: false });
    }
  });
});

describe('SGR pointer input', () => {
  it.each([
    ['JetBrains-JediTerm', ''],
    ['JediTerm', ''],
    ['Apple_Terminal', 'JetBrains-JediTerm'],
  ])('normalizes JediTerm hover with program=%s emulator=%s', (program, emulator) => {
    vi.stubEnv('TERM_PROGRAM', program);
    vi.stubEnv('TERMINAL_EMULATOR', emulator);
    const test = input();
    test.feed('\x1b[<3;12;8M');
    expect(test.events).toEqual([expect.objectContaining({
      name: 'mousemove', sequence: '\x1b[<35;12;8M', insertable: false,
      shift: false, alt: false, ctrl: false,
    })]);
  });

  it('preserves modifier bits when normalizing JediTerm hover', () => {
    vi.stubEnv('TERMINAL_EMULATOR', 'JetBrains-JediTerm');
    const test = input();
    test.feed('\x1b[<7;12;8M\x1b[<11;13;8M\x1b[<19;14;8M');
    expect(test.events.map(key => key.sequence)).toEqual([
      '\x1b[<39;12;8M', '\x1b[<43;13;8M', '\x1b[<51;14;8M',
    ]);
    expect(test.events[0]).toMatchObject({ name: 'mousemove', shift: true });
    expect(test.events[1]).toMatchObject({ name: 'mousemove', alt: true });
    expect(test.events[2]).toMatchObject({ name: 'mousemove', ctrl: true });
  });

  it.each(['Apple_Terminal', 'WezTerm', 'vscode', ''])(
    'does not reinterpret ambiguous button 3 outside JediTerm (%s)', program => {
      vi.stubEnv('TERM_PROGRAM', program);
      const test = input();
      test.feed('\x1b[<3;12;8M\x1b[<3;12;8m');
      expect(test.events).toEqual([]);
    },
  );

  it('keeps JediTerm clicks, releases, drag and wheel input distinct', () => {
    vi.stubEnv('TERMINAL_EMULATOR', 'JetBrains-JediTerm');
    const test = input();
    test.feed('\x1b[<0;2;3M\x1b[<32;3;3M\x1b[<0;3;3m' +
      '\x1b[<3;3;3m\x1b[<1;3;3m\x1b[<2;3;3M\x1b[<64;3;3M\x1b[<65;3;3M');
    expect(test.events.map(key => key.name)).toEqual([
      'mouseclick', 'mousemove', 'mouserelease', 'mouseright', 'wheelup', 'wheeldown',
    ]);
    expect(test.events[1].sequence).toBe('\x1b[<32;3;3M');
    expect(test.events[2].sequence).toBe('\x1b[<0;3;3m');
    expect(test.events.every(key => !key.insertable)).toBe(true);
  });

  it('keeps standard motion unchanged inside JediTerm', () => {
    vi.stubEnv('TERMINAL_EMULATOR', 'JetBrains-JediTerm');
    const test = input();
    test.feed('\x1b[<35;12;8M');
    expect(test.events).toEqual([expect.objectContaining({
      name: 'mousemove', sequence: '\x1b[<35;12;8M', insertable: false,
    })]);
  });
  it('delivers motion and modified motion as non-insertable events', () => {
    const test = input();
    test.feed('\x1b[<35;12;8M\x1b[<39;13;8M\x1b[<43;14;8M\x1b[<51;15;8M');
    expect(test.events.map(key => key.name)).toEqual(['mousemove', 'mousemove', 'mousemove', 'mousemove']);
    expect(test.events.every(key => !key.insertable)).toBe(true);
    expect(test.events[1].shift).toBe(true);
    expect(test.events[2].alt).toBe(true);
    expect(test.events[3].ctrl).toBe(true);
  });

  it('keeps button presses, motion and wheel events distinct and filters releases', () => {
    const test = input();
    test.feed('\x1b[<0;2;3M\x1b[<0;2;3m\x1b[<1;2;3M\x1b[<2;2;3M' +
      '\x1b[<32;3;3M\x1b[<64;3;3M\x1b[<65;3;3M');
    expect(test.events.map(key => key.name)).toEqual(['mouseclick', 'mouserelease', 'mousemiddle', 'mouseright', 'mousemove', 'wheelup', 'wheeldown']);
    expect(test.events.every(key => !key.insertable)).toBe(true);
  });
  it('emits middle-button presses once, preserves modifiers and ignores their releases', () => {
    const test = input();
    test.feed('\x1b[<1;2;3M\x1b[<1;2;3m\x1b[<17;2;3M');
    expect(test.events).toHaveLength(2);
    expect(test.events[0]).toMatchObject({ name: 'mousemiddle', insertable: false, ctrl: false });
    expect(test.events[1]).toMatchObject({ name: 'mousemiddle', insertable: false, ctrl: true });
  });

  it('emits right presses once and preserves modifiers without treating drag as a press', () => {
    const test = input();
    test.feed('\x1b[<2;2;3M\x1b[<2;2;3m\x1b[<34;3;3M\x1b[<18;2;3M\x1b[<6;2;3M');
    expect(test.events.map(key => key.name)).toEqual(['mouseright', 'mousemove', 'mouseright', 'mouseright']);
    expect(test.events[0]).toMatchObject({ insertable: false, ctrl: false, shift: false });
    expect(test.events[2]).toMatchObject({ ctrl: true, insertable: false });
    expect(test.events[3]).toMatchObject({ shift: true, insertable: false });
  });

  it.each([35, 3])('does not turn Enter into a newline after pointer code %i', button => {
    vi.stubEnv('TERMINAL_EMULATOR', 'JetBrains-JediTerm');
    vi.useFakeTimers(); vi.setSystemTime(1000);
    const test = input();
    test.feed('x');
    vi.advanceTimersByTime(100);
    test.feed(`\x1b[<${button};2;3M`);
    vi.advanceTimersByTime(5);
    test.feed('\r');
    expect(test.events.at(-1)).toMatchObject({ name: 'return', shift: false, insertable: false });
    expect(test.events.map(key => key.name)).toEqual(['x', 'mousemove', 'return']);
  });

  it('preserves fast unbracketed-paste returns and bracketed paste', () => {
    vi.useFakeTimers(); vi.setSystemTime(1000);
    const test = input();
    test.feed('x');
    vi.advanceTimersByTime(5); test.feed('\r');
    expect(test.events.at(-1)).toMatchObject({ name: 'return', shift: true, insertable: true });
    test.feed('\x1b[200~中文 draft\x1b[201~');
    expect(test.events.at(-1)).toMatchObject({ name: 'paste', sequence: '中文 draft', insertable: true });
  });
});