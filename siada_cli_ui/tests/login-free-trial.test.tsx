import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  keypress: null as null | ((key: { name: string; sequence?: string }) => void),
}));
vi.mock('../src/hooks/useKeypress.js', () => ({
  useKeypress: (handler: typeof state.keypress, options: { isActive?: boolean }) => {
    if (options.isActive) state.keypress = handler;
  },
}));
vi.mock('../src/components/Input/ShortcutTextInput.js', () => ({
  ShortcutTextInput: () => { throw new Error('Free trial must not ask for a key'); },
}));
import { LoginSelector } from '../src/components/Login/LoginSelector.js';

let app: ReturnType<typeof render> | undefined;
afterEach(() => {
  app?.unmount();
  app?.cleanup();
  app = undefined;
  state.keypress = null;
});

it.each([false, true])('selects free models and navigates back (cancelable=%s)', async cancelable => {
  const onSelect = vi.fn();
  let output = '';
  const stdout = Object.assign(new PassThrough(), { columns: 100, rows: 24 });
  stdout.on('data', chunk => { output += chunk.toString(); });
  const models = Array.from({ length: 12 }, (_, i) => ({
    id: `provider/model-${i}:free`, name: `Free model ${i}`, context: 0,
  }));
  app = render(<LoginSelector onSelect={onSelect} cancelable={cancelable} freeTrialModels={models} />,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0, debug: true });
  await vi.waitFor(() => expect(state.keypress).not.toBeNull());
  state.keypress!({ name: 'down' });
  await vi.waitFor(() => expect(output).toContain('▶ Free Trial'));
  state.keypress!({ name: 'return' });
  await vi.waitFor(() => expect(output).toContain('Free Trial — Choose Model'));
  for (let i = 1; i < models.length; i++) {
    state.keypress!({ name: 'down' });
    await vi.waitFor(() => expect(output).toContain(`▶ Free model ${i}`));
  }
  state.keypress!({ name: 'return' });
  expect(onSelect).toHaveBeenCalledWith('4', JSON.stringify({ model: models[11].id }));
  state.keypress!({ name: 'escape' });
  await vi.waitFor(() => expect(output.slice(-2000)).toContain('▶ Free Trial'));
  state.keypress!({ name: 'escape' });
  expect(onSelect).toHaveBeenLastCalledWith(cancelable ? 'cancel' : 'skip');
});

it('disables duplicate submission and allows cancellation while submitting', async () => {
  const onSelect = vi.fn();
  const stdout = Object.assign(new PassThrough(), { columns: 100, rows: 24 });
  app = render(<LoginSelector onSelect={onSelect} submitting cancelable />,
    { stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false });
  await vi.waitFor(() => expect(state.keypress).not.toBeNull());
  state.keypress!({ name: 'return' });
  expect(onSelect).not.toHaveBeenCalled();
  state.keypress!({ name: 'escape' });
  expect(onSelect).toHaveBeenCalledWith('cancel');
});