import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync, rmSync } from 'node:fs';
import { dirname } from 'node:path';
import { setUiLanguage } from '../../i18n/index.js';
import { PNG } from 'pngjs';

const fake = vi.hoisted(() => ({
  replies: new Map<string, Buffer | Error>(),
  nativeRead: vi.fn(),
  nativeWrite: vi.fn(),
  nativeImage: vi.fn(),
  calls: [] as { cmd: string; args: string[]; input?: string; timeout: number; signal?: AbortSignal }[],
  release: 'generic-linux',
  pipeError: false,
  killed: vi.fn(),
}));
vi.mock('../nativeClipboard.js', () => ({
  nativeClipboard: { readText: fake.nativeRead, writeText: fake.nativeWrite, readImage: fake.nativeImage },
}));
vi.mock('child_process', () => ({
  execFile: (cmd: string, args: string[], options: { timeout: number; signal?: AbortSignal }, callback: Function) => {
    const call = { cmd, args, input: undefined as string | undefined, timeout: options.timeout, signal: options.signal };
    fake.calls.push(call);
    const reply = fake.replies.get(`${cmd} ${args[0]}`) ?? fake.replies.get(cmd) ?? new Error(`spawn ${cmd} ENOENT`);
    queueMicrotask(() => queueMicrotask(() => callback(reply instanceof Error ? reply : null,
      reply instanceof Error ? Buffer.alloc(0) : reply, Buffer.alloc(0))));
    return {
      kill: fake.killed,
      stdin: {
        on: (event: string, handler: (error: Error) => void) => {
          if (fake.pipeError) queueMicrotask(() => handler(new Error('EPIPE')));
        },
        end: (input?: string) => { call.input = input; },
      },
    };
  },
}));
vi.mock('os', async importOriginal => ({
  ...await importOriginal<typeof import('os')>(),
  release: () => fake.release,
}));
vi.mock('../logger.js', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

import {
  canPasteOnRightClick, copyClipboardText, copySelectionToClipboard, copyTextToClipboard, discardClipboardContent, getImageFromClipboard,
  getTextFromClipboard, isWslSession, readClipboardContent,
  readClipboardText, resetTerminalCopyCache, terminalCopySequence,
} from '../clipboard.js';

const platform = Object.getOwnPropertyDescriptor(process, 'platform')!;
const tty = Object.getOwnPropertyDescriptor(process.stdout, 'isTTY');
const paths: string[] = [];

function setPlatform(value: string) {
  Object.defineProperty(process, 'platform', { configurable: true, value });
}

beforeEach(() => {
  setUiLanguage('zh-CN');
  fake.calls.length = 0;
  fake.nativeRead.mockReset().mockRejectedValue(new Error('native unavailable'));
  fake.nativeWrite.mockReset().mockRejectedValue(new Error('native unavailable'));
  fake.nativeImage.mockReset().mockResolvedValue(null);
  fake.replies.clear();
  fake.release = 'generic-linux';
  fake.pipeError = false;
  fake.killed.mockClear();
  resetTerminalCopyCache();
  for (const key of ['SSH_TTY', 'SSH_CONNECTION', 'SSH_CLIENT', 'TMUX', 'TMUX_PANE', 'WSL_DISTRO_NAME', 'WSL_INTEROP', 'TERM_PROGRAM']) {
    vi.stubEnv(key, '');
  }
  setPlatform('linux');
  Object.defineProperty(process.stdout, 'isTTY', { configurable: true, value: true });
});
afterEach(() => {
  setUiLanguage('en');
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  Object.defineProperty(process, 'platform', platform);
  if (tty) Object.defineProperty(process.stdout, 'isTTY', tty);
  else delete process.stdout.isTTY;
  for (const path of paths.splice(0)) rmSync(dirname(path), { recursive: true, force: true });
});

describe('right-click paste environment', () => {
  it.each(['darwin', 'linux', 'win32'])('allows local text paste on %s', platform => {
    setPlatform(platform);
    expect(canPasteOnRightClick()).toBe(true);
  });
  it.each(['SSH_TTY', 'SSH_CONNECTION', 'SSH_CLIENT'])('leaves paste to the terminal when %s is set', name => {
    vi.stubEnv(name, 'synthetic');
    expect(canPasteOnRightClick()).toBe(false);
    expect(fake.nativeRead).not.toHaveBeenCalled();
  });
  it.each(['vscode', 'VSCode'])('leaves paste to a recognized %s terminal', program => {
    vi.stubEnv('TERM_PROGRAM', program);
    expect(canPasteOnRightClick()).toBe(false);
  });
  it('does not enable host reads on unsupported platforms', () => {
    setPlatform('android');
    expect(canPasteOnRightClick()).toBe(false);
  });
});

describe('clipboard language', () => {
  it.each(['en', 'zh-CN'] as const)('localizes native copy and empty input in %s', async language => {
    setUiLanguage(language);
    fake.nativeWrite.mockResolvedValue(undefined);
    expect((await copyClipboardText('用户文字 stays unchanged')).message).toBe(
      language === 'en' ? 'Copied to clipboard.' : '已复制到剪贴板。',
    );
    expect(fake.nativeWrite).toHaveBeenCalledWith('用户文字 stays unchanged', undefined);
    expect((await copyClipboardText('')).message).toBe(
      language === 'en' ? 'No text available to copy.' : '没有可复制的文字。',
    );
  });

  it.each(['en', 'zh-CN'] as const)('localizes terminal copy outcomes in %s', async language => {
    setUiLanguage(language);
    vi.stubEnv('SSH_CONNECTION', 'synthetic');
    const write = vi.spyOn(process.stdout, 'write').mockImplementation((...args: any[]) => {
      args.at(-1)?.();
      return true;
    });
    expect((await copyClipboardText('text')).message).toBe(language === 'en'
      ? 'Terminal copy requested; clipboard delivery depends on terminal settings.'
      : '已请求终端复制；是否写入剪贴板取决于终端设置。');
    write.mockImplementation(() => { throw new Error('synthetic output error'); });
    expect((await copyClipboardText('text')).message).toBe(language === 'en'
      ? 'Terminal copy failed. Select the text and use the terminal copy command.'
      : '终端复制失败，请使用终端选择文字后复制。');
    vi.stubEnv('SSH_CONNECTION', '');
    expect((await copyClipboardText('text')).message).toBe(language === 'en'
      ? 'Copy failed. Select the text and use the terminal copy command.'
      : '复制失败，请使用终端选择文字后复制。');
  });

  it.each(['en', 'zh-CN'] as const)('localizes clipboard errors and terminal guidance in %s', async language => {
    setUiLanguage(language);
    await expect(readClipboardText()).rejects.toThrow(language === 'en'
      ? 'Could not read the Linux desktop clipboard.' : '无法读取Linux 桌面剪贴板。');
    vi.stubEnv('SSH_CONNECTION', 'synthetic');
    await expect(readClipboardContent(false)).rejects.toThrow(language === 'en'
      ? "The local clipboard is unavailable over SSH. Use the terminal's Paste command"
      : 'SSH 会话无法读取本地剪贴板。请使用终端菜单“粘贴”');
    vi.stubEnv('SSH_CONNECTION', '');
    fake.nativeRead.mockResolvedValue('');
    await expect(readClipboardContent(false)).rejects.toThrow(language === 'en'
      ? 'No text or image available to paste from the clipboard.' : '剪贴板中没有可粘贴的文字或图片。');
    expect(() => terminalCopySequence('x'.repeat(100001), false)).toThrow(language === 'en'
      ? 'Terminal copy exceeds 100 KB.' : '终端复制内容超过 100 KB。');
  });

  it('uses the language selected while an asynchronous copy is pending', async () => {
    setUiLanguage('en');
    let complete!: () => void;
    fake.nativeWrite.mockImplementation(() => new Promise<void>(resolve => { complete = resolve; }));
    const result = copyClipboardText('text');
    setUiLanguage('zh-CN');
    complete();
    expect((await result).message).toBe('已复制到剪贴板。');
    setUiLanguage('en');
    fake.nativeWrite.mockResolvedValue(undefined);
    expect((await copyClipboardText('text')).message).toBe('Copied to clipboard.');
  });
});

describe('clipboard reads', () => {
  it('reads native PNG images without starting external clipboard tools', async () => {
    const png = PNG.sync.write({ width: 2, height: 3, data: Buffer.alloc(24, 255) });
    fake.nativeImage.mockResolvedValue({ data: png, width: 2, height: 3 });
    const content = await readClipboardContent(true);
    expect(content.kind).toBe('image');
    if (content.kind !== 'image') throw new Error('expected image');
    paths.push(content.image.filePath);
    expect(content.image).toMatchObject({ width: 2, height: 3, mediaType: 'image/png' });
    expect(PNG.sync.read(readFileSync(content.image.filePath))).toMatchObject({ width: 2, height: 3 });
    expect(fake.calls).toHaveLength(0);
    expect(fake.nativeRead).not.toHaveBeenCalled();
  });

  it('retains text paste when the image backend is unavailable', async () => {
    fake.nativeImage.mockRejectedValue(new Error('image unavailable'));
    fake.nativeRead.mockResolvedValue('text still works');
    expect(await readClipboardContent(true)).toEqual({ kind: 'text', text: 'text still works' });
  });

  it('reports image read failure separately from an empty clipboard', async () => {
    fake.nativeImage.mockRejectedValue(new Error('image unavailable'));
    fake.nativeRead.mockResolvedValue('');
    await expect(readClipboardContent(true)).rejects.toThrow('无法读取剪贴板图片');
    expect(await getImageFromClipboard()).toBeNull();
  });
  it('uses the latest language after image and text fallback have both completed', async () => {
    fake.nativeImage.mockRejectedValue(new Error('image unavailable'));
    fake.nativeRead.mockImplementation(async () => {
      setUiLanguage('en');
      return '';
    });
    await expect(readClipboardContent(true)).rejects.toThrow('Could not read the clipboard image');
  });
  it('reads Linux text natively without wl-paste or xclip', async () => {
    fake.nativeRead.mockResolvedValue(' 中文 👋\r\nsecond line ');
    expect(await readClipboardText()).toBe(' 中文 👋\nsecond line ');
    expect(fake.calls).toHaveLength(0);
  });

  it('treats an empty native clipboard as empty without trying external helpers', async () => {
    fake.nativeRead.mockResolvedValue('');
    expect(await readClipboardText()).toBe('');
    expect(fake.calls).toHaveLength(0);
  });

  it('does not read a Linux clipboard in WSL or SSH_CLIENT-only sessions', async () => {
    vi.stubEnv('WSL_INTEROP', 'synthetic');
    fake.replies.set('powershell.exe', Buffer.from('Windows text'));
    expect(await readClipboardText()).toBe('Windows text');
    expect(fake.nativeRead).not.toHaveBeenCalled();
    vi.stubEnv('WSL_INTEROP', '');
    vi.stubEnv('SSH_CLIENT', 'synthetic');
    await expect(readClipboardText()).rejects.toThrow('SSH');
    expect(fake.nativeRead).not.toHaveBeenCalled();
  });
  it.each(['wl-paste', 'xclip'])('reads Linux text with %s and preserves whitespace', async cmd => {
    fake.replies.set(cmd, Buffer.from(' 中文\r\n second\rthird\n'));
    expect(await readClipboardText()).toBe(' 中文\n second\nthird\n');
    expect(fake.calls.at(-1)?.cmd).toBe(cmd);
  });
  it('reports missing Linux tools and retains nullable compatibility', async () => {
    await expect(readClipboardText()).rejects.toThrow('Ctrl+Shift+V');
    expect(await getTextFromClipboard()).toBeNull();
  });
  it.each(['win32', 'wsl'])('reads Windows clipboard for %s without Linux fallback', async mode => {
    setPlatform(mode === 'win32' ? 'win32' : 'linux');
    if (mode === 'wsl') vi.stubEnv('WSL_DISTRO_NAME', 'Test');
    fake.replies.set(mode === 'wsl' ? 'powershell.exe' : 'powershell', Buffer.from('中文\r\ntext'));
    expect(await readClipboardText()).toBe('中文\ntext');
    expect(fake.calls).toHaveLength(1);
    expect(fake.calls[0].args.join(' ')).toContain('Get-Clipboard -Raw');
    expect(fake.calls[0].timeout).toBe(3000);
  });
  it('recognizes WSL kernel without inherited WSL variables', () => {
    fake.release = '5.15.0-microsoft-standard-WSL2';
    expect(isWslSession()).toBe(true);
  });
  it('does not read another clipboard when Windows clipboard fails in WSL', async () => {
    vi.stubEnv('WSL_INTEROP', 'test');
    fake.replies.set('wl-paste', Buffer.from('wrong clipboard'));
    await expect(readClipboardText()).rejects.toThrow('Windows');
    expect(fake.calls.map(call => call.cmd)).toEqual(['powershell.exe']);
  });
  it('rejects SSH reads without launching clipboard commands', async () => {
    vi.stubEnv('SSH_CONNECTION', 'test');
    await expect(readClipboardContent(true)).rejects.toThrow('SSH');
    expect(await getImageFromClipboard()).toBeNull();
    expect(fake.calls).toHaveLength(0);
  });
  it('reports an empty clipboard separately from backend failure', async () => {
    fake.replies.set('wl-paste', Buffer.alloc(0));
    await expect(readClipboardContent(false)).rejects.toThrow('没有可粘贴');
  });
  it('falls back from unavailable image data to text', async () => {
    fake.replies.set('wl-paste', Buffer.from('text'));
    expect(await readClipboardContent(true)).toEqual({ kind: 'text', text: 'text' });
  });
  it('reads a WSL image through base64 into a unique local temporary file', async () => {
    vi.stubEnv('WSL_DISTRO_NAME', 'Test');
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10, 0]);
    fake.replies.set('powershell.exe', Buffer.from(png.toString('base64')));
    const first = await getImageFromClipboard();
    const second = await getImageFromClipboard();
    expect(first?.mediaType).toBe('image/png');
    expect(second?.filePath).not.toBe(first?.filePath);
    paths.push(first!.filePath, second!.filePath);
    discardClipboardContent({ kind: 'image', image: first! });
  });
});

describe('clipboard copies', () => {
  it('falls back to OSC52 on an unidentified terminal when local clipboard writes fail', async () => {
    vi.stubEnv('TERM', 'xterm-256color');
    vi.stubEnv('TERM_PROGRAM', undefined);
    vi.stubEnv('STY', '');
    const write = vi.fn();
    expect(await copySelectionToClipboard('selected 中文', { isTTY: true, write } as any)).toBe('osc52');
    expect(fake.nativeWrite).toHaveBeenCalledWith('selected 中文', undefined);
    expect(fake.calls.map(call => call.cmd)).toEqual(['wl-copy', 'xclip']);
    expect(write).toHaveBeenCalledOnce();
    expect(write).toHaveBeenCalledWith(
      `\x1b]52;c;${Buffer.from('selected 中文').toString('base64')}\x07`,
    );
  });
  it('copies Linux text natively without starting external clipboard writers', async () => {
    fake.nativeWrite.mockResolvedValue(undefined);
    expect((await copyClipboardText('native 中文')).status).toBe('copied');
    expect(fake.nativeWrite).toHaveBeenCalledWith('native 中文', undefined);
    expect(fake.calls).toHaveLength(0);
  });

  it('does not fall back to external writers after native cancellation', async () => {
    const abort = new AbortController();
    fake.nativeWrite.mockImplementation(async () => { abort.abort(); throw new Error('aborted'); });
    expect(await copyTextToClipboard('cancelled', abort.signal)).toBe(false);
    expect(fake.calls).toHaveLength(0);
  });
  it.each(['darwin', 'linux', 'win32', 'wsl'])('writes text to %s via stdin', async mode => {
    setPlatform(mode === 'wsl' ? 'linux' : mode);
    if (mode === 'wsl') vi.stubEnv('WSL_DISTRO_NAME', 'Test');
    const cmd = { darwin: '/usr/bin/pbcopy', linux: 'wl-copy', win32: 'powershell', wsl: 'powershell.exe' }[mode]!;
    fake.replies.set(cmd, Buffer.alloc(0));
    const text = '中文\n`echo secret` $(do-not-run) \' "';
    expect((await copyClipboardText(text)).status).toBe('copied');
    expect(fake.calls[0].input).toBe(text);
    expect(fake.calls[0].args.join(' ')).not.toContain(text);
  });
  it('falls back to xclip when wl-copy is unavailable', async () => {
    fake.replies.set('xclip', Buffer.alloc(0));
    expect((await copyClipboardText('text')).status).toBe('copied');
    expect(fake.calls.map(call => call.cmd)).toEqual(['wl-copy', 'xclip']);
  });
  it('uses OSC 52 for SSH without writing the remote native clipboard', async () => {
    vi.stubEnv('SSH_TTY', 'test');
    const write = vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.();
      return true;
    });
    expect((await copyClipboardText('中文')).status).toBe('requested');
    expect(write).toHaveBeenCalledWith(terminalCopySequence('中文', false), expect.any(Function));
    expect(fake.calls).toHaveLength(0);
  });
  it('falls back to OSC 52 after native copy failure', async () => {
    vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.();
      return true;
    });
    expect((await copyClipboardText('text')).status).toBe('requested');
  });
  it('uses tmux forwarding and closes stdin', async () => {
    vi.stubEnv('TMUX', 'test');
    vi.stubEnv('TMUX_PANE', '%1');
    fake.replies.set('tmux show-options', Buffer.from('on\n'));
    fake.replies.set('tmux display-message', Buffer.from('$1\n'));
    fake.replies.set('tmux list-clients', Buffer.from('100 /dev/pts/1\n200 /dev/pts/2\n'));
    fake.replies.set('tmux load-buffer', Buffer.alloc(0));
    expect((await copyClipboardText('text')).status).toBe('requested');
    expect(fake.calls.at(-1)?.input).toBe('text');
    expect(fake.calls.at(-1)?.args).toEqual(['load-buffer', '-w', '-t', '/dev/pts/2', '-']);
    expect(fake.calls.find(call => call.args[0] === 'list-clients')?.args)
      .toContain('$1');
  });
  it('wraps OSC 52 for tmux when forwarding fails', async () => {
    vi.stubEnv('TMUX', 'test');
    vi.stubEnv('TMUX_PANE', '%1');
    const write = vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.();
      return true;
    });
    expect((await copyClipboardText('text')).status).toBe('requested');
    expect(write).toHaveBeenCalledWith(terminalCopySequence('text', true), expect.any(Function));
  });
  it('does not emit terminal escapes to redirected output', async () => {
    Object.defineProperty(process.stdout, 'isTTY', { configurable: true, value: false });
    const write = vi.spyOn(process.stdout, 'write');
    expect((await copyClipboardText('text')).status).toBe('failed');
    expect(write).not.toHaveBeenCalled();
  });
  it('does not report a confirmed copy if stdin delivery fails', async () => {
    fake.pipeError = true;
    setPlatform('darwin');
    fake.replies.set('/usr/bin/pbcopy', Buffer.alloc(0));
    Object.defineProperty(process.stdout, 'isTTY', { configurable: true, value: false });
    expect((await copyClipboardText('text')).status).toBe('failed');
    expect(fake.killed).toHaveBeenCalled();
  });
  it('reports a terminal write error instead of claiming a copy request succeeded', async () => {
    vi.stubEnv('SSH_TTY', 'test');
    vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.(new Error('write failed'));
      return false;
    });
    expect((await copyClipboardText('text')).status).toBe('failed');
  });
  it('rejects empty copies without touching any backend', async () => {
    expect((await copyClipboardText('')).status).toBe('failed');
    expect(fake.calls).toHaveLength(0);
  });
  it('preserves cancellation and payload bounds for selection callers', async () => {
    expect(await copyTextToClipboard('text', AbortSignal.abort())).toBe(false);
    expect(await copyTextToClipboard('x'.repeat(100001))).toBe(false);
    expect(fake.calls).toHaveLength(0);
  });
  it('passes the selection abort signal to native helpers without terminal fallback', async () => {
    const abort = new AbortController();
    fake.replies.set('wl-copy', Buffer.alloc(0));
    expect(await copyTextToClipboard('text', abort.signal)).toBe(true);
    expect(fake.calls[0].signal).toBe(abort.signal);
    fake.replies.clear();
    const write = vi.spyOn(process.stdout, 'write');
    expect(await copyTextToClipboard('text', abort.signal)).toBe(false);
    expect(write).not.toHaveBeenCalled();
  });
  it('bounds terminal payloads by UTF-8 bytes and encodes control characters', () => {
    expect(() => terminalCopySequence('中'.repeat(33334), false)).toThrow('100 KB');
    const text = '中文\x1b]52;c;injected\x07';
    const sequence = terminalCopySequence(text, false);
    expect(sequence).toBe(`\x1b]52;c;${Buffer.from(text).toString('base64')}\x07`);
  });
});

describe('terminal copy cache for SSH paste', () => {
  it('pastes the latest OSC 52 copy over SSH without touching the remote clipboard', async () => {
    vi.stubEnv('SSH_TTY', 'test');
    const write = vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.();
      return true;
    });
    expect((await copyClipboardText('第一次复制')).status).toBe('requested');
    expect((await copyClipboardText('SSH 复制的中文')).status).toBe('requested');
    expect(await readClipboardContent(true)).toEqual({ kind: 'text', text: 'SSH 复制的中文' });
    expect(await readClipboardContent(false)).toEqual({ kind: 'text', text: 'SSH 复制的中文' });
    expect(fake.nativeRead).not.toHaveBeenCalled();
    expect(fake.calls).toHaveLength(0);
  });

  it('caches selection OSC 52 copies for SSH paste', async () => {
    vi.stubEnv('SSH_CONNECTION', 'test');
    const write = vi.fn();
    expect(await copySelectionToClipboard('选择复制的中文', { isTTY: true, write } as any)).toBe('osc52');
    expect(await readClipboardContent(true)).toEqual({ kind: 'text', text: '选择复制的中文' });
    expect(fake.nativeRead).not.toHaveBeenCalled();
    expect(fake.calls).toHaveLength(0);
  });

  it('keeps the SSH read error when nothing was copied through the terminal', async () => {
    vi.stubEnv('SSH_CONNECTION', 'test');
    await expect(readClipboardContent(false)).rejects.toThrow('SSH');
    expect(fake.nativeRead).not.toHaveBeenCalled();
  });

  it('does not cache failed terminal copies', async () => {
    vi.stubEnv('SSH_TTY', 'test');
    vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.(new Error('write failed'));
      return false;
    });
    expect((await copyClipboardText('text')).status).toBe('failed');
    await expect(readClipboardContent(false)).rejects.toThrow('SSH');
  });

  it('prefers the real clipboard over the terminal copy outside SSH', async () => {
    vi.stubEnv('TMUX', 'test');
    const write = vi.spyOn(process.stdout, 'write').mockImplementation((chunk: any, callback: any) => {
      callback?.();
      return true;
    });
    expect((await copyClipboardText('terminal copy')).status).toBe('requested');
    vi.stubEnv('TMUX', '');
    fake.nativeRead.mockResolvedValue('native text');
    expect(await readClipboardContent(true)).toEqual({ kind: 'text', text: 'native text' });
    expect(fake.nativeRead).toHaveBeenCalledOnce();
  });
});
