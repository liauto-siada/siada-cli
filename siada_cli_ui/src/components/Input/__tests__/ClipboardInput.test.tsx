import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { Key } from '../../../contexts/KeypressContext.js';

const fake = vi.hoisted(() => ({
  key: null as ((key: Key) => void) | null,
  read: vi.fn(),
  copy: vi.fn(),
}));
vi.mock('../../../hooks/useKeypress.js', () => ({
  useKeypress: (handler: (key: Key) => void) => { fake.key = handler; },
}));
vi.mock('../../../utils/clipboard.js', () => ({
  readClipboardContent: fake.read,
  copyClipboardText: fake.copy,
  discardClipboardContent: vi.fn(),
}));
vi.mock('../../../hooks/useCommandCompletion.js', () => ({
  useCommandCompletion: () => ({ suggestions: [], showSuggestions: false, reset: vi.fn() }),
}));
vi.mock('../../../hooks/useShellHistory.js', () => ({
  useShellHistory: () => ({ resetIndex: vi.fn() }),
}));
vi.mock('../../../components/EditorDialog/index.js', () => ({
  EditorDialog: () => null,
  useEditorDialog: () => ({ isOpen: false }),
}));
vi.mock('../../../components/StatusBarDialog/index.js', () => ({
  StatusBarDialog: () => null,
  StatusDialog: () => null,
  useStatusBarDialog: () => ({ isOpen: false, visibleItems: [] }),
  useStatusDialog: () => ({ isOpen: false }),
}));
vi.mock('../../../services/slashCommandService.js', () => ({
  slashCommandService: { getCommands: async () => [] },
}));
vi.mock('../../../utils/logger.js', () => ({
  logger: { info: vi.fn(), debug: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
import { ShortcutTextInput } from '../ShortcutTextInput.js';
import { InputPromptWithWrapUseKPC } from '../InputPromptWithWrapUseKPC.js';
import { AppProvider } from '../../../store/context.js';

let app: ReturnType<typeof render> | undefined;
let output = '';
const submit = vi.fn();
function mount(main = false, onTipChange?: (tip: string | null) => void) {
  const stdout = Object.assign(new PassThrough(), { columns: 80, rows: 24 });
  stdout.on('data', data => { output += String(data); });
  const content = main
    ? <AppProvider><InputPromptWithWrapUseKPC onSubmit={submit} width={80} onTipChange={onTipChange} /></AppProvider>
    : <ShortcutTextInput onSubmit={submit} />;
  app = render(content, {
    stdout, stdin: new PassThrough(), patchConsole: false,
    exitOnCtrlC: false, maxFps: 0,
  });
}
const send = (name: string, sequence = '', ctrl = false) => {
  fake.key!({ name, sequence, ctrl, insertable: !!sequence } as Key);
};
beforeEach(() => {
  vi.resetAllMocks();
  output = '';
  fake.copy.mockResolvedValue({ status: 'copied', message: '已复制到剪贴板。' });
});
describe('clipboard shortcuts in the main prompt', () => {
  it('accepts terminal text paste over SSH without a recognized terminal', async () => {
    vi.stubEnv('SSH_CONNECTION', 'synthetic');
    vi.stubEnv('TERM', 'xterm-256color');
    vi.stubEnv('TERM_PROGRAM', undefined);
    try {
      mount(true);
      const text = 'terminal 中文\nsecond line';
      send('paste', text);
      await vi.waitFor(() => expect(output).toContain('second line'));
      expect(fake.read).not.toHaveBeenCalled();
      expect(submit).not.toHaveBeenCalled();
      send('return');
      await vi.waitFor(() => expect(submit).toHaveBeenCalledWith(text, undefined));
    } finally {
      vi.unstubAllEnvs();
    }
  });
  it.each(['text', 'image'] as const)('pastes %s with the middle mouse button without submitting or copying', async kind => {
    fake.read.mockResolvedValue(kind === 'text'
      ? { kind, text: 'middle 中文\nnext line' }
      : { kind, image: { filePath: '/synthetic/image.png', mediaType: 'image/png' } });
    mount(true);
    send('mousemiddle', '\x1b[<1;3;3M');
    await vi.waitFor(() => expect(output).toContain(kind === 'text' ? 'middle 中文' : '[Image #1]'));
    expect(fake.read).toHaveBeenCalledWith(true);
    expect(fake.copy).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });
  it('ignores modified middle presses', () => {
    mount(true);
    send('mousemiddle', '\x1b[<17;3;3M', true);
    expect(fake.read).not.toHaveBeenCalled();
    expect(fake.copy).not.toHaveBeenCalled();
  });
  it('copies expanded large-paste text rather than its placeholder', async () => {
    mount(true);
    const text = '中文 paragraph\n'.repeat(100);
    send('paste', text);
    await vi.waitFor(() => expect(output).toContain('Pasted text #1'));
    send('b', '', true);
    await vi.waitFor(() => expect(fake.copy).toHaveBeenCalledWith(text));
    await vi.waitFor(() => expect(output).toContain('已复制到剪贴板'));
  });
  it('shows read failures even when all normal status bar items are hidden', async () => {
    fake.read.mockRejectedValue(new Error('Linux 剪贴板不可用，请使用终端粘贴。'));
    mount(true);
    send('v', '', true);
    await vi.waitFor(() => expect(output).toContain('Linux 剪贴板不可用'));
    expect(submit).not.toHaveBeenCalled();
  });
  it('routes clipboard feedback through the existing three-pane tip footer', async () => {
    const onTipChange = vi.fn();
    fake.read.mockRejectedValue(new Error('SSH 会话请使用终端粘贴。'));
    mount(true, onTipChange);
    send('v', '', true);
    await vi.waitFor(() => expect(onTipChange).toHaveBeenCalledWith('SSH 会话请使用终端粘贴。'));
    expect(output).not.toContain('SSH 会话请使用终端粘贴');
  });
});
afterEach(() => {
  app?.unmount();
  app?.cleanup();
});
describe('clipboard shortcuts in standalone input', () => {
  it('pastes middle-button text into standalone fields as one line', async () => {
    fake.read.mockResolvedValue({ kind: 'text', text: 'first\nsecond' });
    mount();
    send('mousemiddle', '\x1b[<1;3;3M');
    await vi.waitFor(() => expect(output).toContain('firstsecond'));
    expect(fake.read).toHaveBeenCalledWith(false);
    expect(fake.copy).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });
  it('shows failure feedback and still accepts terminal paste', async () => {
    fake.read.mockRejectedValue(new Error('请使用终端粘贴。'));
    mount();
    send('v', '', true);
    await vi.waitFor(() => expect(output).toContain('请使用终端粘贴'));
    send('paste', '中文\r\ntext');
    await vi.waitFor(() => expect(output).toContain('中文text'));
    send('return');
    expect(submit).toHaveBeenCalledWith('中文text');
  });
  it('copies the current input and renders confirmed feedback', async () => {
    mount();
    send('paste', '中文');
    await vi.waitFor(() => expect(output).toContain('中文'));
    send('b', '', true);
    await vi.waitFor(() => expect(fake.copy).toHaveBeenCalledWith('中文'));
    await vi.waitFor(() => expect(output).toContain('已复制到剪贴板'));
  });
  it('pastes clipboard text as a single line without submitting', async () => {
    fake.read.mockResolvedValue({ kind: 'text', text: 'first\nsecond' });
    mount();
    send('v', '', true);
    await vi.waitFor(() => expect(output).toContain('firstsecond'));
    expect(submit).not.toHaveBeenCalled();
    expect(fake.read).toHaveBeenCalledWith(false);
  });
});