import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import type { Key } from '../src/hooks/useKeypress.js';
import { LoginSelector } from '../src/components/Login/LoginSelector.js';

const input = vi.hoisted(() => ({
  handleKey: undefined as ((key: Key) => void) | undefined,
}));

vi.mock('../src/hooks/useKeypress.js', () => ({
  // Mirror the real hook's subscription contract: a handler registered with
  // `isActive: false` must not receive keypresses. LoginSelector registers a
  // second, Escape-only handler while `submitting`; without this check the
  // last-registered inactive handler shadows the wizard handler and every
  // dispatched key becomes a no-op (the component never re-renders).
  useKeypress: (handler: (key: Key) => void, options: { isActive?: boolean } = {}) => {
    if (options.isActive !== false) {
      input.handleKey = handler;
    }
  },
}));

const waitForRender = () => new Promise(resolve => setTimeout(resolve, 40));

async function sendKey(name: string, sequence = '', insertable = false) {
  input.handleKey?.({
    name, sequence, insertable, shift: false, alt: false, ctrl: false, cmd: false,
  });
  await waitForRender();
}

describe('public API key configuration', () => {
  it('offers only API key setup and masks the key while preserving the submitted value', async () => {
    const onSelect = vi.fn();
    const stdout = Object.assign(new PassThrough(), { columns: 100, rows: 24 });
    const frames: string[] = [];
    stdout.on('data', chunk => frames.push(chunk.toString()));
    const app = render(
      <LoginSelector
        onSelect={onSelect}
        providers={[{
          id: 'custom', name: 'Custom Provider', baseUrl: '', apiKeyHint: '', models: [],
        }]}
      />,
      { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, debug: true },
    );

    try {
      await waitForRender();
      expect(frames.join('')).toContain('Configure API Key');
      expect(frames.join('')).not.toMatch(/LiId|Device Code/);
      await sendKey('return');
      await sendKey('return');
      await sendKey('text', 'https://api.example.com/v1', true);
      await sendKey('return');
      await sendKey('text', 'example-model', true);
      await sendKey('return');
      const beforeKey = frames.length;
      const key = 'test-only-api-value';
      await sendKey('text', key, true);
      expect(frames.slice(beforeKey).join('')).not.toContain(key);
      expect(frames.slice(beforeKey).join('')).toContain('•'.repeat(key.length));
      await sendKey('return');

      expect(onSelect).toHaveBeenCalledTimes(1);
      expect(onSelect.mock.calls[0][0]).toBe('3');
      expect(JSON.parse(onSelect.mock.calls[0][1])).toEqual({
        provider_id: 'custom',
        base_url: 'https://api.example.com/v1',
        model: 'example-model',
        api_key: key,
      });
    } finally {
      app.unmount();
      app.cleanup();
      input.handleKey = undefined;
    }
  });

  it('cancels reconfiguration before applying any credentials', async () => {
    const onSelect = vi.fn();
    const app = render(<LoginSelector onSelect={onSelect} cancelable />, {
      stdout: Object.assign(new PassThrough(), { columns: 80, rows: 24 }),
      stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, debug: true,
    });
    try {
      await waitForRender();
      await sendKey('escape');
      expect(onSelect).toHaveBeenCalledWith('cancel');
    } finally {
      app.unmount();
      app.cleanup();
      input.handleKey = undefined;
    }
  });
});