import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClientConfig, Message } from '../src/types/index.js';

const observed = vi.hoisted(() => ({ messages: [] as Message[], client: null as any }));
vi.mock('../src/components/layouts/MainLayout.js', () => ({
  MainLayout: (props: { messages: Message[] }) => { observed.messages = props.messages; return null; },
}));
vi.mock('../src/components/Banner/Banner.js', () => ({ Banner: () => null }));
vi.mock('../src/hooks/useMemoryMonitor.js', () => ({ useMemoryMonitor: () => {} }));
vi.mock('../src/hooks/useBackendExit.js', () => ({ useBackendExit: () => {} }));
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));
vi.mock('../src/utils/logger.js', () => ({
  LogLevel: { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 },
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
    logACPMessage: vi.fn(), logStateChange: vi.fn(), logWithTiming: vi.fn(),
    withContext: (_context: unknown, callback: () => unknown) => callback() },
}));

import { App } from '../src/components/App.js';
import { SiadaACPAdapter } from '../src/acp/adapter.js';
import { SiadaACPClient } from '../src/acp/client.js';

let app: ReturnType<typeof render> | undefined;
const config = { workingDir: '/sample/project', model: 'synthetic' } as ClientConfig;

beforeEach(() => {
  observed.messages = [];
  observed.client = null;
  vi.spyOn(SiadaACPAdapter.prototype, 'start').mockResolvedValue(undefined);
  vi.spyOn(SiadaACPClient.prototype, 'connect').mockImplementation(async function () {
    observed.client = this;
    this.emit('connected');
  });
  vi.spyOn(SiadaACPClient.prototype, 'isConnected').mockReturnValue(true);
  vi.spyOn(SiadaACPClient.prototype, 'sendMessage').mockResolvedValue(undefined);
  vi.spyOn(SiadaACPClient.prototype, 'sendNotification').mockImplementation(function (method) {
    if (method === 'session/pullHistory') this.emit('session:pullHistoryDone', {});
  });
});

afterEach(() => {
  app?.unmount();
  app?.cleanup();
  app = undefined;
  vi.restoreAllMocks();
});

function notify(method: string, params: object = {}) {
  const adapter = observed.client.adapter as any;
  expect(adapter.tryParseACPJson(JSON.stringify({ jsonrpc: '2.0', method, params }))).toBe(true);
}

async function mount() {
  app = render(<App config={config} initialPrompt="Continue the task" />, {
    stdout: Object.assign(new PassThrough(), { columns: 100, rows: 30 }),
    stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
  });
  await vi.waitFor(() => expect(observed.client).not.toBeNull());
  (observed.client.adapter as any).handleACPSessionUpdate({ params: {
    reason: 'banner_info', content: JSON.stringify({
      version: 'synthetic', working_dir: config.workingDir, model: 'synthetic',
    }),
  } });
  observed.client.emit('ready');
  await new Promise(resolve => setTimeout(resolve, 30));
}

describe('initial submission with real ACP hooks', () => {
  it.each([true, false])('waits for delayed startup history (nonempty=%s)', async nonempty => {
    await mount();
    expect(observed.client.sendMessage).not.toHaveBeenCalled();
    notify('ui/loadHistory', { messages: nonempty ? [{ role: 'user', content: 'saved task' }] : [] });
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(observed.client.sendMessage).not.toHaveBeenCalled();
    notify('ui/startupComplete');
    await vi.waitFor(() => expect(observed.client.sendMessage).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(observed.messages.map(message => message.content)).toEqual(
      nonempty ? ['saved task', 'Continue the task'] : ['Continue the task'],
    ));
    notify('ui/startupComplete');
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(observed.client.sendMessage).toHaveBeenCalledTimes(1);
  });

  it('does not wait for a history batch on a new session', async () => {
    await mount();
    notify('ui/startupComplete');
    await vi.waitFor(() => expect(observed.client.sendMessage).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(observed.messages.map(message => message.content)).toEqual(['Continue the task']));
  });

  it('commits history before submitting when completion arrives in the same batch', async () => {
    await mount();
    notify('ui/loadHistory', { messages: [{ role: 'user', content: 'saved task' }] });
    notify('ui/startupComplete');
    await vi.waitFor(() => expect(observed.client.sendMessage).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(observed.messages.map(message => message.content)).toEqual([
      'saved task', 'Continue the task',
    ]));
  });
});
