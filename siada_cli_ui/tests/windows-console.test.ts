import { PassThrough } from 'node:stream';
import { once } from 'node:events';
import { describe, expect, it, vi } from 'vitest';
import { ConsoleInputStream } from '../src/services/windowsConsole.js';
import { createKeypressProcessor, emitKeys, type Key } from '../src/contexts/KeypressContext.js';

vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

describe('native console input transport', () => {
  it('preserves modified delete and tab events in the existing parser', async () => {
    const source = new PassThrough();
    const stream = new ConsoleInputStream(source);
    const keys: Key[] = [];
    const parser = emitKeys(createKeypressProcessor(key => keys.push(key)));
    parser.next();
    stream.on('data', text => { for (const character of String(text)) parser.next(character); });
    source.end(JSON.stringify({ type: 'input', data: '\x1b[127;5u\x1b[127;3u\x1b[9;5u' }) + '\n');
    await once(stream, 'end');
    expect(keys).toMatchObject([
      { name: 'backspace', ctrl: true, insertable: false },
      { name: 'backspace', alt: true, insertable: false },
      { name: 'tab', ctrl: true, insertable: false },
    ]);
  });

  it('delivers real parser click/release events from fragmented native messages', async () => {
    const source = new PassThrough();
    const stream = new ConsoleInputStream(source);
    const keys: Key[] = [];
    const parser = emitKeys(createKeypressProcessor(key => keys.push(key)));
    parser.next();
    stream.on('data', text => { for (const character of String(text)) parser.next(character); });
    source.write('{"type":"input","data":"\\u001b[<0;3;4');
    source.write('M"}\n{"type":"input","data":"\\u001b[<0;3;4m"}\n');
    source.end('{"type":"input","data":"中"}\n');
    await once(stream, 'end');
    expect(keys.slice(0, 2).map(key => key.name)).toEqual(['mouseclick', 'mouserelease']);
    expect(keys[2]).toMatchObject({ sequence: '中', insertable: true });
    expect(keys[0].sequence).toBe('\x1b[<0;3;4M');
  });

  it('keeps handshake and resize messages out of keyboard text', async () => {
    const source = new PassThrough();
    const stream = new ConsoleInputStream(source);
    const ready = vi.fn();
    const resize = vi.fn();
    const data = vi.fn();
    stream.on('ready', ready).on('resize', resize).on('data', data);
    source.end('{"type":"ready"}\n{"type":"resize","columns":90,"rows":25}\n');
    await once(stream, 'end');
    expect(ready).toHaveBeenCalledOnce();
    expect(resize).toHaveBeenCalledWith({ columns: 90, rows: 25 });
    expect(data).not.toHaveBeenCalled();
  });

  it('supports the Ink raw-mode API without changing the real console', () => {
    const stream = new ConsoleInputStream(new PassThrough());
    expect(stream.isTTY).toBe(true);
    expect(stream.setRawMode(true)).toBe(stream);
    expect(stream.isRaw).toBe(true);
    expect(() => { stream.ref(); stream.unref(); }).not.toThrow();
    stream.destroy();
  });

  it('fails visibly on broken helper messages without inserting them as text', async () => {
    const source = new PassThrough();
    const stream = new ConsoleInputStream(source);
    const data = vi.fn();
    stream.on('data', data);
    const error = once(stream, 'error');
    source.write('{"type":"error","error":"input reader failed"}\n');
    expect((await error)[0].message).toContain('input reader failed');
    expect(data).not.toHaveBeenCalled();
  });
});