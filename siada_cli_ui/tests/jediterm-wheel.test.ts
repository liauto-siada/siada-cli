import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createKeypressProcessor, emitKeys, type Key } from '../src/contexts/KeypressContext.js';
import { createJediTermWheelFilter } from '../src/utils/jediTermWheel.js';

vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

function input() {
  const events: Key[] = [];
  const processor = createKeypressProcessor(key => events.push(key));
  const parser = emitKeys(processor);
  parser.next();
  return {
    events, processor,
    feed: (data: string) => { for (const character of data) parser.next(character); },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1000);
  vi.stubEnv('TERM_PROGRAM', '');
  vi.stubEnv('TERMINAL_EMULATOR', 'JetBrains-JediTerm');
  vi.stubEnv('TERM', 'xterm-256color');
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllEnvs(); });

const down = '\x1b[<65;12;8M\x1b[B\x1b[B\x1b[B';
const up = '\x1b[<64;12;8M\x1b[A\x1b[A\x1b[A';

describe('JediTerm wheel and alternate-scroll pairing', () => {
  it('delivers one wheel event and consumes its synthesized arrow burst', () => {
    const test = input();
    test.feed(down);
    expect(test.events.map(key => key.name)).toEqual(['wheeldown']);
  });

  it('drops unconfirmed upward reports throughout a downward touchpad tail', () => {
    const test = input();
    test.feed(down);
    for (let index = 0; index < 30; index++) {
      vi.advanceTimersByTime(16);
      test.feed('\x1b[<64;12;8M');
    }
    vi.advanceTimersByTime(100);
    expect(test.events.map(key => key.name)).toEqual(['wheeldown']);
  });

  it('preserves an immediate deliberate reversal in either direction', () => {
    const test = input();
    test.feed(down + up + down + up);
    expect(test.events.map(key => key.name)).toEqual([
      'wheeldown', 'wheelup', 'wheeldown', 'wheelup',
    ]);
  });

  it('pairs application-cursor arrows even across input chunks and intervening hover', () => {
    const test = input();
    test.feed('\x1b[<65;12;8M\x1bOB');
    test.feed('\x1b[<64;12;8M');
    vi.advanceTimersByTime(8);
    test.feed('\x1b[<3;12;8M\x1bOA\x1bOA');
    expect(test.events.map(key => key.name)).toEqual(['wheeldown', 'mousemove', 'wheelup']);
  });

  it('detects pairing from the first valid upward gesture', () => {
    const test = input();
    test.feed(up);
    test.feed('\x1b[<64;12;8M');
    vi.advanceTimersByTime(100);
    expect(test.events.map(key => key.name)).toEqual(['wheelup']);
  });

  it('keeps plain SGR wheels unchanged when the terminal does not synthesize arrows', () => {
    const test = input();
    test.feed('\x1b[<65;12;8M\x1b[<64;12;8M');
    expect(test.events.map(key => key.name)).toEqual(['wheeldown', 'wheelup']);
  });

  it('does not apply pairing to other terminals', () => {
    vi.stubEnv('TERMINAL_EMULATOR', '');
    vi.stubEnv('TERM_PROGRAM', 'Apple_Terminal');
    const events: Key[] = [];
    const filter = createJediTermWheelFilter(key => events.push(key));
    const wheel: Key = {
      name: 'wheelup', sequence: '\x1b[<64;12;8M',
      shift: false, alt: false, ctrl: false, cmd: false, insertable: false,
    };
    const arrow: Key = { ...wheel, name: 'up', sequence: '\x1b[A' };
    filter(wheel);
    filter(arrow);
    expect(events).toEqual([wheel, arrow]);
    filter.dispose();
  });

  it('preserves wheel modifiers and modified keyboard arrows', () => {
    const test = input();
    test.feed('\x1b[<81;12;8M\x1b[B');
    test.feed('\x1b[<64;12;8M\x1b[1;2A');
    vi.advanceTimersByTime(100);
    expect(test.events).toHaveLength(2);
    expect(test.events[0]).toMatchObject({ name: 'wheeldown', ctrl: true });
    expect(test.events[1]).toMatchObject({ name: 'up', shift: true });
  });

  it('keeps a later real keyboard arrow and text entry after a phantom wheel report', () => {
    const test = input();
    test.feed(down);
    test.feed('\x1b[<64;12;8M');
    vi.advanceTimersByTime(100);
    test.feed('\x1b[Ax');
    expect(test.events.map(key => key.name)).toEqual(['wheeldown', 'up', 'x']);
  });

  it('cancels pending timers on cleanup and keeps detection local to each processor', () => {
    const test = input();
    test.feed(down + '\x1b[<64;12;8M');
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    test.processor.dispose();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(100);
    expect(test.events.map(key => key.name)).toEqual(['wheeldown']);
    const other = input();
    other.feed('\x1b[<64;12;8M');
    expect(other.events.map(key => key.name)).toEqual(['wheelup']);
  });
});