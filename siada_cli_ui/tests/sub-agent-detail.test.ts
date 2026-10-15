import { describe, it, expect } from 'vitest';
import { entriesToMessages } from '../src/components/SubAgent/SubAgentDetailView.js';
import { mergeSubAgentEntry } from '../src/utils/subAgentMessages.js';
import type { SubAgentMessageEntry } from '../src/hooks/useAcp/types.js';

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

  it('keeps the reasoning identity and streaming metadata through completion', () => {
    const entry: SubAgentMessageEntry = {
      id: 'r1', kind: 'thinking', text: 'partial', isComplete: false,
    };
    const pending = entriesToMessages('sa_x', [entry])[0];
    const completed = entriesToMessages('sa_x', [{ ...entry, text: 'complete', isComplete: true }])[0];
    expect(pending.id).toBe(completed.id);
    expect(pending.metadata).toMatchObject({ isStreaming: true, streamEnd: false });
    expect(completed.metadata).toMatchObject({ isStreaming: false, streamEnd: true });
  });
});

describe('mergeSubAgentEntry', () => {
  it('updates reasoning in place while preserving tools and legacy append entries', () => {
    const initial: SubAgentMessageEntry[] = [
      { id: 'r1', kind: 'thinking', text: 'first', isComplete: false },
      { kind: 'tool_call', text: 'tool' },
    ];
    const next = mergeSubAgentEntry(initial, {
      id: 'r1', kind: 'thinking', text: 'first second', isComplete: false,
    });
    expect(next.map(entry => entry.text)).toEqual(['first second', 'tool']);
    expect(initial[0].text).toBe('first');
    expect(next[1]).toBe(initial[1]);
    expect(mergeSubAgentEntry(next, { kind: 'thinking', text: 'legacy' })).toHaveLength(3);
  });

  it('accepts new identities and never reopens a completed entry', () => {
    const completed: SubAgentMessageEntry = {
      id: 'r1', kind: 'thinking', text: 'done', isComplete: true,
    };
    const entries = mergeSubAgentEntry([], completed);
    expect(mergeSubAgentEntry(entries, { ...completed, text: 'stale', isComplete: false })).toBe(entries);
    expect(mergeSubAgentEntry(entries, { ...completed, id: 'r2' })).toHaveLength(2);
  });
});
