import './helpers/chineseLocale.js';
import React, { useState } from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { useQuitShortcut, QUIT_SHORTCUT_TIMEOUT_MS } from '../src/hooks/useQuitShortcut.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const handlers = new Set<(key: Key) => void>();
vi.mock('../src/hooks/useTerminalSize.js', () => ({
  useTerminalSize: () => ({ rows: 24, columns: 80 }),
}));
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

const wait = (ms = 45) => new Promise(resolve => setTimeout(resolve, ms));
const key = (name: string, extra: Partial<Key> = {}) => {
  const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false,
    insertable: false, sequence: '', ...extra };
  [...handlers].forEach(handler => handler(event));
};
const ctrlC = () => key('c', { ctrl: true, sequence: '\x03' });

function harness(running = false) {
  const stopped = vi.fn();
  const exited = vi.fn();
  const submitted = vi.fn();
  const stdout = Object.assign(new PassThrough(), { rows: 24, columns: 80 });
  const screen = new TerminalScreen(24, 80);
  let frame = '';
  stdout.on('data', chunk => screen.feed(chunk.toString()));

  function Harness() {
    const [loading, setLoading] = useState(running);
    const shortcut = useQuitShortcut({ running: loading, onExit: exited,
      onStop: () => { stopped(); setLoading(false); } });
    return <AppProvider><MainLayout workingDir="." model="synthetic" isCollapsed
      messages={[{ id: 'a', type: 'agent', content: 'Synthetic answer', timestamp: '', author: 'Siada',
        metadata: { subtype: 'answer' } }]}
      loading={loading} onSendMessage={submitted} onCtrlC={shortcut.onCtrlC} interruptNotice={shortcut.notice}
      todoItems={[{ content: 'Demo todo', status: 'in_progress' }]}
      todoMessageRanges={new Map([['Demo todo', { startIdx: 0, endIdx: null }]])}
      subAgentItems={[{ id: 'agent', title: 'Demo agent', status: 'running' }]}
      subAgentMessages={new Map([['agent', [{ kind: 'message', text: 'Agent answer' }]]])}
    /></AppProvider>;
  }
  const app = render(<Harness />, { stdout, stdin: new PassThrough(), patchConsole: false,
    exitOnCtrlC: false, maxFps: 0, onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); } });
  return { stopped, exited, submitted, screen, get frame() { return frame; },
    close() { app.unmount(); app.cleanup(); } };
}

describe('three-pane Ctrl+C interaction', () => {
  it.each([false, true])('arms on the first press and exits on the second, running=%s', async running => {
    const test = harness(running);
    try {
      await wait();
      ctrlC(); await wait();
      expect(test.exited).not.toHaveBeenCalled();
      expect(test.stopped).toHaveBeenCalledTimes(running ? 1 : 0);
      expect(test.screen.display()).toContain(running ? '已停止 · 再按 Ctrl+C 退出' : '再按 Ctrl+C 退出');
      ctrlC(); await wait();
      expect(test.exited).toHaveBeenCalledOnce();
      expect(test.stopped).toHaveBeenCalledTimes(running ? 1 : 0);
      expect(test.frame.split('\n').length).toBeLessThanOrEqual(23);
    } finally { test.close(); }
  });

  it('expires the exit hint and treats a later press as a new first press', async () => {
    const test = harness();
    try {
      await wait();
      ctrlC(); await wait(QUIT_SHORTCUT_TIMEOUT_MS + 30);
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      ctrlC(); await wait();
      expect(test.exited).not.toHaveBeenCalled();
      expect(test.frame).toContain('再按 Ctrl+C 退出');
    } finally { test.close(); }
  });

  it('cancels the armed shortcut on editing while pointer motion leaves it armed', async () => {
    const test = harness();
    try {
      await wait();
      ctrlC(); await wait();
      key('left'); await wait();
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      ctrlC(); await wait();
      expect(test.exited).not.toHaveBeenCalled();
      key('mousemove', { sequence: '\x1b[<35;70;3M' }); await wait();
      ctrlC(); await wait();
      expect(test.exited).toHaveBeenCalledOnce();
    } finally { test.close(); }
  });

  it.each(['ordinary', 'large paste'])('clears and recalls the %s draft before interrupting active work', async kind => {
    const test = harness(true);
    const text = kind === 'ordinary' ? 'Draft to keep' : 'Original pasted content '.repeat(80);
    try {
      await wait();
      key('paste', { sequence: text, insertable: true }); await wait(110);
      ctrlC(); await wait();
      expect(test.stopped).not.toHaveBeenCalled();
      expect(test.exited).not.toHaveBeenCalled();
      expect(test.frame).toContain('已清空输入 · 再按 Ctrl+C 退出');
      expect(test.frame).toContain('可输入下一条消息');
      key('up'); await wait(110);
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      expect(test.frame).toContain(kind === 'ordinary' ? text : '[Pasted text #1');
      key('return'); await wait();
      expect(test.submitted).toHaveBeenCalledWith(text, undefined);
    } finally { test.close(); }
  });

  it('handles two Ctrl+C presses in one input batch after clearing a draft', async () => {
    const test = harness();
    try {
      await wait();
      key('paste', { sequence: 'Draft', insertable: true }); await wait();
      ctrlC(); ctrlC(); await wait();
      expect(test.exited).toHaveBeenCalledOnce();
      expect(test.stopped).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('dismisses the turn directory without interrupting or arming exit', async () => {
    const test = harness(true);
    try {
      await wait();
      key('g', { ctrl: true }); await wait();
      expect(test.frame).toContain('对话目录');
      ctrlC(); await wait();
      expect(test.frame).not.toContain('对话目录');
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      expect(test.stopped).not.toHaveBeenCalled();
      ctrlC(); await wait();
      expect(test.stopped).toHaveBeenCalledOnce();
      expect(test.exited).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it.each(['todo', 'sub-agent'])('closes %s details before stopping the main run', async panel => {
    const test = harness(true);
    try {
      await wait();
      key('tab'); await wait();
      if (panel === 'sub-agent') { key('tab'); await wait(); }
      key('return'); await wait();
      expect(test.frame).toContain('Esc 返回');
      ctrlC(); await wait();
      expect(test.frame).toContain('可输入下一条消息');
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      expect(test.stopped).not.toHaveBeenCalled();
      ctrlC(); await wait();
      expect(test.stopped).toHaveBeenCalledOnce();
      expect(test.exited).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('keeps selection-copy routing ahead of stop and clears any older exit hint', async () => {
    const test = harness(true);
    try {
      await wait();
      ctrlC(); await wait();
      key('selectioncopy', { ctrl: true }); await wait();
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      ctrlC(); await wait();
      expect(test.exited).not.toHaveBeenCalled();
      expect(test.stopped).toHaveBeenCalledOnce();
    } finally { test.close(); }
  });
});