import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClientConfig } from '../src/types/index.js';
import type { BannerInfo, LoginState } from '../src/hooks/useAcp/types.js';

const state = vi.hoisted(() => ({
  connectionStatus: { connected: false, connecting: true, ready: false, error: undefined as string | undefined },
  client: null as object | null,
  bannerInfo: null as BannerInfo | null,
  loginState: null as LoginState,
  loading: false,
  startupComplete: false,
  messages: [] as any[],
  sendMessage: vi.fn(),
  setShowSessionBrowser: null as ((show: boolean) => void) | null,
  mainRendered: false,
}));

vi.mock('../src/hooks/useACP.js', () => ({
  useACP: () => ({
    messages: state.messages,
    connectionStatus: state.connectionStatus,
    client: state.client,
    clientRef: { current: state.client },
    bannerInfo: state.bannerInfo,
    loginState: state.loginState,
    loading: state.loading,
    startupComplete: state.startupComplete,
    sendMessage: state.sendMessage,
  }),
}));
vi.mock('../src/components/layouts/MainLayout.js', () => ({
  MainLayout: () => { state.mainRendered = true; return null; },
}));
vi.mock('../src/components/Login/index.js', () => ({ LoginSelector: () => null, LoginWaiting: () => null }));
vi.mock('../src/components/SessionBrowser/index.js', () => ({ SessionBrowser: () => null }));
vi.mock('../src/components/Banner/Banner.js', () => ({ Banner: () => null }));
vi.mock('../src/hooks/useMemoryMonitor.js', () => ({ useMemoryMonitor: () => {} }));
vi.mock('../src/hooks/useBackendExit.js', () => ({ useBackendExit: () => {} }));
vi.mock('../src/hooks/useAdapterEvents.js', () => ({
  useAdapterEvents: (_client: unknown, handlers: any) => { state.setShowSessionBrowser = handlers.setShowSessionBrowser; },
}));
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));
vi.mock('../src/hooks/usePromptDrain.js', () => ({ usePromptDrain: () => {} }));
vi.mock('../src/utils/logger.js', () => ({
  LogLevel: { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 },
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { App } from '../src/components/App.js';

const config = { workingDir: '/sample/project', model: 'synthetic-model' } as ClientConfig;
let app: ReturnType<typeof render> | undefined;

beforeEach(() => {
  state.connectionStatus = { connected: false, connecting: true, ready: false, error: undefined };
  state.client = null;
  state.bannerInfo = null;
  state.loginState = null;
  state.loading = false;
  state.startupComplete = false;
  state.messages = [];
  state.setShowSessionBrowser = null;
  state.mainRendered = false;
  state.sendMessage.mockReset().mockResolvedValue(undefined);
});
afterEach(() => {
  app?.unmount();
  app?.cleanup();
  app = undefined;
});

function ready() {
  state.startupComplete = true;
  state.connectionStatus = { connected: true, connecting: false, ready: true, error: undefined };
  state.client = {};
  state.bannerInfo = { version: '0.0.0', workingDir: config.workingDir, agent: 'coder', provider: 'synthetic', model: config.model! };
}

async function mount(message?: string) {
  app = render(<App config={config} initialPrompt={message} />, {
    stdout: Object.assign(new PassThrough(), { columns: 100, rows: 30 }),
    stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
  });
  await new Promise(resolve => setTimeout(resolve, 30));
}

async function rerender(message?: string) {
  app!.rerender(<App config={config} initialPrompt={message} />);
  await new Promise(resolve => setTimeout(resolve, 30));
}

function expectSubmittedOnce(message: string) {
  expect(state.sendMessage).toHaveBeenCalledTimes(1);
  expect(state.sendMessage).toHaveBeenCalledWith(message, undefined);
}

describe('interactive initial message', () => {
  it.each(['你好', '/goal Fix the failing tests', 'Keep "quotes" and\nnewlines'])('submits %s once and leaves the UI open', async message => {
    ready();
    await mount(message);
    await vi.waitFor(() => expectSubmittedOnce(message));
    await rerender(message);
    expect(state.sendMessage).toHaveBeenCalledTimes(1);
    expect(state.mainRendered).toBe(true);
  });

  it.each([undefined, '', '   '])('does not submit a missing or blank message: %s', async message => {
    ready();
    await mount(message);
    expect(state.sendMessage).not.toHaveBeenCalled();
  });

  it('waits for readiness, banner configuration, and the connected client', async () => {
    await mount('你好');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.connectionStatus = { connected: true, connecting: false, ready: false, error: undefined };
    await rerender('你好');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.connectionStatus.ready = true;
    await rerender('你好');
    expect(state.sendMessage).not.toHaveBeenCalled();
    ready();
    state.client = null;
    await rerender('你好');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.client = {};
    await rerender('你好');
    expectSubmittedOnce('你好');
  });

  it.each(['selecting', 'waiting'] as const)('waits for login phase %s to finish', async phase => {
    ready();
    state.loginState = phase === 'selecting' ? { phase } : { phase, url: 'https://login.test', openBrowser: false };
    await mount('你好');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.loginState = null;
    await rerender('你好');
    expectSubmittedOnce('你好');
  });

  it('does not resubmit after a disconnect and reconnect', async () => {
    ready();
    await mount('你好');
    state.connectionStatus = { connected: false, connecting: true, ready: false, error: undefined };
    await rerender('你好');
    ready();
    await rerender('你好');
    expect(state.sendMessage).toHaveBeenCalledTimes(1);
  });

  it('waits for a startup session browser to close', async () => {
    await mount('Continue the task');
    state.setShowSessionBrowser!(true);
    ready();
    await rerender('Continue the task');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.setShowSessionBrowser!(false);
    await rerender('Continue the task');
    expectSubmittedOnce('Continue the task');
  });

  it('does not submit while an existing turn is busy', async () => {
    ready();
    state.loading = true;
    await mount('Continue the task');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.loading = false;
    await rerender('Continue the task');
    expectSubmittedOnce('Continue the task');
  });

  it('waits for startup history synchronization after the banner is ready', async () => {
    ready();
    state.startupComplete = false;
    await mount('Continue the task');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.messages = [{ id: 'history', type: 'user', content: 'saved task' }];
    await rerender('Continue the task');
    expect(state.sendMessage).not.toHaveBeenCalled();
    state.startupComplete = true;
    await rerender('Continue the task');
    expectSubmittedOnce('Continue the task');
  });

  it('does not submit through a startup error screen', async () => {
    ready();
    state.messages = [{ id: 'startup-error', type: 'error', content: 'synthetic startup failure',
      metadata: { type: 'startup_error' } }];
    await mount('你好');
    expect(state.sendMessage).not.toHaveBeenCalled();
  });

  it('submits after readiness when restored history contains a runtime error', async () => {
    ready();
    state.messages = [{ id: 'runtime-error', type: 'error', content: 'synthetic previous turn failure' }];
    await mount('Continue the task');
    expectSubmittedOnce('Continue the task');
    expect(state.mainRendered).toBe(true);
  });
});
