import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { Scrollable } from '../src/components/common/Scrollable.js';
import type { Key } from '../src/hooks/useKeypress.js';

const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return {
    useKeypress: (handler: (key: Key) => void) => {
      React.useEffect(() => {
        handlers.add(handler);
        return () => { handlers.delete(handler); };
      }, [handler]);
    },
  };
});

describe('scrollbar visibility', () => {
  it('keeps Ink scrollbars visible by default and hides only their drawing', async () => {
    let output = '';
    const stdout = Object.assign(new PassThrough(), { rows: 12, columns: 40 });
    const view = (hidden: boolean, top: number) =>
      <Box height={4} width={40} flexDirection="column" overflowY="scroll" scrollTop={top}
        scrollbarVisibility={hidden ? 'hidden' : undefined}>
        <Box flexShrink={0}>
          <Text>{Array.from({ length: 30 }, (_, index) => `ROW_${index}`).join('\n')}</Text>
        </Box>
      </Box>;
    const app = render(view(false, 0), {
      stdout, stdin: new PassThrough(), patchConsole: false, maxFps: 0,
      onRender: frame => { output = frame.output; },
    });
    try {
      await vi.waitFor(() => expect(output).toMatch(/[█▀▄]/));
      app.rerender(view(true, 10));
      await vi.waitFor(() => expect(output).toContain('ROW_10'));
      expect(output).not.toMatch(/[█▀▄]/);
      expect(output).not.toContain('ROW_0');
    } finally { app.unmount(); app.cleanup(); }
  });

  it('renders a thin line and keeps wheel and page scrolling active', async () => {
    let output = '';
    const stdout = Object.assign(new PassThrough(), { rows: 12, columns: 40 });
    const app = render(
      <Scrollable hasFocus height={5} width={40} scrollToBottom={false}>
        <Text>{Array.from({ length: 30 }, (_, index) => `ROW_${index}`).join('\n')}</Text>
      </Scrollable>,
      {
        stdout, stdin: new PassThrough(), patchConsole: false, maxFps: 0,
        onRender: frame => { output = frame.output; },
      },
    );
    const send = (name: string) => {
      const key: Key = { name, sequence: '', alt: false, ctrl: false, cmd: false,
        shift: false, insertable: false };
      handlers.forEach(handler => handler(key));
    };
    try {
      await vi.waitFor(() => expect(output).toContain('ROW_0'));
      expect(output).toContain('│');
      expect(output).not.toMatch(/[█▀▄]/);
      send('wheeldown');
      await vi.waitFor(() => expect(output).toContain('ROW_7'));
      expect(output).not.toContain('ROW_0');
      send('pageup');
      await vi.waitFor(() => expect(output).toContain('ROW_0'));
      expect(output).toContain('│');
      expect(output).not.toMatch(/[█▀▄]/);
    } finally { app.unmount(); app.cleanup(); }
  });
});