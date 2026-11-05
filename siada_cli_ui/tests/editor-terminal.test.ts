import { describe, expect, it, vi } from 'vitest';
import { withEditorTerminal } from '../src/utils/editorTerminal.js';

function terminal(alternateBuffer = true, kittyKeyboard = true, mouseTracking = true) {
  const events: string[] = [];
  const stdin = {
    isRaw: true, readableFlowing: true,
    pause: () => events.push('pause'),
    resume: () => events.push('resume'),
    setRawMode: (raw: boolean) => events.push(`raw:${raw}`),
  } as unknown as NodeJS.ReadStream;
  const stdout = { isTTY: true, write: (text: string) => events.push(text) } as unknown as NodeJS.WriteStream;
  const repaint = vi.fn(() => events.push('repaint'));
  return { events, options: { stdin, stdout, alternateBuffer, kittyKeyboard, mouseTracking, repaint } };
}

describe('external editor terminal ownership', () => {
  it('waits for native reader suspension before handing off and resumes after failure', () => {
    const { events, options } = terminal();
    const nativeInput = {
      suspend: () => events.push('native:paused'),
      resume: () => events.push('native:running'),
    };
    expect(() => withEditorTerminal(() => {
      expect(events).toContain('native:paused');
      events.push('editor');
      throw Error('editor failed');
    }, { ...options, nativeInput })).toThrow('editor failed');
    expect(events.indexOf('native:paused')).toBeLessThan(events.indexOf('editor'));
    expect(events.indexOf('native:running')).toBeGreaterThan(events.indexOf('editor'));
    expect(events.indexOf('native:running')).toBeLessThan(events.indexOf('repaint'));
  });

  it('does not launch an editor if the native reader cannot suspend', () => {
    const { options } = terminal();
    const action = vi.fn();
    const nativeInput = {
      suspend: () => { throw Error('pause timeout'); },
      resume: vi.fn(),
    };
    expect(() => withEditorTerminal(action, { ...options, nativeInput })).toThrow('pause timeout');
    expect(action).not.toHaveBeenCalled();
    expect(nativeInput.resume).not.toHaveBeenCalled();
  });

  it('releases modes before launch and restores them before a complete repaint', () => {
    const { events, options } = terminal();
    expect(withEditorTerminal(() => {
      expect(events).toContain('raw:false');
      expect(events).toContain('\x1b[?7h\x1b[?1049l');
      events.push('editor');
      return 42;
    }, options)).toBe(42);
    expect(events.slice(events.indexOf('editor') + 1)).toEqual([
      '\x1b[?1049h\x1b[?7l', '\x1b[0m\x1b[?2004h', '\x1b[>1u',
      '\x1b[?1007l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h\x1b]22;default\x1b\\', 'raw:true', 'resume', 'repaint',
    ]);
  });

  it.each(['launch failure', 'editor failure'])('restores input and screen after %s', message => {
    const { events, options } = terminal();
    expect(() => withEditorTerminal(() => { throw Error(message); }, options)).toThrow(message);
    expect(events.slice(-3)).toEqual(['raw:true', 'resume', 'repaint']);
    expect(options.repaint).toHaveBeenCalledOnce();
  });

  it('keeps main-buffer operation and leaves unsupported modes disabled', () => {
    const { events, options } = terminal(false, false, false);
    withEditorTerminal(() => undefined, options);
    const output = events.join('');
    expect(output).not.toContain('1049');
    expect(output).not.toContain('\x1b[>1u');
    expect(output).not.toContain('\x1b[<u');
    expect(output).not.toContain('\x1b[?1000h');
    expect(options.repaint).toHaveBeenCalledOnce();
  });

  it('retains an initially paused cooked input stream', () => {
    const { events, options } = terminal();
    Object.assign(options.stdin, { isRaw: false, readableFlowing: false });
    withEditorTerminal(() => undefined, options);
    expect(events.slice(-2)).toEqual(['raw:false', 'repaint']);
    expect(events).not.toContain('resume');
  });
});