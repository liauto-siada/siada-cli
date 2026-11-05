import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { Writable } from 'node:stream';
import { render } from '@jrichman/ink';

// The picker only needs keyboard wiring for real use; the test drives rendering.
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));

import { DemoPickerCard } from '../src/components/layouts/DemoPickerCard.js';

class MockStdout extends Writable {
  columns = 80;
  rows = 24;
  chunks: string[] = [];
  _write(chunk: any, _enc: any, cb: (err?: Error | null) => void) {
    this.chunks.push(chunk.toString());
    cb();
  }
}

const stripAnsi = (value: string) => value.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '');

const renderCard = (items: string[]) => {
  const stdout = new MockStdout();
  const stderr = new MockStdout();
  const instance = render(
    <DemoPickerCard
      title="Agents · Sub agents"
      items={items}
      onSelect={() => {}}
      onClose={() => {}}
      pageHeight={12}
    />,
    {
      stdout,
      stderr,
      stdin: new Writable({ write: (_chunk, _enc, cb) => cb() }) as any,
      patchConsole: false,
      exitOnCtrlC: false,
    },
  );
  return { instance, stdout, stderr };
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('DemoPickerCard row keys', () => {
  it('does not warn when two rows render the same label', () => {
    // Two sub-agent runs of the same instruction that failed with the same
    // error produce byte-identical labels. A text-only React key then collides,
    // and every collision warning is written to the terminal by Ink, scrolling
    // the whole UI away while the panel stays open.
    const duplicate = 'visual-reviewer dispatch (rerun): req-home-001 · failed · Error code: 404';
    // The CLI renders with `patchConsole: false`, so React's warning reaches the
    // terminal through the global console — exactly what corrupts the frame.
    const consoleErrors: string[] = [];
    vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      consoleErrors.push(args.map(String).join(' '));
    });

    const { instance, stderr } = renderCard([duplicate, duplicate, 'other agent · running']);
    instance.unmount();

    const emitted = consoleErrors.join('') + stderr.chunks.join('');
    expect(emitted).not.toContain('same key');
    expect(emitted).not.toContain('Encountered two children');
  });

  it('renders a multi-line label on a single row', () => {
    const { instance, stdout } = renderCard(['first line\n\nsecond line · failed']);
    instance.unmount();

    const frame = stripAnsi(stdout.chunks.join(''));
    expect(frame).toContain('first line second line · failed');
  });
});
