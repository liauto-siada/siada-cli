import React from 'react';
import { PassThrough } from 'node:stream';
import { Box, Text, render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ClientConfig, Message } from '../src/types/index.js';
import { SiadaACPAdapter } from '../src/acp/adapter.js';
import { SiadaACPClient } from '../src/acp/client.js';
import { MessageList } from '../src/components/Chat/MessageList.js';
import { useACPState } from '../src/hooks/useAcp/state/index.js';
import { useStreamingMessages } from '../src/hooks/useAcp/streaming/index.js';
import { useClientEvents } from '../src/hooks/useAcp/events/index.js';
import { parseFileEditPresentation } from '../src/utils/diff.js';

afterEach(() => vi.restoreAllMocks());

function content(callId: string, status: string, extra: Record<string, unknown> = {}): string {
  return `File edit: update example.rs\n<!-- siada-file-edit:start -->\n${JSON.stringify({
    callId, action: 'update', path: 'example.rs', status, ...extra,
  })}\n<!-- siada-file-edit:end -->`;
}

describe('real ACP and Ink file-edit results', () => {
  it.each([
    { collapsed: false, columns: 32 }, { collapsed: true, columns: 32 },
    { collapsed: false, columns: 80 }, { collapsed: true, columns: 80 },
  ])('bounds the entire pending suffix and eventually prints full ordered history, collapsed=$collapsed, columns=$columns', async ({ collapsed, columns }) => {
    vi.spyOn(SiadaACPAdapter.prototype, 'start').mockResolvedValue(undefined);
    const config = { workingDir: '.', model: 'test-model' } as ClientConfig;
    const stdout = Object.assign(new PassThrough(), { columns, rows: 24 });
    let client: SiadaACPClient | null = null;
    let observed: Message[] = [];
    let dynamic = '';
    const statics: string[] = [];
    const writes: string[] = [];
    stdout.on('data', chunk => writes.push(chunk.toString()));
    function Harness() {
      const state = useACPState();
      client = state.client;
      observed = state.messages;
      const streaming = useStreamingMessages({ ...state, stdout, workingDir: '.', model: config.model });
      useClientEvents(config, { ...state, ...streaming });
      return <Box width={columns} flexDirection="column">
        <MessageList messages={state.messages} isCollapsed={collapsed} />
        <Text>{Array.from({ length: 12 }, (_, index) => `input row ${index}`).join('\n')}</Text>
      </Box>;
    }
    const app = render(<Harness />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ staticOutput, output }) => { if (staticOutput) statics.push(staticOutput); dynamic = output; },
    });
    const text = (value: string) => value.replace(/\x1b\[[0-9;]*m/g, '');
    const emit = (delta: string) => (client!.adapter as any).handleACPSessionUpdate({
      params: { reason: 'lifecycle_event', type: 'tool_use', delta, chunk_index: 0, is_final: true },
    });
    try {
      await vi.waitFor(() => expect(client).not.toBeNull());
      emit(content('original', 'pending', { executionStatus: 'pending' }));
      await vi.waitFor(() => expect(text(dynamic).replace(/\s+/g, ' ')).toContain('Waiting for tool result'));
      const initialWrites = writes.join('').length;
      const addedText = Array.from({ length: 50 }, (_, index) => `added line ${index}`).join('\n');
      emit(content('large', 'completed', { oldString: '', newString: addedText }));
      await vi.waitFor(() => expect(observed).toHaveLength(2));
      expect(text(dynamic).split('\n').length).toBeLessThan(stdout.rows);
      expect(text(dynamic)).toContain('input row 11');
      expect(text(dynamic)).not.toContain('added line 49');
      expect(text(statics.join(''))).not.toContain('added line');
      for (let index = 0; index < 12; index++) emit(content(`later-${index}`, 'pending'));
      await vi.waitFor(() => expect(observed).toHaveLength(14));
      expect(text(dynamic).split('\n').length).toBeLessThan(stdout.rows);
      expect(text(dynamic)).toContain('input row 11');
      expect(writes.join('').slice(initialWrites)).not.toContain('\x1b[2J\x1b[3J\x1b[H');
      for (let index = 0; index < 12; index++) emit(content(`later-${index}`, 'failed', { error: `Rejected later ${index}.` }));
      emit(content('original', 'failed', { error: 'Hook blocked this tool call.' }));
      await vi.waitFor(() => expect(text(statics.join('')).replace(/\s+/g, ' ')).toContain('Rejected later 11.'));
      const finalized = text(statics.join('')).replace(/\s+/g, ' ');
      expect(finalized).toContain('added line 49');
      expect(finalized.indexOf('Hook blocked')).toBeLessThan(finalized.indexOf('added line 0'));
      expect(finalized.indexOf('added line 49')).toBeLessThan(finalized.indexOf('Rejected later 0.'));
      expect(finalized.match(/● Update example.rs/g)).toHaveLength(14);
      expect(text(dynamic)).toContain('input row 11');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it.each([
    { collapsed: false, invalid: false }, { collapsed: true, invalid: false },
    { collapsed: false, invalid: true }, { collapsed: true, invalid: true },
  ])('updates pending and failed rows without stale static boxes, collapsed=$collapsed, invalid=$invalid', async ({ collapsed, invalid }) => {
    vi.spyOn(SiadaACPAdapter.prototype, 'start').mockResolvedValue(undefined);
    const config = { workingDir: '.', model: 'test-model' } as ClientConfig;
    const stdout = Object.assign(new PassThrough(), { columns: 80, rows: 24 });
    let client: SiadaACPClient | null = null;
    let observed: Message[] = [];
    let dynamic = '';
    const statics: string[] = [];
    function Harness() {
      const state = useACPState();
      client = state.client;
      observed = state.messages;
      const streaming = useStreamingMessages({ ...state, stdout, workingDir: '.', model: config.model });
      useClientEvents(config, { ...state, ...streaming });
      return <Box width={80} flexDirection="column"><MessageList messages={state.messages} isCollapsed={collapsed} /><Text>input</Text></Box>;
    }
    const app = render(<Harness />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ staticOutput, output }) => { if (staticOutput) statics.push(staticOutput); dynamic = output; },
    });
    const text = (value: string) => value.replace(/\x1b\[[0-9;]*m/g, '');
    const emit = (delta: string) => (client!.adapter as any).handleACPSessionUpdate({
      params: { reason: 'lifecycle_event', type: 'tool_use', delta, chunk_index: 0, is_final: true },
    });
    try {
      await vi.waitFor(() => expect(client).not.toBeNull());
      emit(content('original', invalid ? 'failed' : 'pending', {
        argumentsComplete: !invalid, executionStatus: 'pending',
        ...(invalid ? { error: 'Invalid JSON arguments; no changes applied.' } : {}),
      }));
      await vi.waitFor(() => expect(text(dynamic)).toContain(invalid ? 'Invalid JSON' : 'Waiting for tool result...'));
      const originalId = observed[0]!.id;
      expect(text(statics.join(''))).not.toContain('Waiting for tool result');
      expect(text(statics.join(''))).not.toContain('Invalid JSON');
      emit(content('later', 'completed', { oldString: 'old', newString: 'new' }));
      await vi.waitFor(() => expect(text(dynamic)).toContain('(+1 -1)'));
      expect(text(statics.join(''))).not.toContain('(+1 -1)');
      emit(content('original', 'failed', { error: 'Invalid JSON arguments; no changes applied.' }));
      await vi.waitFor(() => expect(text(statics.join(''))).toContain('Invalid JSON arguments; no changes applied.'));
      expect(observed).toHaveLength(2);
      expect(observed[0]!.id).toBe(originalId);
      expect(observed.map(m => parseFileEditPresentation(m.content)?.status)).toEqual(['failed', 'completed']);
      const finalized = text(statics.join(''));
      expect(finalized.match(/● Update example.rs/g)).toHaveLength(2);
      expect(finalized.indexOf('Invalid JSON')).toBeLessThan(finalized.indexOf('(+1 -1)'));
      expect(finalized).not.toMatch(/[╭╮╰╯│]/);
      expect(finalized).not.toContain('Waiting for tool result');
      expect(text(dynamic)).toContain('input');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});
