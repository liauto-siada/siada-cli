/**
 * SiadaACPAdapter session/update routing tests.
 */

import { describe, it, expect, vi } from 'vitest';
import { SiadaACPAdapter } from '../adapter.js';
import { SiadaACPClient } from '../client.js';
import { logger } from '../../utils/logger.js';

describe('command output during a live model stream', () => {
  it('does not use slash-command buffers or stop the active animation', () => {
    const adapter = new SiadaACPAdapter();
    const result = vi.fn(), stop = vi.fn(), message = vi.fn();
    adapter.on('ui:commandResult', result);
    adapter.on('animation:stop', stop);
    adapter.on('message', message);
    const stream = { isActive: true, content: ['unfinished model output'] };
    (adapter as any).streamingBuffer = stream;
    const params = { commandId: 'q', command: 'status', content: 'Model: synthetic' };
    (adapter as any).tryParseACPJson(JSON.stringify({
      jsonrpc: '2.0', method: 'ui/commandResult', params,
    }));
    expect(result).toHaveBeenCalledWith(params);
    expect((adapter as any).streamingBuffer).toBe(stream);
    expect((adapter as any).slashCommandBuffer).toBeNull();
    expect(stop).not.toHaveBeenCalled();
    expect(message).not.toHaveBeenCalled();
  });
});

describe('ACP log correlation', () => {
  it('transmits a unique request identifier without altering prompt or image fields', async () => {
    const adapter = new SiadaACPAdapter();
    const write = vi.fn(() => true);
    (adapter as any).process = { stdin: { write, writable: true } };
    (adapter as any).isReady = true;
    const params = { prompt: '/status\n<<<SIADA_MSG_END>>>', image_paths: ['synthetic.png'], queue_id: 'q' };
    await adapter.sendMessage({ jsonrpc: '2.0', id: '1', method: 'agent/execute', params });
    await adapter.sendMessage({ jsonrpc: '2.0', id: '2', method: 'agent/execute', params });
    const envelopes = write.mock.calls.map(([frame]) => JSON.parse(frame.split('\n')[1]));
    expect(envelopes[0].prompt).toBe(params.prompt);
    expect(envelopes[0].image_paths).toEqual(params.image_paths);
    expect(envelopes[0].queue_id).toBe('q');
    expect(envelopes[0]._meta.siadaLog.requestId).toBeTruthy();
    expect(envelopes[0]._meta.siadaLog.requestId).not.toBe(envelopes[1]._meta.siadaLog.requestId);
    await adapter.sendMessage({ jsonrpc: '2.0', id: '3', method: 'agent/stop', params: {} });
    expect(write.mock.calls[2][0]).toContain('\x03');
  });

  it('preserves stream metadata alongside log metadata', () => {
    const adapter = new SiadaACPAdapter();
    const events: any[] = [];
    adapter.on('message', event => events.push(event));
    const spy = vi.spyOn(logger, 'debug');
    (adapter as any).tryParseACPJson(JSON.stringify({
      jsonrpc: '2.0', method: 'session/update',
      params: {
        reason: 'message_chunk', content: 'synthetic',
        metadata: { chunkType: 'answer', streamStartId: 'stream' },
        _meta: { siadaLog: { sessionId: 's', requestId: 'r', agent: 'CodeAgent' } },
      },
    }));
    expect(events[0].data.streamStartId).toBe('stream');
    expect(events[0].data.subtype).toBe('answer');
    spy.mockRestore();
  });
});

describe('SiadaACPAdapter handleACPSessionUpdate', () => {
  it.each(['notification', 'blocked', 'stopped'])('routes %s hook feedback independently of errors and tools', status => {
    const client = new SiadaACPClient({} as any);
    const adapter = client.adapter;
    const received: any[] = [];
    const messages: any[] = [];
    client.on('agentMessage', message => messages.push(message));
    adapter.on('message', event => received.push(event));
    (adapter as any).tryParseACPJson(JSON.stringify({
      jsonrpc: '2.0', method: 'session/update',
      params: { reason: 'lifecycle_event', type: 'hook', content: 'Synthetic hook notice',
        hook_event: 'PreToolUse', hook_status: status, timestamp: 123 },
    }));
    expect(received).toHaveLength(1);
    expect(received[0].data).toMatchObject({
      content: 'Synthetic hook notice', subtype: 'hook', isStreaming: false, streamEnd: true,
      metadata: { eventType: 'hook', hookEvent: 'PreToolUse', hookStatus: status },
    });
    expect(messages).toHaveLength(1);
    expect(messages[0].metadata).toMatchObject({
      subtype: 'hook', eventType: 'hook', hookEvent: 'PreToolUse', hookStatus: status,
    });
  });

  it('preserves lifecycle errors as errors instead of tool output', () => {
    const adapter = new SiadaACPAdapter();
    const received: any[] = [];
    adapter.on('message', event => received.push(event));
    (adapter as any).tryParseACPJson(JSON.stringify({
      jsonrpc: '2.0', method: 'session/update',
      params: { reason: 'lifecycle_event', type: 'error',
        content: 'The system is currently experiencing high demand.',
        timestamp: '2026-01-01T00:00:00Z' },
    }));
    expect(received).toHaveLength(1);
    expect(received[0].data).toMatchObject({
      content: 'The system is currently experiencing high demand.',
      subtype: 'error', isStreaming: false, streamEnd: true,
      metadata: { eventType: 'error' },
    });
  });

  it.each(['ui/loginDismiss', 'ui/loginCancelled', 'ui/loginError'])(
    'closes the login selector on %s',
    method => {
      const adapter = new SiadaACPAdapter();
      const dismissed = vi.fn();
      adapter.on('ui:loginDismiss', dismissed);
      (adapter as any).tryParseACPJson(JSON.stringify({
        jsonrpc: '2.0', method, params: { reason: 'synthetic cancellation' },
      }));
      expect(dismissed).toHaveBeenCalledOnce();
      expect(dismissed).toHaveBeenCalledWith({ reason: 'synthetic cancellation' });
    },
  );

  it("routes reason 'restore_input' to an 'input:restore' event carrying the content", () => {
    const adapter = new SiadaACPAdapter();
    const received: Array<{ content: string }> = [];
    adapter.on('input:restore', (data: { content: string }) => { received.push(data); });

    (adapter as any).handleACPSessionUpdate({
      params: { reason: 'restore_input', content: 'fix the bug' },
    });

    expect(received).toEqual([{ content: 'fix the bug' }]);
  });

  it.each(['request_user_input', 'user_input_closed'])(
    'ignores retired question notification %s without changing input readiness',
    (reason) => {
      const adapter = new SiadaACPAdapter();
      const emit = vi.spyOn(adapter, 'emit');

      (adapter as any).handleACPSessionUpdate({
        params: {
          reason,
          metadata: { request_id: 'retired-request', status: 'waiting' },
        },
      });

      expect(emit).not.toHaveBeenCalled();

      (adapter as any).handleACPSessionUpdate({
        params: { reason: 'input_ready', metadata: { animation_control: 'stop' } },
      });
      expect(emit).toHaveBeenCalledOnce();
      expect(emit).toHaveBeenCalledWith('animation:stop');
    },
  );

  it('continues to route password input independently of retired question tools', () => {
    const adapter = new SiadaACPAdapter();
    const received: unknown[] = [];
    adapter.on('interactive:input', (data) => received.push(data));

    (adapter as any).handleACPSessionUpdate({
      params: {
        reason: 'interactive_input_request',
        content: 'Password:',
        metadata: { inputType: 'password', isPassword: true },
      },
    });

    expect(received).toEqual([{
      prompt: 'Password:', inputType: 'password', isPassword: true,
    }]);
  });
});

describe('SiadaACPAdapter readiness (banner_info)', () => {
  const banner = {
    params: { reason: 'banner_info', content: '{}', metadata: { type: 'banner' } },
  };

  it('marks ready even after waitForReady already timed out', () => {
    // First login (e.g. configuring a Custom Provider) can exceed the 30s
    // waitForReady timeout, whose handler clears readyResolver but leaves
    // isReady false. The banner then arrives late and must still mark ready,
    // otherwise isConnected() stays false and every send reports "Not connected".
    const adapter = new SiadaACPAdapter();
    (adapter as any).readyResolver = null;
    (adapter as any).isReady = false;

    (adapter as any).handleACPSessionUpdate(banner);

    expect((adapter as any).isReady).toBe(true);
  });

  it('is adapter-ready once the late banner arrives', () => {
    const adapter = new SiadaACPAdapter();
    (adapter as any).readyResolver = null;
    (adapter as any).isReady = false;
    (adapter as any).process = { exitCode: null };

    (adapter as any).handleACPSessionUpdate(banner);

    expect(adapter.isAdapterReady()).toBe(true);
  });

  it('resolves and clears a pending waitForReady resolver', () => {
    const adapter = new SiadaACPAdapter();
    const resolve = vi.fn();
    (adapter as any).isReady = false;
    (adapter as any).readyResolver = resolve;

    (adapter as any).handleACPSessionUpdate(banner);

    expect(resolve).toHaveBeenCalledOnce();
    expect((adapter as any).readyResolver).toBeNull();
    expect((adapter as any).isReady).toBe(true);
  });
});
