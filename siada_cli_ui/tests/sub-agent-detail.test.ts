import { describe, it, expect } from 'vitest';
import { entriesToMessages } from '../src/components/SubAgent/SubAgentDetailView.js';

describe('entriesToMessages', () => {
  it('maps kinds and drops tool_output entries', () => {
    const msgs = entriesToMessages('sa_x', [
      { kind: 'thinking', text: 't' },
      { kind: 'tool_call', text: 'c', toolName: 'run_cmd' },
      { kind: 'tool_output', text: 'o' },   // filtered out — results are noise in the detail view
      { kind: 'message', text: 'm' },
    ]);
    expect(msgs.map(m => [m.type, m.metadata?.subtype])).toEqual([
      ['agent', 'thinking'],
      ['agent', 'tool_use'],
      ['agent', 'answer'],
    ]);
    expect(msgs.map(m => m.id)).toEqual(['sa_x_0', 'sa_x_1', 'sa_x_2']);
  });
});
