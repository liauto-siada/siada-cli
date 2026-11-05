import React, { useRef, useState } from 'react';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { render, Text } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import type { ClientConfig } from '../src/types/config.js';
import type { Message } from '../src/types/index.js';
import type { GoalState, TodoItem, TodoMessageRange } from '../src/hooks/useAcp/types.js';

let emitSession: (id: string) => void;
let emitTodoState: (todos: TodoItem[]) => void;

const EDIT = 'In the file `src/a.ts`, replace the string:\n```ts\nold\n```\nwith:\n```ts\nnew\n```';
const MARKDOWN_EDIT = 'In the file `docs/notes.md``, replace the string:\nold\nwith:\nnew';
const FAILED_EDIT = 'File edit: update src/example.rs\n<!-- siada-file-edit:start -->\n' +
  JSON.stringify({ callId: 'failed-history', action: 'update', path: 'src/example.rs', status: 'failed',
    error: 'Invalid JSON arguments; no changes applied.' }) + '\n<!-- siada-file-edit:end -->';
vi.mock('../src/acp/client.js', () => ({
  SiadaACPClient: class extends EventEmitter {
    adapter = new EventEmitter();

    connect() {
      emitSession = id => this.emit('session:id', id);
      emitTodoState = todos => this.adapter.emit('context:todoState', { todos });
      // The backend sends its single restored banner, then a tiny history
      // batch before the frontend connect() promise can settle.
      this.emit('session:id', 'restored-session');
      this.adapter.emit('ui:loadHistory', {
        messages: [
          { role: 'user', content: 'from cold resume' },
          { role: 'agent', content: EDIT, subtype: 'tool_use' },
          { role: 'agent', content: MARKDOWN_EDIT, subtype: 'tool_use' },
          { role: 'agent', content: FAILED_EDIT, subtype: 'tool_use' },
        ],
      });
      emitTodoState([{ content: 'Restore current task', status: 'in_progress' }]);
      this.adapter.emit('context:goalState', {
        goal: { objective: 'Finish task', status: 'blocked', turns: 3 }, verifying: false,
      });
      this.adapter.emit('ui:startupComplete');
      return new Promise<void>(() => {});
    }

    disconnect() { return Promise.resolve(); }
  },
}));

import { useClientEvents } from '../src/hooks/useAcp/events/index.js';

describe('cold --resume history delivery', () => {
  it('handles ui/loadHistory even when it arrives before connect resolves', async () => {
    let observed: Message[] = [];
    let observedTodos: TodoItem[] = [];
    let observedRanges = new Map<string, TodoMessageRange>();
    let observedGoal: GoalState | null = null;
    let observedStartupComplete = false;
    const config = { workingDir: '/sample/project' } as ClientConfig;
    const noop = () => {};

    function Harness() {
      const [messages, setMessages] = useState<Message[]>([]);
      const [todos, setTodoItems] = useState<TodoItem[]>([]);
      const [ranges, setTodoMessageRanges] = useState(new Map<string, TodoMessageRange>());
      const [goal, setGoalState] = useState<GoalState | null>(null);
      const [startupComplete, setStartupComplete] = useState(false);
      const clientRef = useRef(null);
      observed = messages;
      observedTodos = todos;
      observedRanges = ranges;
      observedGoal = goal;
      observedStartupComplete = startupComplete;
      useClientEvents(config, {
        setMessages,
        clientRef,
        setClient: noop,
        setConnectionStatus: noop,
        setLoading: noop,
        setStartupComplete,
        setTokenUsage: noop,
        setInteractiveInput: noop,
        setLoginState: noop,
        setTodoItems,
        setTodoMessageRanges,
        setGoalState,
        setSubAgentItems: noop,
        setSubAgentMessages: noop,
        setBannerInfo: noop,
        setCacheStatus: noop,
        handleAgentMessage: noop,
        handleToolUse: noop,
        handleStreamAborted: noop,
        flushStreamingNow: noop,
        resetStreaming: noop,
        messagesRef: useRef([]),
        currentSessionIdRef: useRef(null),
        pendingHistoryRef: useRef(false),
        historyBufferRef: useRef([]),
        pendingUserMessageIdRef: useRef(null),
        pullHistoryTimeoutRef: useRef(null),
      } as unknown as Parameters<typeof useClientEvents>[1]);
      return <Text>{messages.map(m => m.content).join(' ')}</Text>;
    }

    const stdout = Object.assign(new PassThrough(), { columns: 80, rows: 24 });
    const app = render(<Harness />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    });
    try {
      await new Promise(resolve => setTimeout(resolve, 60));
      expect(observed.map(m => m.content)).toEqual(['from cold resume', EDIT, MARKDOWN_EDIT, FAILED_EDIT]);
      expect(observed[1].metadata).toMatchObject({ subtype: 'tool_use', streamEnd: true });
      expect(observed[2].metadata).toMatchObject({ subtype: 'tool_use', streamEnd: true });
      expect(observed[3].metadata).toMatchObject({ subtype: 'tool_use', streamEnd: true });
      expect(observedTodos).toEqual([{ content: 'Restore current task', status: 'in_progress' }]);
      expect(observedGoal).toMatchObject({ goal: { status: 'blocked', turns: 3 }, verifying: false });
      expect(observedStartupComplete).toBe(true);
      expect(observedRanges.has('Restore current task')).toBe(true);
      expect(observedRanges.get('Restore current task')?.startIdx).toBe(4);

      emitSession('different-session');
      await new Promise(resolve => setTimeout(resolve, 60));
      expect(observedTodos).toEqual([]);
      expect(observedRanges.size).toBe(0);
      expect(observedGoal).toBeNull();

      // Reusing the same task label must open a range owned by the new session.
      emitTodoState([{ content: 'Restore current task', status: 'in_progress' }]);
      await new Promise(resolve => setTimeout(resolve, 60));
      expect(observedRanges.has('Restore current task')).toBe(true);
      expect(observedRanges.get('Restore current task')?.startIdx).toBe(0);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});
