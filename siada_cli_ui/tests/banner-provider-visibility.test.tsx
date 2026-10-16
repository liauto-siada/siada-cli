import React from 'react';
import { PassThrough } from 'node:stream';
import { stripVTControlCharacters } from 'node:util';
import { Box, Text, render } from '@jrichman/ink';
import { describe, expect, it } from 'vitest';

import { MessageList } from '../src/components/Chat/MessageList.js';
import { AppHeader } from '../src/components/layouts/AppHeader.js';
import { renderBannerBlock } from '../src/utils/conversationExport.js';

const columns = 160;
const header = {
  workingDir: '/synthetic/workspace',
  agent: 'coder',
  provider: 'example-provider',
  model: 'example-model',
};

describe('banner provider visibility', () => {
  it.each([true, false])('omits the provider from exports (compact=%s)', isCollapsed => {
    const output = renderBannerBlock({ ...header, isCollapsed }, columns);
    expect(output).toContain('Agent: coder, Model: example-model');
    expect(output).not.toContain('Provider:');
    expect(output).not.toContain(header.provider);
    expect(output).toContain(`${isCollapsed ? 'compact' : 'expanded'} mode (ctrl+o)`);
  });

  it.each([true, false])('omits the provider from the legacy header (compact=%s)', async isCollapsed => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 48 });
    const frames: string[] = [];
    const app = render(<AppHeader {...header} isCollapsed={isCollapsed} />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => frames.push(stripVTControlCharacters(output)),
    });
    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      expect(frames.at(-1)).toContain('Agent: coder, Model: example-model');
      expect(frames.at(-1)).not.toContain('Provider:');
      expect(frames.at(-1)).not.toContain(header.provider);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it.each([false, true])('keeps the provider hidden across view changes (noStatic=%s)', async noStatic => {
    const stdout = Object.assign(new PassThrough(), { columns, rows: 48 });
    const frames: string[] = [];
    const view = (isCollapsed: boolean) => (
      <Box width={columns} flexDirection="column">
        <MessageList
          messages={[]}
          headerProps={header}
          terminalWidth={columns}
          isCollapsed={isCollapsed}
          noStatic={noStatic}
        />
        <Text>input</Text>
      </Box>
    );
    const app = render(view(true), {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ staticOutput, output }) => {
        for (const frame of [staticOutput, output]) {
          if (frame?.includes('Agent:')) frames.push(stripVTControlCharacters(frame));
        }
      },
    });

    try {
      await new Promise(resolve => setTimeout(resolve, 80));
      expect(frames.at(-1)).toContain('Agent: coder, Model: example-model; compact mode');
      expect(frames.at(-1)).not.toContain('Provider:');
      expect(frames.at(-1)).not.toContain(header.provider);

      app.rerender(view(false));
      await new Promise(resolve => setTimeout(resolve, 450));
      expect(frames.at(-1)).toContain('Agent: coder, Model: example-model; expanded mode');
      expect(frames.at(-1)).not.toContain('Provider:');
      expect(frames.at(-1)).not.toContain(header.provider);

      app.rerender(view(true));
      await new Promise(resolve => setTimeout(resolve, 450));
      expect(frames.at(-1)).toContain('Agent: coder, Model: example-model; compact mode');
      expect(frames.at(-1)).not.toContain('Provider:');
      expect(frames.at(-1)).not.toContain(header.provider);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});