import { EventEmitter, once } from 'node:events';
import { PassThrough } from 'node:stream';
import { spawn, spawnSync } from 'node:child_process';
import { describe, expect, it, vi } from 'vitest';
import { WindowsConsoleInput } from '../src/services/windowsConsole.js';

vi.mock('node:child_process', () => ({ spawn: vi.fn(), spawnSync: vi.fn() }));
vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

describe('native input control failure', () => {
  it.each(['pause', 'resume'] as const)(
    'closes and requests restoration when %s was sent but acknowledgement times out', async failedAction => {
    const child = Object.assign(new EventEmitter(), {
      stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
      pid: 1234, exitCode: null, signalCode: null,
    });
    vi.mocked(spawn).mockReturnValue(child as any);
    const actions: string[] = [];
    vi.mocked(spawnSync).mockImplementation((_file, args) => {
      const action = args![args!.length - 1];
      actions.push(action);
      return { status: action === failedAction ? 1 : 0, stdout: 'ack timeout', stderr: '' } as any;
    });
    const pending = WindowsConsoleInput.start('python', 'helper.py');
    child.stdout.write('{"type":"ready"}\n');
    const input = await pending;
    if (failedAction === 'resume') input.suspend();
    const failure = once(input.stream, 'error');
    try {
      expect(() => failedAction === 'pause' ? input.suspend() : input.resume()).toThrow(failedAction);
      expect(input.stream.destroyed).toBe(true);
      expect((await failure)[0].message).toContain(failedAction);
      expect(actions).toEqual(failedAction === 'pause' ? ['pause', 'stop'] : ['pause', 'resume', 'stop']);
      expect(() => input.resume()).toThrow();
    } finally {
      input.stop();
    }
  });
});