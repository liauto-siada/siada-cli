import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClientConfig, Message } from '../src/types/index.js';
import type { ThinkingStep } from '../src/constants/phrases.js';

vi.mock('../src/utils/logger.js', () => ({
  LogLevel: { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 },
  logger: {
    debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
    logACPMessage: vi.fn(), logStateChange: vi.fn(), logWithTiming: vi.fn(),
  },
}));

import { SiadaACPAdapter } from '../src/acp/adapter.js';
import { SiadaACPClient } from '../src/acp/client.js';
import { ThinkingIndicator } from '../src/components/common/ThinkingIndicator.js';
import { useACPState } from '../src/hooks/useAcp/state/index.js';
import { useStreamingMessages } from '../src/hooks/useAcp/streaming/index.js';
import { useClientEvents } from '../src/hooks/useAcp/events/index.js';

beforeEach(() => {
  vi.spyOn(SiadaACPAdapter.prototype, 'start').mockResolvedValue(undefined);
});

afterEach(() => vi.restoreAllMocks());

async function mountActivityIndicator() {
  const stdout = Object.assign(new PassThrough(), { columns: 120, rows: 24 });
  const config = { workingDir: '.', model: 'test-model' } as ClientConfig;
  let client: SiadaACPClient | null = null;
  let step: ThinkingStep | null = null;
  let output = '';
  let streaming: ReturnType<typeof useStreamingMessages>;

  function Harness() {
    const state = useACPState();
    client = state.client;
    step = state.activeStep;
    streaming = useStreamingMessages({
      ...state, stdout, workingDir: config.workingDir, model: config.model,
    });
    useClientEvents(config, { ...state, ...streaming });
    return <ThinkingIndicator active={state.loading} step={state.activeStep} showTime={false} />;
  }

  const app = render(<Harness />, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: frame => { output = frame.output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  await vi.waitFor(() => expect(client).not.toBeNull());

  return {
    emit(params: Record<string, unknown>) {
      (client!.adapter as any).handleACPSessionUpdate({
        params: { reason: 'lifecycle_event', ...params },
      });
    },
    get step() { return step; },
    get output() { return output; },
    get streaming() { return streaming; },
    close() { app.unmount(); app.cleanup(); },
  };
}

describe('agent activity indicator', () => {
  it.each([
    { type: 'info', content: 'Compacted: 100 → 22 messages (78 removed)' },
    { type: 'info', content: 'Nothing to compact (conversation too short or already compact).' },
    { type: 'info', content: 'Compaction failed: synthetic failure' },
    { type: 'error', content: 'Compaction failed: synthetic failure' },
    { type: 'info', content: 'Compaction interrupted.' },
  ])('ends the compaction animation before another model token arrives: $content ($type)', async event => {
    const ui = await mountActivityIndicator();
    try {
      ui.emit({ type: 'processing_started', animation_control: 'start' });
      ui.emit({ type: 'info', content: 'Compacting context...' });
      await vi.waitFor(() => {
        expect(ui.step).toBe('compaction');
        expect(ui.output).toContain('Compacting context...');
      });

      ui.emit(event);
      await vi.waitFor(() => {
        expect(ui.step).toBe('reasoning');
        expect(ui.output).toContain('Model reasoning...');
        expect(ui.output).not.toContain('Compacting context...');
      });
    } finally {
      ui.close();
    }
  });

  it.each([
    { type: 'info', content: 'Compression is enabled for the archive.' },
    { type: 'warning', content: 'The compact layout needs more space.' },
    { type: 'tool_result', content: '读取了压缩模块，继续分析。' },
    { type: 'tool_use', delta: 'Compacting context...', chunk_index: 0, is_final: true },
    { type: 'tool_use', delta: 'compress archive.zip', chunk_index: 1, is_final: true },
  ])('does not infer compaction from ordinary messages or tool chunks: $type', async event => {
    const ui = await mountActivityIndicator();
    try {
      ui.emit({ type: 'processing_started', animation_control: 'start' });
      ui.emit(event);
      await vi.waitFor(() => {
        expect(ui.step).toBe('tool_execution');
        expect(ui.output).toContain('Executing tools...');
        expect(ui.output).not.toContain('Compacting context...');
      });
    } finally {
      ui.close();
    }
  });

  it('resets a previous compaction label when processing starts again', async () => {
    const ui = await mountActivityIndicator();
    try {
      ui.emit({ type: 'info', content: 'Compacting context...' });
      await vi.waitFor(() => expect(ui.step).toBe('compaction'));
      ui.emit({ type: 'processing_started', animation_control: 'start' });
      await vi.waitFor(() => {
        expect(ui.step).toBe('reasoning');
        expect(ui.output).toContain('Model reasoning...');
      });
    } finally {
      ui.close();
    }
  });

  it.each(['thinking', 'answer'])('recognizes a %s stream before its first text delta', async messageType => {
    const ui = await mountActivityIndicator();
    try {
      ui.emit({ type: 'processing_started', animation_control: 'start' });
      ui.emit({ type: 'info', content: 'Compacting context...' });
      await vi.waitFor(() => expect(ui.step).toBe('compaction'));
      ui.emit({ type: 'message_start', message_type: messageType, message_id: 'model-stream' });
      await vi.waitFor(() => {
        expect(ui.step).toBe('reasoning');
        expect(ui.output).toContain('Model reasoning...');
      });
      ui.emit({
        type: 'content_delta', delta: 'I will inspect the compression module.',
        is_final: false, stream_start_id: 'model-stream',
      });
      await vi.waitFor(() => expect(ui.step).toBe('reasoning'));
    } finally {
      ui.close();
    }
  });

  it('clears the compaction label when streaming state is reset', async () => {
    const ui = await mountActivityIndicator();
    try {
      ui.emit({ type: 'info', content: 'Compacting context...' });
      await vi.waitFor(() => expect(ui.step).toBe('compaction'));
      ui.streaming.resetStreaming();
      await vi.waitFor(() => expect(ui.step).toBeNull());
    } finally {
      ui.close();
    }
  });

  it('applies the same compaction boundaries to process messages', async () => {
    const ui = await mountActivityIndicator();
    const message = (content: string): Message => ({
      id: content, type: 'system', content, author: 'Siada', timestamp: '2026-01-01T00:00:00.000Z',
      metadata: { subtype: 'process', isStreaming: false, streamEnd: true },
    });
    try {
      ui.streaming.handleAgentMessage(message('Compacting context...'));
      await vi.waitFor(() => expect(ui.step).toBe('compaction'));
      ui.streaming.handleAgentMessage(message('Compacted: 100 → 22 messages (78 removed)'));
      await vi.waitFor(() => expect(ui.step).toBe('reasoning'));
    } finally {
      ui.close();
    }
  });
});