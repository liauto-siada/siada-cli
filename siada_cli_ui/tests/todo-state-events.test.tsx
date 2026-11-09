import React, { useEffect } from 'react';
import { PassThrough } from 'node:stream';
import { render, Text } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClientConfig } from '../src/types/index.js';
import type { TodoItem } from '../src/hooks/useAcp/types.js';

vi.mock('../src/utils/logger.js', () => ({
  LogLevel: { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 },
  logger: {
    debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
    logACPMessage: vi.fn(), logStateChange: vi.fn(), logWithTiming: vi.fn(),
  },
}));

import { SiadaACPAdapter } from '../src/acp/adapter.js';
import { SiadaACPClient } from '../src/acp/client.js';
import { useACPState } from '../src/hooks/useAcp/state/index.js';
import { useStreamingMessages } from '../src/hooks/useAcp/streaming/index.js';
import { useClientEvents } from '../src/hooks/useAcp/events/index.js';

beforeEach(() => {
  vi.spyOn(SiadaACPAdapter.prototype, 'start').mockResolvedValue(undefined);
});

afterEach(() => vi.restoreAllMocks());

async function mountTodoState() {
  const stdout = Object.assign(new PassThrough(), { columns: 100, rows: 24 });
  const config = { workingDir: '.', model: 'test-model' } as ClientConfig;
  let client: SiadaACPClient | null = null;
  let state: ReturnType<typeof useACPState>;

  function Harness() {
    state = useACPState();
    client = state.client;
    useEffect(() => { state.messagesRef.current = state.messages; }, [state.messages]);
    const streaming = useStreamingMessages({
      ...state, stdout, workingDir: config.workingDir, model: config.model,
    });
    useClientEvents(config, { ...state, ...streaming });
    return <Text>{JSON.stringify(state.todoItems)}</Text>;
  }

  const app = render(<Harness />, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
  });
  await vi.waitFor(() => expect(client).not.toBeNull());

  return {
    toolInput(content: string) {
      (client!.adapter as any).handleACPSessionUpdate({
        params: { reason: 'lifecycle_event', type: 'tool_use', delta: content, chunk_index: 0, is_final: true },
      });
    },
    failedResult() {
      (client!.adapter as any).handleACPSessionUpdate({
        params: { reason: 'lifecycle_event', type: 'tool_result',
          content: 'An error occurred while running the tool. Error: Invalid JSON input for tool todo_write' },
      });
    },
    todoState(todos: TodoItem[]) {
      client!.adapter.emit('context:todoState', { todos });
    },
    get todos() { return state.todoItems; },
    get messages() { return state.messages; },
    get ranges() { return state.todoMessageRanges; },
    close() { app.unmount(); app.cleanup(); },
  };
}

describe('confirmed todo state', () => {
  it('keeps a rejected todo write out of session state', async () => {
    const ui = await mountTodoState();
    const attempted = '◐  Attempted task\n○  Remaining task\n[0/2 completed]';
    try {
      ui.toolInput(attempted);
      ui.failedResult();
      await vi.waitFor(() => expect(ui.messages.some(message => message.content === attempted)).toBe(true));

      expect(ui.todos).toEqual([]);
      expect(ui.ranges.size).toBe(0);
    } finally {
      ui.close();
    }
  });

  it.each(['Clearing todo list', '◐  Stale task\n[0/1 completed]'])(
    'preserves the resumed backend snapshot after late tool input: %s', async input => {
      const ui = await mountTodoState();
      const resumed: TodoItem[] = [{ content: 'Resumed task', status: 'in_progress' }];
      try {
        ui.todoState(resumed);
        await vi.waitFor(() => expect(ui.todos).toEqual(resumed));
        ui.toolInput(input);
        await vi.waitFor(() => expect(ui.messages.some(message => message.content === input)).toBe(true));

        expect(ui.todos).toEqual(resumed);
        expect(ui.ranges.has('Resumed task')).toBe(true);
        expect(ui.ranges.has('Stale task')).toBe(false);

        ui.todoState([]);
        await vi.waitFor(() => expect(ui.todos).toEqual([]));
        expect(ui.ranges.get('Resumed task')?.endIdx).toEqual(expect.any(Number));
      } finally {
        ui.close();
      }
    },
  );
});