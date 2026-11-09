import { describe, it, expect } from 'vitest';
import type { Message } from '../../../../types/index.js';
import { appendCommandResult } from '../commandResult.js';

describe('independent command results', () => {
  it('preserves the active answer object and streaming metadata', () => {
    const answer: Message = {
      id: 'answer', type: 'agent', content: 'unfinished answer', author: 'Siada', timestamp: '',
      metadata: { subtype: 'answer', isStreaming: true, streamEnd: false },
    };
    const result = appendCommandResult([answer], {
      commandId: 'q1', command: 'status', content: 'Model: synthetic',
    });
    expect(result[0]).toBe(answer);
    expect(result[0].metadata?.streamEnd).toBe(false);
    expect(result[1].metadata?.subtype).toBe('slash_command_result');
    expect(result[1].content).toBe('Model: synthetic');
  });

  it('deduplicates by command id and keeps errors out of the model stream', () => {
    const data = { commandId: 'q1', command: 'status', content: 'synthetic failure', error: true };
    const once = appendCommandResult([], data);
    expect(once[0].type).toBe('error');
    expect(appendCommandResult(once, data)).toBe(once);
  });
});