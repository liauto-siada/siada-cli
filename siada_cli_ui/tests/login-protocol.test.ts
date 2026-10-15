import { describe, expect, it, vi } from 'vitest';
import { SiadaACPClient } from '../src/acp/client.js';
import type { ClientConfig } from '../src/types/index.js';
import { logger } from '../src/utils/logger.js';

describe('login protocol replies', () => {
  it.each([undefined, 'selector-request'])('writes API configuration with request ID %s without logging the key', async requestId => {
    const client = new SiadaACPClient({ workingDir: '.', model: 'test-model' } as ClientConfig);
    const write = vi.fn(() => true);
    (client.adapter as any).process = { exitCode: null, stdin: { write, writable: true } };
    const debug = vi.spyOn(logger, 'debug').mockImplementation(() => {});
    const info = vi.spyOn(logger, 'info').mockImplementation(() => {});
    try {
      const payload = JSON.stringify({ provider_id: 'kimi', api_key: 'synthetic-secret-key' });
      await client.sendLoginChoice('3', payload, requestId);
      const frame = write.mock.calls[0][0] as string;
      const body = frame.split('\n')[1];
      const encoded = body.slice('__LOGIN_CHOICE__:3:'.length);
      expect(body.startsWith('__LOGIN_CHOICE__:3:')).toBe(true);
      if (requestId) {
        expect(JSON.parse(encoded)).toEqual({ requestId, payload });
      } else {
        expect(encoded).toBe(payload);
      }
      expect(frame).toContain('synthetic-secret-key');
      expect(JSON.stringify([...debug.mock.calls, ...info.mock.calls])).not.toContain('synthetic-secret-key');
    } finally {
      debug.mockRestore();
      info.mockRestore();
    }
  });

  it('scopes cancellation to the same request without an API payload', async () => {
    const client = new SiadaACPClient({ workingDir: '.', model: 'test-model' } as ClientConfig);
    const send = vi.spyOn(client.adapter, 'sendRawInput').mockResolvedValue(undefined);
    vi.spyOn(client.adapter, 'isProcessRunning').mockReturnValue(true);
    await client.sendLoginChoice('cancel', undefined, 'selector-request');
    expect(send.mock.calls[0][0]).toBe(
      '__LOGIN_CHOICE__:cancel:{"requestId":"selector-request","payload":null}',
    );
    vi.restoreAllMocks();
  });
});