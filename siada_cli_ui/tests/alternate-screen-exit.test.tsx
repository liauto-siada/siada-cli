import React from 'react';
import { PassThrough } from 'node:stream';
import { render, Text } from '@jrichman/ink';
import { describe, expect, it } from 'vitest';

describe('alternate-screen exit', () => {
  it.each([false, true])('restores the main screen without replaying messages (incremental=%s)', async incrementalRendering => {
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 80 });
    let output = '';
    stdout.on('data', chunk => { output += chunk.toString(); });
    const app = render(<Text>SYNTHETIC CONVERSATION MESSAGE</Text>, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false,
      alternateBuffer: true, incrementalRendering, maxFps: 0,
    });
    try {
      expect(output).toContain('\x1b[?1049h');
      expect(output).toContain('SYNTHETIC CONVERSATION MESSAGE');
      const exited = app.waitUntilExit();
      app.unmount();
      await exited;
      const restoreAt = output.lastIndexOf('\x1b[?1049l');
      expect(restoreAt).toBeGreaterThanOrEqual(0);
      expect(output).toContain('\x1b[?7h');
      expect(output.slice(restoreAt + '\x1b[?1049l'.length))
        .not.toContain('SYNTHETIC CONVERSATION MESSAGE');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});