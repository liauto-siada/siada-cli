import React from 'react';
import { PassThrough, Writable } from 'node:stream';
import { Box, render } from '@jrichman/ink';
import stripAnsi from 'strip-ansi';
import { Banner, type BannerProps } from '../components/Banner/Banner.js';
import { ConversationBlock, conversationBlocks } from '../components/Chat/ConversationViewport.js';
import type { Message } from '../types/index.js';

const ignoreMeasurement = () => {};

/** Render into private streams so export never redraws or reads the live terminal. */
async function renderFrame(node: React.ReactNode, columns: number): Promise<string> {
  const stdout = Object.assign(new Writable({
    write(_chunk, _encoding, callback) { callback(); },
  }), { columns, rows: 24, isTTY: false });
  const stdin = new PassThrough();
  let resolveFrame!: (output: string) => void;
  const frame = new Promise<string>(resolve => { resolveFrame = resolve; });
  const app = render(node, {
    stdout: stdout as unknown as NodeJS.WriteStream,
    stdin: stdin as unknown as NodeJS.ReadStream,
    stderr: stdout as unknown as NodeJS.WriteStream,
    patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => resolveFrame(output),
  });
  try {
    const output = await Promise.race([
      frame,
      app.waitUntilExit().then(() => { throw new Error('Export renderer exited before producing a frame'); }),
    ]);
    return stripAnsi(output).split('\n').map(line => line.trimEnd()).join('\n');
  } finally {
    app.unmount();
    app.cleanup();
    stdin.destroy();
    stdout.destroy();
  }
}

export function renderExportBanner(info: BannerProps, columns: number): Promise<string> {
  return renderFrame(<Banner {...info} interactive={false} />, columns);
}

export interface ConversationRenderOptions {
  bannerInfo?: BannerProps;
  columns?: number;
  isCollapsed?: boolean;
  collapsedOverrides?: ReadonlyMap<string, boolean>;
  presentation?: boolean;
}

/** Render all history blocks, including those outside the virtualized viewport. */
export async function renderExportConversation(
  messages: Message[], options: ConversationRenderOptions = {},
): Promise<string> {
  const columns = Math.max(1, Math.floor(options.columns || 80));
  const presentation = options.presentation ?? false;
  const collapsed = options.isCollapsed ?? options.bannerInfo?.isCollapsed ?? false;
  const parts: string[] = [];
  if (options.bannerInfo) parts.push(await renderExportBanner(options.bannerInfo, columns), '');
  // Bound each render tree without dropping history or truncating long answers.
  for (const block of conversationBlocks(messages, presentation)) {
    parts.push(await renderFrame(
      <Box width={columns} flexDirection="column">
        <ConversationBlock block={block} width={columns}
          collapsed={options.collapsedOverrides?.get(block.id) ?? collapsed}
          presentation={presentation} hovered={false}
          onMeasure={ignoreMeasurement} onHeadingRef={ignoreMeasurement} onBlockRef={ignoreMeasurement} />
      </Box>, columns,
    ));
  }
  return parts.join('\n').trimEnd() + '\n';
}