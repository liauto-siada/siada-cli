import React from 'react';
import { PassThrough } from 'node:stream';
import { render, Text } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Key } from '../../contexts/KeypressContext.js';
import type { ClipboardContent } from '../../utils/clipboard.js';

const fake = vi.hoisted(() => ({
  read: vi.fn(),
  copy: vi.fn(),
  discard: vi.fn(),
  rightClickAllowed: vi.fn(),
}));
vi.mock('../../utils/clipboard.js', () => ({
  readClipboardContent: fake.read,
  copyClipboardText: fake.copy,
  discardClipboardContent: fake.discard,
  canPasteOnRightClick: fake.rightClickAllowed,
}));
import { useClipboard } from '../useClipboard.js';
import { setUiLanguage } from '../../i18n/index.js';

let api: ReturnType<typeof useClipboard>;
let app: ReturnType<typeof render> | undefined;
let output = '';
const pasted = vi.fn();
function Harness({ active = true, owner = 'first' }: { active?: boolean; owner?: string }) {
  api = useClipboard({ active, owner, onPaste: pasted });
  return <Text>{api.message || 'ready'}</Text>;
}
function mount() {
  const stdout = Object.assign(new PassThrough(), { columns: 80, rows: 24 });
  stdout.on('data', data => { output += String(data); });
  app = render(<Harness />, {
    stdout, stdin: new PassThrough(), patchConsole: false,
    exitOnCtrlC: false, maxFps: 0,
  });
}
const key = (name: string, ctrl = false) => ({ name, ctrl } as Key);
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { resolve, promise };
}

beforeEach(() => {
  setUiLanguage('en');
  vi.resetAllMocks();
  output = '';
  fake.copy.mockResolvedValue({ status: 'copied', message: '已复制到剪贴板。' });
  fake.rightClickAllowed.mockReturnValue(true);
});
afterEach(() => {
  setUiLanguage('en');
  app?.unmount();
  app?.cleanup();
  app = undefined;
});

describe('clipboard input ownership and feedback', () => {
  it.each(['en', 'zh-CN'] as const)('renders localized reading progress and generic failures in %s', async language => {
    setUiLanguage(language);
    const read = deferred<ClipboardContent>();
    fake.read.mockReturnValueOnce(read.promise);
    mount();
    api.paste();
    await vi.waitFor(() => expect(output).toContain(language === 'en'
      ? 'Reading clipboard…' : '正在读取剪贴板…'));
    read.resolve({ kind: 'text', text: '用户内容' });
    await vi.waitFor(() => expect(pasted).toHaveBeenCalledWith({ kind: 'text', text: '用户内容' }));
    fake.read.mockRejectedValueOnce(null);
    api.paste();
    await vi.waitFor(() => expect(output).toContain(language === 'en'
      ? 'Clipboard operation failed.' : '剪贴板操作失败。'));
  });
  it('renders clipboard read failures without inserting content', async () => {
    fake.read.mockRejectedValue(new Error('SSH 会话请使用终端粘贴。'));
    mount();
    api.paste();
    await vi.waitFor(() => expect(output).toContain('SSH'));
    expect(pasted).not.toHaveBeenCalled();
  });
  it('inserts a successful clipboard read into the current input', async () => {
    fake.read.mockResolvedValue({ kind: 'text', text: '中文\ntext' });
    mount();
    api.paste(false);
    await vi.waitFor(() => expect(pasted).toHaveBeenCalledWith({ kind: 'text', text: '中文\ntext' }));
    expect(fake.read).toHaveBeenCalledWith(false);
  });
  it('reads only text on right click and ignores repeated presses and pointer motion', async () => {
    const read = deferred<ClipboardContent>();
    fake.read.mockReturnValue(read.promise);
    mount();
    api.onKey(key('mouseright'));
    api.pasteOnRightClick();
    api.onKey(key('mousemove'));
    api.onKey(key('mouserelease'));
    api.onKey(key('mouseright'));
    api.pasteOnRightClick();
    read.resolve({ kind: 'text', text: 'once' });
    await vi.waitFor(() => expect(pasted).toHaveBeenCalledWith({ kind: 'text', text: 'once' }));
    expect(pasted).toHaveBeenCalledOnce();
    expect(fake.read).toHaveBeenCalledOnce();
    expect(fake.read).toHaveBeenCalledWith(false);
  });
  it('does not read the clipboard on a terminal-owned right click', () => {
    fake.rightClickAllowed.mockReturnValue(false);
    mount();
    api.pasteOnRightClick();
    expect(fake.read).not.toHaveBeenCalled();
  });
  it('suppresses repeated shortcuts while a clipboard read is pending', async () => {
    const read = deferred<ClipboardContent>();
    fake.read.mockReturnValue(read.promise);
    mount();
    api.onKey(key('v', true));
    api.paste();
    api.onKey(key('mousemiddle'));
    api.paste();
    api.onKey(key('v', true));
    api.paste();
    api.copy('other');
    read.resolve({ kind: 'text', text: 'once' });
    await vi.waitFor(() => expect(pasted).toHaveBeenCalledTimes(1));
    expect(fake.read).toHaveBeenCalledTimes(1);
    expect(fake.copy).not.toHaveBeenCalled();
  });
  it.each(['input', 'terminal-paste', 'owner', 'inactive', 'unmount'])(
    'discards late content after %s', async action => {
      const read = deferred<ClipboardContent>();
      fake.read.mockReturnValue(read.promise);
      mount();
      api.paste();
      if (action === 'input') api.onKey(key('a'));
      if (action === 'terminal-paste') api.onKey(key('paste'));
      if (action === 'owner') app!.rerender(<Harness owner="second" />);
      if (action === 'inactive') app!.rerender(<Harness active={false} />);
      if (action === 'unmount') app!.unmount();
      const content: ClipboardContent = { kind: 'image', image: { filePath: '/synthetic/image.png', mediaType: 'image/png' } };
      read.resolve(content);
      await vi.waitFor(() => expect(fake.discard).toHaveBeenCalledWith(content));
      expect(pasted).not.toHaveBeenCalled();
    },
  );
  it('renders confirmed copy feedback', async () => {
    mount();
    api.copy('text');
    await vi.waitFor(() => expect(output).toContain('已复制到剪贴板'));
    expect(fake.copy).toHaveBeenCalledWith('text');
  });
  it('shows terminal requests separately from confirmed writes', async () => {
    fake.copy.mockResolvedValue({ status: 'requested', message: '已请求终端复制。' });
    mount();
    api.copy('text');
    await vi.waitFor(() => expect(output).toContain('已请求终端复制'));
  });
});