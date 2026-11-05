import { afterEach, describe, expect, it, vi } from 'vitest';

const execute = vi.hoisted(() => vi.fn());
vi.mock('node:child_process', () => ({
  execFile: execute,
}));
import { openExternalUrl } from '../src/utils/openExternalUrl.js';

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe('openExternalUrl', () => {
  it.each([
    ['darwin', 'open', ['https://example.com/?q=$(touch%20file)&a=1']],
    ['linux', 'xdg-open', ['https://example.com/?q=$(touch%20file)&a=1']],
    ['win32', 'rundll32.exe', ['url.dll,FileProtocolHandler', 'https://example.com/?q=$(touch%20file)&a=1']],
  ])('passes the URL as an argument on %s without a shell', async (platform, command, args) => {
    vi.stubGlobal('process', { ...process, platform });
    execute.mockImplementation((_command, _args, _options, callback) => {
      callback(null, '', '');
    });
    const signal = new AbortController().signal;
    await openExternalUrl('https://example.com/?q=$(touch%20file)&a=1', signal);
    expect(execute).toHaveBeenCalledWith(command, args,
      { timeout: 10000, windowsHide: true, signal }, expect.any(Function));
  });

  it('rejects non-web URLs before spawning a process', async () => {
    await expect(openExternalUrl('file:///tmp/example')).rejects.toThrow('Only HTTPS');
    expect(execute).not.toHaveBeenCalled();
  });

  it('reports OS handler failure to its caller', async () => {
    execute.mockImplementation((_command, _args, _options, callback) => {
      callback(new Error('ENOENT'));
    });
    await expect(openExternalUrl('https://example.com')).rejects.toThrow('ENOENT');
  });
});