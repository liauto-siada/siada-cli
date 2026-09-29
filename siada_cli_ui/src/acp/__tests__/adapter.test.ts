/**
 * SiadaACPAdapter session/update routing tests.
 */

import { describe, it, expect } from 'vitest';
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
});
