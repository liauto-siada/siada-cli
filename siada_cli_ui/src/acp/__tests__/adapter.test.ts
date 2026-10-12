/**
 * SiadaACPAdapter session/update routing tests.
 */

import { describe, it, expect, vi } from 'vitest';
import { SiadaACPAdapter } from '../adapter.js';

describe('SiadaACPAdapter handleACPSessionUpdate', () => {
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
