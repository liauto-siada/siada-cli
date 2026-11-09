import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { Key } from '../../../contexts/KeypressContext.js';

const fake = vi.hoisted(() => ({
  key: null as ((key: Key) => void) | null,
  nativeRead: vi.fn(),
  nativeWrite: vi.fn(),
  nativeImage: vi.fn(),
}));
vi.mock('../../../hooks/useKeypress.js', () => ({
  useKeypress: (handler: (key: Key) => void) => { fake.key = handler; },
}));
// Real clipboard module: exercises the SSH fallback against the terminal copy cache.
vi.mock('../../../utils/nativeClipboard.js', () => ({
  nativeClipboard: { readText: fake.nativeRead, writeText: fake.nativeWrite, readImage: fake.nativeImage },
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
import { InputPromptWithWrapUseKPC } from '../InputPromptWithWrapUseKPC.js';
import { AppProvider } from '../../../store/context.js';
import { copySelectionToClipboard, resetTerminalCopyCache } from '../../../utils/clipboard.js';

let app: ReturnType<typeof render> | undefined;
let output = '';
const submit = vi.fn();
function mount() {
  const stdout = Object.assign(new PassThrough(), { columns: 80, rows: 24 });
  stdout.on('data', data => { output += String(data); });
  app = render(
    <AppProvider><InputPromptWithWrapUseKPC onSubmit={submit} width={80} /></AppProvider>,
    {
      stdout, stdin: new PassThrough(), patchConsole: false,
      exitOnCtrlC: false, maxFps: 0,
    },
  );
}
const send = (name: string, sequence = '', ctrl = false) => {
  fake.key!({ name, sequence, ctrl, insertable: !!sequence } as Key);
};

beforeEach(() => {
  vi.resetAllMocks();
  output = '';
  resetTerminalCopyCache();
  vi.stubEnv('SSH_CONNECTION', 'synthetic');
  fake.nativeRead.mockRejectedValue(new Error('native unavailable'));
  fake.nativeWrite.mockRejectedValue(new Error('native unavailable'));
  fake.nativeImage.mockResolvedValue(null);
});
afterEach(() => {
  vi.unstubAllEnvs();
  app?.unmount();
  app?.cleanup();
});

describe('Ctrl+V over SSH falls back to the last OSC 52 copy', () => {
  it('inserts the latest selection copy into the input box', async () => {
    // "Copy inside Siada": mouse selection delivered through OSC 52.
    const write = vi.fn();
    expect(await copySelectionToClipboard('选择复制的中文\nsecond line', { isTTY: true, write } as any)).toBe('osc52');
    mount();
    send('v', '', true);
    await vi.waitFor(() => expect(output).toContain('选择复制的中文'));
    expect(submit).not.toHaveBeenCalled();
    expect(fake.nativeRead).not.toHaveBeenCalled();
  });

  it('shows the SSH guidance when nothing was copied through the terminal', async () => {
    mount();
    send('v', '', true);
    await vi.waitFor(() => expect(output).toContain('SSH'));
    expect(fake.nativeRead).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });
});
