import { EventEmitter } from 'node:events';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render } from '@jrichman/ink';
import { SubAgentDetailView } from '../src/components/SubAgent/SubAgentDetailView.js';
import { mergeSubAgentEntry } from '../src/utils/subAgentMessages.js';
import type { SubAgentMessageEntry } from '../src/hooks/useAcp/types.js';

vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));
vi.mock('../src/hooks/useTerminalSize.js', () => ({
  useTerminalSize: () => ({ rows: 30, columns: 100 }),
}));

describe('sub-agent detail real Ink rendering', () => {
  it('renders partial reasoning and replaces it before the agent completes', () => {
    const stdout = new EventEmitter() as any;
    stdout.columns = 100;
    stdout.rows = 30;
    const writes: string[] = [];
    stdout.write = (data: string) => { writes.push(data); return true; };
    const item = { id: 'sa_test', title: 'Stream test', status: 'running' as const };
    let entries: SubAgentMessageEntry[] = [];
    const view = () => (
      <SubAgentDetailView item={item} entries={entries} terminalWidth={100} onClose={() => {}} />
    );
    const instance = render(view(), { stdout, debug: true });
    const screen = () => [...writes].reverse().find(write => write.includes('Stream test')) ?? '';
    try {
      expect(screen()).toContain('No messages recorded');
      entries = mergeSubAgentEntry(entries, {
        id: 'r1', kind: 'thinking', text: 'REASONING-FIRST', isComplete: false,
      });
      instance.rerender(view());
      expect(screen()).toContain('REASONING-FIRST');
      expect(screen()).toContain('[running]');
      expect(screen()).toContain('1 message');

      entries = mergeSubAgentEntry(entries, {
        id: 'r1', kind: 'thinking', text: 'REASONING-FIRST NEXT-DELTA', isComplete: false,
      });
      instance.rerender(view());
      expect(screen()).toContain('NEXT-DELTA');
      expect(screen().match(/REASONING-FIRST/g)).toHaveLength(1);
      expect(screen()).toContain('1 message');

      entries = mergeSubAgentEntry(entries, {
        id: 'r1', kind: 'thinking', text: 'REASONING-FIRST NEXT-DELTA', isComplete: true,
      });
      instance.rerender(view());
      expect(screen()).toContain('NEXT-DELTA');
      expect(screen().match(/REASONING-FIRST/g)).toHaveLength(1);
    } finally {
      instance.unmount();
    }
  });
});