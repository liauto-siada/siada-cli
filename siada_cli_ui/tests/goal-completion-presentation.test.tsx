import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import stringWidth from 'string-width';
import { ConversationViewport } from '../src/components/Chat/ConversationViewport.js';
import { GoalStatusBar } from '../src/components/Goal/GoalStatusBar.js';
import { goalObjectivePreview, goalResultSummary } from '../src/utils/goalDisplay.js';
import { colors } from '../src/utils/colors.js';
import { setActiveTheme } from '../src/themes/index.js';
import type { Key } from '../src/hooks/useKeypress.js';
import type { Message } from '../src/types/index.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useKeypress.js', async () => {
  const React = await import('react');
  return { useKeypress: (handler: (key: Key) => void, options: { isActive?: boolean } = {}) => {
    React.useEffect(() => {
      if (options.isActive === false) return;
      handlers.add(handler);
      return () => { handlers.delete(handler); };
    }, [handler, options.isActive]);
  }};
});
vi.mock('../src/utils/clipboard.js', () => ({
  copySelectionToClipboard: vi.fn().mockResolvedValue('native'),
}));

const wait = () => new Promise(resolve => setTimeout(resolve, 80));
afterEach(() => { setActiveTheme('dark'); });

describe('compact completion actions', () => {
  it.each(['dark', 'light'] as const)('renders blue completion actions and expands full Goal content in %s', async theme => {
    setActiveTheme(theme);
    chalk.level = 3;
    const objective = 'Verify compatibility and installation evidence for Windows';
    const result = { achieved: true, turns: 3, elapsedSeconds: 20, tokensUsed: 0,
      objective, reason: 'All checks passed.' };
    const messages: Message[] = [
      { id: 'plan', type: 'agent', timestamp: '', content: '✓  Check compatibility\n\n[1/1 completed]',
        metadata: { subtype: 'tool_use' } },
      { id: 'goal', type: 'system', timestamp: '', content: '',
        metadata: { subtype: 'goal_result', goalResult: result } },
    ];
    let raw = '', frame = '';
    const screen = new TerminalScreen(24, 80);
    const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 80 });
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const app = render(<ConversationViewport messages={messages} width={80} height={20}
      isCollapsed presentation />, {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { raw = output; frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await wait();
      const rgb = colors.info.match(/[0-9a-f]{2}/gi)!.map(channel => parseInt(channel, 16)).join(';');
      for (const action of ['Plan completed', 'Goal Achieved']) {
        expect(raw).toMatch(new RegExp(`\\x1b\\[38;2;${rgb}m[●✓] (?:\\x1b\\[[0-9;]*m)*${action}`));
      }
      const goalLine = frame.split('\n').find(line => line.includes('Goal Achieved'))!;
      expect(goalLine).toContain('…');
      expect(goalLine).not.toContain('checks');
      expect(stringWidth(goalLine)).toBeLessThanOrEqual(48);
      expect(frame).not.toContain(objective);
      const lines = frame.split('\n');
      const row = lines.findIndex(line => line.includes('Goal Achieved'));
      const x = lines[row].indexOf('Goal') + 1;
      for (const name of ['mouseclick', 'mouserelease']) {
        [...handlers].forEach(handler => handler({ name, sequence: `\x1b[<0;${x};${row + 1}${name === 'mouseclick' ? 'M' : 'm'}`,
          ctrl: false, cmd: false, alt: false, shift: false, insertable: false }));
        await wait();
      }
      expect(frame).toContain(objective);
      expect(frame).toContain('Checks: 3');
      expect(frame).toContain('All checks passed.');
      expect(screen.display()).toContain('Goal Achieved');
    } finally { app.unmount(); app.cleanup(); }
  });

  it('bounds live Goal and record previews for CJK text without losing status', async () => {
    const objective = '核对实现与跨平台验收证据'.repeat(5);
    expect(stringWidth(goalObjectivePreview(objective))).toBeLessThanOrEqual(24);
    expect(goalObjectivePreview(objective)).toContain('…');
    const result = { achieved: false, continuing: true, turns: 2, elapsedSeconds: 5,
      tokensUsed: 0, objective, reason: 'More evidence needed.' };
    expect(stringWidth(goalResultSummary(result, 44))).toBeLessThanOrEqual(44);
    expect(goalResultSummary(result, 44)).toContain('Continuing');
    let frame = '';
    const app = render(<GoalStatusBar compact width={48} goalState={{
      goal: { objective, status: 'active' }, verifying: true,
    }} />, {
      stdout: Object.assign(new PassThrough(), { rows: 24, columns: 48 }), stdin: new PassThrough(),
      patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await wait();
      expect(frame).toContain('Verifying');
      expect(frame).not.toContain(objective);
      expect(frame.split('\n')).toHaveLength(1);
      expect(stringWidth(frame)).toBeLessThanOrEqual(48);
    } finally { app.unmount(); app.cleanup(); }
  });
});