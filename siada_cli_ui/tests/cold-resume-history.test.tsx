import React, { useRef, useState } from 'react';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { render, Text } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import type { ClientConfig } from '../src/types/config.js';
import type { Message } from '../src/types/index.js';

const EDIT = 'In the file `src/a.ts`, replace the string:\n```ts\nold\n```\nwith:\n```ts\nnew\n```';

vi.mock('../src/acp/client.js', () => ({
  SiadaACPClient: class extends EventEmitter {
    adapter = new EventEmitter();

    connect() {
      // The backend sends its single restored banner, then a tiny history
      // batch before the frontend connect() promise can settle.
      this.adapter.emit('ui:loadHistory', {
        messages: [
          { role: 'user', content: 'from cold resume' },
          { role: 'agent', content: EDIT, subtype: 'tool_use' },
        ],
      });
      return new Promise<void>(() => {});
    }

    disconnect() { return Promise.resolve(); }
  },
}));

import { useClientEvents } from '../src/hooks/useAcp/events/index.js';

describe('cold --resume history delivery', () => {
  it('handles ui/loadHistory even when it arrives before connect resolves', async () => {
    let observed: Message[] = [];
    const config = { workingDir: '/sample/project' } as ClientConfig;
    const noop = () => {};

    function Harness() {
      const [messages, setMessages] = useState<Message[]>([]);
      const clientRef = useRef(null);
      observed = messages;
      useClientEvents(config, {
        setMessages,
        clientRef,
        setClient: noop,
        setConnectionStatus: noop,
        setLoading: noop,
        setTokenUsage: noop,
        setInteractiveInput: noop,
        setLoginState: noop,
        setTodoItems: noop,
        setTodoMessageRanges: noop,
        setGoalState: noop,
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
      expect(observed.map(m => m.content)).toEqual(['from cold resume', EDIT]);
      expect(observed[1].metadata).toMatchObject({ subtype: 'tool_use', streamEnd: true });
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});
