import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LoginSelectorProps } from '../src/components/Login/LoginSelector.js';
import type { ClientConfig } from '../src/types/index.js';

const state = vi.hoisted(() => ({
  selector: null as LoginSelectorProps | null,
  sendLoginChoice: vi.fn(),
}));

vi.mock('../src/hooks/useACP.js', () => ({
  useACP: () => ({
    messages: [],
    connectionStatus: { connecting: false, connected: true, ready: true },
    loading: false,
    loginState: { phase: 'selecting', cancelable: true },
    client: { sendLoginChoice: state.sendLoginChoice },
    clientRef: { current: null },
  }),
}));
vi.mock('../src/components/Login/index.js', () => ({
  LoginSelector: (props: LoginSelectorProps) => { state.selector = props; return null; },
  LoginWaiting: () => null,
}));
vi.mock('../src/components/Banner/Banner.js', () => ({ Banner: () => null }));
vi.mock('../src/hooks/useMemoryMonitor.js', () => ({ useMemoryMonitor: () => {} }));
vi.mock('../src/hooks/useBackendExit.js', () => ({ useBackendExit: () => {} }));
vi.mock('../src/hooks/useAdapterEvents.js', () => ({ useAdapterEvents: () => {} }));
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));
vi.mock('../src/hooks/usePromptDrain.js', () => ({ usePromptDrain: () => {} }));
vi.mock('../src/utils/logger.js', () => ({
  LogLevel: { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 },
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { App } from '../src/components/App.js';

let app: ReturnType<typeof render> | undefined;

beforeEach(() => {
  state.selector = null;
  state.sendLoginChoice.mockReset().mockResolvedValue(undefined);
});
afterEach(() => {
  app?.unmount();
  app?.cleanup();
  app = undefined;
});

async function submitLogin() {
  app = render(<App config={{ workingDir: '.', model: 'test-model' } as ClientConfig} />, {
    stdout: Object.assign(new PassThrough(), { columns: 100, rows: 30 }),
    stdin: new PassThrough(),
    patchConsole: false,
    exitOnCtrlC: false,
    maxFps: 0,
  });
  await vi.waitFor(() => expect(state.selector).not.toBeNull());
  state.selector!.onSelect('3', 'synthetic-payload');
  await vi.waitFor(() => expect(state.selector!.submitting).toBe(true));
}

describe('login submission', () => {
  it.each(['cancel', 'skip'] as const)('sends %s while a login reply is pending', async choice => {
    await submitLogin();
    state.selector!.onSelect(choice);
    await vi.waitFor(() => {
      expect(state.sendLoginChoice).toHaveBeenLastCalledWith(choice, undefined);
      expect(state.sendLoginChoice).toHaveBeenCalledTimes(2);
    });
  });

  it('still blocks duplicate API submissions while waiting for the backend', async () => {
    await submitLogin();
    state.selector!.onSelect('3', 'duplicate-payload');
    expect(state.sendLoginChoice).toHaveBeenCalledTimes(1);
    expect(state.sendLoginChoice).toHaveBeenCalledWith('3', 'synthetic-payload');
  });
});