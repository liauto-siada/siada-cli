import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ProviderInfo } from '../src/components/Login/LoginSelector.js';

const state = vi.hoisted(() => ({
  keypress: null as null | ((key: { name: string; sequence?: string }) => void),
  submitKey: null as null | ((value: string) => void),
}));

vi.mock('../src/hooks/useKeypress.js', () => ({
  useKeypress: (handler: typeof state.keypress, options: { isActive?: boolean }) => {
    if (options.isActive) state.keypress = handler;
  },
}));
vi.mock('../src/components/Input/ShortcutTextInput.js', () => ({
  ShortcutTextInput: (props: { onSubmit: (value: string) => void }) => {
    state.submitKey = props.onSubmit;
    return null;
  },
}));

import { LoginSelector } from '../src/components/Login/LoginSelector.js';

let app: ReturnType<typeof render> | undefined;
afterEach(() => {
  app?.unmount();
  app?.cleanup();
  app = undefined;
  state.keypress = null;
  state.submitKey = null;
});

describe('DeepSeek API key configuration', () => {
  it.each([
    { label: 'offline first sign-in', providers: undefined, cancelable: false },
    { label: 'empty-cache reconfigure', providers: [], cancelable: true },
    {
      label: 'backend catalogue reconfigure',
      providers: [{
        id: 'deepseek', name: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1',
        apiKeyHint: 'DeepSeek API key',
        models: [{ id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', context: 1000 }],
      }] satisfies ProviderInfo[],
      cancelable: true,
    },
  ])('submits the selected provider and model for $label', async ({ providers, cancelable }) => {
    const onSelect = vi.fn();
    let output = '';
    const stdout = Object.assign(new PassThrough(), { columns: 100, rows: 30 });
    stdout.on('data', chunk => { output += chunk.toString(); });
    app = render(
      <LoginSelector onSelect={onSelect} providers={providers} cancelable={cancelable} liidDisabled />,
      // Debug mode exposes intermediate frames even when CI renders only on exit.
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0, debug: true },
    );
    await vi.waitFor(() => expect(state.keypress).not.toBeNull());
    state.keypress!({ name: 'return' });
    await vi.waitFor(() => expect(output).toContain('Choose Provider'));
    if (!providers?.length) {
      state.keypress!({ name: 'down' });
      await vi.waitFor(() => expect(output).toContain('▶ DeepSeek'));
    }
    state.keypress!({ name: 'return' });
    await vi.waitFor(() => expect(output).toContain('DeepSeek — Choose Model'));
    const model = providers?.length ? 'deepseek-v4-pro' : 'deepseek-flash';
    state.keypress!({ name: 'return' });
    await vi.waitFor(() => expect(state.submitKey).not.toBeNull());
    state.submitKey!('synthetic-deepseek-key');
    expect(onSelect).toHaveBeenCalledOnce();
    const [choice, payload] = onSelect.mock.calls[0];
    expect(choice).toBe('3');
    expect(JSON.parse(payload)).toEqual({
      provider_id: 'deepseek', model,
      base_url: 'https://api.deepseek.com/v1', api_key: 'synthetic-deepseek-key',
    });
  });
});