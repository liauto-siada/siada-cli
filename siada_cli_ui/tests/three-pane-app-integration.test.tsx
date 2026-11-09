import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/components/App.js';
import { SiadaACPAdapter } from '../src/acp/adapter.js';
import { promptQueueStore } from '../src/store/promptQueueStore.js';
import { inputRestoreStore } from '../src/store/inputRestoreStore.js';
import type { ClientConfig, Message } from '../src/types/index.js';
import type { Key } from '../src/hooks/useKeypress.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { configManager } from '../src/utils/config.js';
import { setUiLanguage } from '../src/i18n/index.js';
import { exportConversation } from '../src/utils/conversationExport.js';
vi.mock('../src/services/sessionLoader.js', () => ({
  loadSessions: vi.fn(() => []), renameSession: vi.fn(),
}));
vi.mock('../src/utils/conversationExport.js', () => ({
  exportConversation: vi.fn(() => ({ success: true, message: 'Synthetic export completed' })),
}));

const handlers = new Set<(key: Key) => void>();
const clipboard = vi.hoisted(() => ({
  copy: vi.fn().mockResolvedValue('native'),
  image: vi.fn().mockResolvedValue(null),
  text: vi.fn().mockResolvedValue(null),
}));
vi.mock('../src/utils/clipboard.js', async importOriginal => ({
  ...await importOriginal<typeof import('../src/utils/clipboard.js')>(),
  copySelectionToClipboard: clipboard.copy,
  getImageFromClipboard: clipboard.image,
  getTextFromClipboard: clipboard.text,
  readClipboardContent: async (includeImages: boolean) => {
    try {
      const image = includeImages ? await clipboard.image() : null;
      if (image) return { kind: 'image', image };
      const text = await clipboard.text();
      if (text) return { kind: 'text', text };
      throw new Error('empty clipboard');
    } catch {
      throw new Error('无法读取剪贴板，请使用终端粘贴。');
    }
  },
}));
let observedMessages: Message[] = [];
vi.mock('../src/hooks/useMemoryMonitor.js', () => ({
  useMemoryMonitor: (messages: Message[]) => { observedMessages = messages; },
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

const key = (name: string, extra: Partial<Key> = {}) => {
  const event: Key = { name, ctrl: false, cmd: false, alt: false, shift: false,
    insertable: false, sequence: '', ...extra };
  [...handlers].forEach(handler => handler(event));
};
const pause = (ms = 100) => new Promise(resolve => setTimeout(resolve, ms));

afterEach(() => {
  promptQueueStore.clear();
  inputRestoreStore.consume();
  vi.restoreAllMocks();
  clipboard.image.mockReset().mockResolvedValue(null);
  clipboard.text.mockReset().mockResolvedValue(null);
});

async function harness(rows = 24, columns = 80) {
  let adapter: SiadaACPAdapter;
  const sent = vi.spyOn(SiadaACPAdapter.prototype, 'sendMessage').mockResolvedValue(undefined);
  const interrupt = vi.spyOn(SiadaACPAdapter.prototype, 'interrupt').mockResolvedValue(undefined);
  vi.spyOn(SiadaACPAdapter.prototype, 'sendNotification').mockImplementation(() => {});
  vi.spyOn(SiadaACPAdapter.prototype, 'isAdapterReady').mockImplementation(function () {
    return (this as unknown as { isReady: boolean }).isReady;
  });
  vi.spyOn(SiadaACPAdapter.prototype, 'start').mockImplementation(function () {
    adapter = this;
    return new Promise<void>(resolve => {
      // Preserve the real startup boundary: banner_info resolves readiness,
      // then start() emits ready before connect() publishes the client.
      (this as unknown as { readyResolver: () => void }).readyResolver = () => {
        this.emit('ready');
        resolve();
      };
    });
  });
  const stdout = Object.assign(new PassThrough(), { rows, columns });
  const screen = new TerminalScreen(rows, columns);
  const onExit = vi.fn();
  let frame = '';
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  const app = render(<App config={{ workingDir: '.', model: 'synthetic' } as ClientConfig} onExit={onExit} />, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  await vi.waitFor(() => expect(adapter).toBeDefined());
  await pause();
  const update = (params: Record<string, unknown>) =>
    (adapter as unknown as { handleACPSessionUpdate: (data: unknown) => void }).handleACPSessionUpdate({ params });
  const lifecycle = (params: Record<string, unknown>) => update({ reason: 'lifecycle_event', ...params });
  update({ reason: 'banner_info', content: JSON.stringify({
    version: 'synthetic', working_dir: '.', agent: 'coder', provider: 'synthetic',
    model: 'synthetic', session_id: 'synthetic-three-pane-acp',
  }) });
  await vi.waitFor(() => expect(frame).toContain('输入消息'));
  const keyboard = (name: string, extra: Partial<Key> = {}) => {
    if (!app.getSelection().isCollapsed) {
      if ((extra.ctrl || extra.cmd) && name === 'c') name = 'selectioncopy';
      if (name === 'escape') name = 'selectionclear';
    }
    key(name, extra);
  };
  const selectText = async (text: string, cells: number) => {
    const lines = frame.split('\n');
    const row = lines.findLastIndex(line => line.includes(text));
    expect(row, frame).toBeGreaterThanOrEqual(0);
    const x = lines[row].indexOf(text) + 1;
    keyboard('mouseclick', { sequence: `\x1b[<0;${x};${row + 1}M` });
    keyboard('mousemove', { sequence: `\x1b[<32;${x + cells};${row + 1}M` });
    await pause();
    expect(app.getSelection().isCollapsed).toBe(false);
    keyboard('mouserelease', { sequence: `\x1b[<0;${x + cells};${row + 1}m` });
    await pause();
  };
  return { adapter, app, sent, interrupt, onExit, update, lifecycle, screen, keyboard, selectText,
    get frame() { return frame; },
    get messages() { return observedMessages; },
    close() { app.unmount(); app.cleanup(); } };
}

describe('three-pane real App and ACP state', () => {
  it('exports through the real input and writes the rendered conversation without a backend request', async () => {
    const actual = await vi.importActual<typeof import('../src/utils/conversationExport.js')>(
      '../src/utils/conversationExport.js');
    vi.mocked(exportConversation).mockImplementationOnce(actual.exportConversation);
    const directory = mkdtempSync(join(tmpdir(), 'siada-export-app-'));
    const target = join(directory, 'conversation.txt');
    const test = await harness(43, 100);
    try {
      test.lifecycle({ type: 'tool_use',
        delta: 'Run the following command:\n```bash\nnpm test\n```\ntimeout:60s',
        is_final: true, chunk_index: 0 });
      await pause();
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'export-answer' });
      test.lifecycle({ type: 'content_delta', delta: '**Export regression passed.**',
        is_final: false, stream_start_id: 'export-answer' });
      await pause();
      test.lifecycle({ type: 'content_delta', delta: '',
        is_final: true, stream_end: true, stream_start_id: 'export-answer' });
      await pause();
      expect(test.messages.some(message => message.content.includes('Export regression passed.'))).toBe(true);
      const sentBefore = test.sent.mock.calls.length;
      test.keyboard('paste', { sequence: `/export ${target}`, insertable: true });
      await pause();
      test.keyboard('escape'); await pause();
      test.keyboard('return');
      await vi.waitFor(() => expect(test.messages.some(message =>
        message.content.includes(`Conversation exported to: ${target}`))).toBe(true));
      const text = readFileSync(target, 'utf8');
      expect(text).toContain('npm test');
      expect(text).toContain('Export regression passed.');
      expect(text).not.toContain('**Export regression passed.**');
      expect(text).not.toContain('Siada CLI Conversation Export');
      expect(test.sent.mock.calls).toHaveLength(sentBefore);
    } finally {
      test.close();
      rmSync(directory, { recursive: true, force: true });
    }
  });

  it('switches interface language locally, persists it, and closes the picker without interrupting', async () => {
    const persist = vi.spyOn(configManager, 'setLanguage').mockImplementation(() => {});
    const test = await harness(24, 100);
    try {
      setUiLanguage('en'); await pause();
      expect(test.frame).toContain('Type a message');
      const sentBefore = test.sent.mock.calls.length;
      test.keyboard('paste', { sequence: '/language', insertable: true }); await pause();
      test.keyboard('escape'); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('Interface language');
      test.keyboard('down'); await pause();
      test.keyboard('return'); await pause();
      expect(persist).toHaveBeenLastCalledWith('zh-CN');
      expect(test.frame).toContain('输入消息');
      expect(test.sent.mock.calls).toHaveLength(sentBefore);
      test.keyboard('paste', { sequence: '/language en', insertable: true }); await pause();
      test.keyboard('escape'); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('Type a message');
      expect(persist).toHaveBeenLastCalledWith('en');
      test.keyboard('paste', { sequence: '/language', insertable: true }); await pause();
      test.keyboard('escape'); await pause();
      test.keyboard('return'); await pause();
      test.keyboard('c', { ctrl: true }); await pause();
      expect(test.frame).toContain('Type a message');
      expect(test.interrupt).not.toHaveBeenCalled();
      expect(test.onExit).not.toHaveBeenCalled();
      expect(test.sent.mock.calls).toHaveLength(sentBefore);
    } finally { test.close(); }
  });

  it('preserves the latest check, replays records once and clears them on history replacement', async () => {
    const test = await harness(24, 100);
    const goal = { objective: 'Verify restored evidence', status: 'active', createdAt: '2026-01-01T00:00:00Z', turns: 1 };
    const result = { id: 'stable-check', achieved: false, outcome: 'not_achieved', continuing: true,
      objective: goal.objective, turns: 1, elapsedSeconds: 3, tokensUsed: 0,
      reason: 'Missing Windows evidence', nextAction: 'Run Windows checks' };
    const records = () => test.messages.filter(message => message.metadata?.subtype === 'goal_result');
    try {
      test.adapter.emit('context:goalState', { goal, verifying: false, result });
      await pause();
      expect(records()).toHaveLength(1);
      test.adapter.emit('context:goalState', { goal, verifying: true });
      await pause();
      test.keyboard('tab'); await pause(); test.keyboard('return'); await pause();
      expect(test.frame).toContain('Status: Verifying');
      expect(test.frame).toContain('Missing Windows evidence');
      expect(test.frame).toContain('Next action: Run Windows checks');
      test.keyboard('escape'); await pause();

      test.adapter.emit('ui:loadHistory', { messages: [{ role: 'user', content: 'Restored session' }] });
      await pause();
      expect(records()).toHaveLength(0);
      const snapshot = { goal, verifying: false, latestResult: result, results: [result] };
      test.adapter.emit('context:goalState', snapshot);
      await pause();
      test.adapter.emit('context:goalState', snapshot);
      await pause();
      expect(records()).toHaveLength(1);
      expect(records()[0].id).toBe('goal_result_stable-check');
      expect(test.frame).toContain('Continuing');
      test.adapter.emit('context:goalState', { goal: null, verifying: false, notice: 'Goal cleared.' });
      await pause();
      expect(records()).toHaveLength(1);
      expect(test.frame).not.toContain('› Goal');

      test.adapter.emit('ui:loadHistory', { messages: [{ role: 'user', content: 'Another session' }] });
      await pause();
      test.adapter.emit('context:goalState', { goal: null, verifying: false });
      await pause();
      expect(records()).toHaveLength(0);
      expect(test.frame).not.toContain('Verify restored evidence');
    } finally { test.close(); }
  });
  it('suggests line and full-input deletion after repeated backspace, then clears the hint', async () => {
    const test = await harness(24, 100);
    try {
      test.keyboard('paste', { sequence: 'A fairly long draft to delete', insertable: true });
      await pause();
      for (let index = 0; index < 5; index++) {
        test.keyboard('backspace');
        await pause(20);
      }
      await vi.waitFor(() => expect(test.frame).toContain('Ctrl+U 删除至行首 · Ctrl+D 清空输入'));
      test.keyboard('d', { ctrl: true });
      await vi.waitFor(() => expect(test.frame).toContain('输入消息'));
      expect(test.frame).toContain('Ctrl+U 删除至行首');
    } finally { test.close(); }
  });

  it('acknowledges a slow image paste before reading finishes and reports completion', async () => {
    let finishImage!: (image: { filePath: string; mediaType: string }) => void;
    clipboard.image.mockImplementationOnce(() => new Promise(resolve => { finishImage = resolve; }));
    const test = await harness(24, 100);
    try {
      test.keyboard('v', { ctrl: true });
      await vi.waitFor(() => expect(test.frame).toContain('正在读取剪贴板…'));
      expect(clipboard.image).toHaveBeenCalledOnce();
      finishImage({ filePath: '/tmp/synthetic-tip-image.png', mediaType: 'image/png' });
      await vi.waitFor(() => expect(test.frame).toContain('[Image #1]'));
      expect(test.frame).toContain('已添加图片');
      expect(clipboard.text).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('keeps the paste notice through image fallback and reports clipboard errors', async () => {
    let finishText!: (text: string) => void;
    clipboard.text.mockImplementationOnce(() => new Promise(resolve => { finishText = resolve; }));
    const test = await harness(24, 100);
    try {
      test.keyboard('v', { ctrl: true });
      await vi.waitFor(() => expect(clipboard.text).toHaveBeenCalledOnce());
      expect(test.frame).toContain('正在读取剪贴板…');
      finishText('synthetic pasted text');
      await vi.waitFor(() => expect(test.frame).toContain('已粘贴文字'));
      expect(test.frame).toContain('synthetic pasted text');

      clipboard.image.mockRejectedValueOnce(new Error('synthetic failure'));
      test.keyboard('paste', { sequence: '' });
      await vi.waitFor(() => expect(test.frame).toContain('无法读取剪贴板'));
    } finally { test.close(); }
  });

  it('forwards every registered backend slash command and a custom skill through the real input', async () => {
    const source = readFileSync(new URL('../../siada/support/slash_commands.py', import.meta.url), 'utf8');
    const commands = [...source.matchAll(/^    def cmd_(\w+)\(/gm)].map(match => '/' + match[1].replaceAll('_', '-'));
    expect(commands.length).toBeGreaterThan(40);
    const test = await harness(43, 100);
    try {
      for (const command of [...commands, '/synthetic-skill']) {
        test.keyboard('paste', { sequence: command, insertable: true }); await pause(40);
        // Completion may appear before Enter on a busy parallel test run.
        test.keyboard('escape');
        await pause(80);
        test.keyboard('return'); await pause(40);
        if (command === '/export') expect(exportConversation).toHaveBeenCalled();
        else if (command === '/btw') expect(test.frame).toContain('用法：/btw');
        else if (command === '/editor' || command === '/statusbar' || command === '/status') {
          expect(test.frame).toContain(command === '/editor' ? '选择编辑器' : command === '/statusbar' ? '状态栏显示项' : '当前会话状态');
          test.keyboard('escape'); await pause(40);
          test.keyboard('d', { ctrl: true }); await pause(40);
        }
        else await vi.waitFor(() => expect(test.sent, command).toHaveBeenLastCalledWith(expect.objectContaining({
          method: 'agent/execute', params: { prompt: command },
        })));
      }
    } finally { test.close(); }
  }, 20000);

  it.each([20, 24, 43])('keeps history and draft mounted for all backend pickers at %s rows', async rows => {
    const test = await harness(rows, 100);
    try {
      test.adapter.emit('ui:loadHistory', { messages: [
        { role: 'user', content: 'Persistent picker question' },
        { role: 'agent', content: 'Persistent picker answer', subtype: 'answer' },
      ] });
      await pause();
      test.keyboard('paste', { sequence: 'Persistent picker draft', insertable: true }); await pause();
      const cases = [
        ['ui:showModelSelector', { models: Array.from({ length: 20 }, (_, i) => `model-${i}`), currentModel: 'model-0' }, '切换模型', 'down', '/model model-1'],
        ['ui:showEffortSelector', { model: 'synthetic', efforts: ['low', 'medium', 'high'], current: 'medium' }, '推理强度', 'left', '/effort low'],
        ['ui:showThemeSelector', { themes: ['dark', 'light'], current: 'dark' }, '切换主题', 'down', '/theme light'],
        ['ui:showTaskSelector', { tasks: [{ id: 'task-1', title: 'Original task', description: 'Synthetic task body',
          category: 'test', priority: 'low', confidence: 0.9 }] }, '待处理任务', '', 'Synthetic task body'],
      ] as const;
      for (const [event, data, title, move, expected] of cases) {
        test.adapter.emit(event, data); await pause();
        expect(test.frame).toContain('Persistent picker question');
        expect(test.frame).toContain(title);
        expect(test.frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
        if (move) { test.keyboard(move); await pause(); }
        test.keyboard('return'); await pause();
        expect(test.sent.mock.calls.at(-1)?.[0]).toMatchObject({ method: 'agent/execute' });
        expect(test.sent.mock.calls.at(-1)?.[0].params.prompt).toContain(expected);
        expect(test.frame).toContain('Persistent picker draft');
        expect(test.messages.filter(message => message.content === 'Persistent picker question')).toHaveLength(1);
      }
      expect(test.messages.findLast(message => message.type === 'user')?.content).toContain('**Original task**');
      // Task submission adds a turn; the visible history can retain either question.
      const questionHeaders = test.messages.filter(message => message.type === 'user')
        .map(message => message.content.split('\n')[0]);
      test.adapter.emit('ui:showPluginManager', { installed: [], discover: [], marketplaces: [], errors: [] });
      await pause(); expect(test.frame).toContain('发现');
      expect(questionHeaders.some(header => test.frame.includes(header))).toBe(true);
      test.keyboard('c', { ctrl: true }); await pause();
      expect(test.frame).toContain('Persistent picker draft');
      expect(test.interrupt).not.toHaveBeenCalled();
      test.adapter.emit('ui:showSessionBrowser'); await pause();
      expect(questionHeaders.some(header => test.frame.includes(header))).toBe(true);
      test.keyboard('escape'); await pause();
      expect(test.frame).toContain('Persistent picker draft');
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
    } finally { test.close(); }
  }, 12000);

  it('opens original editor and statusbar settings below history and preserves their actions', async () => {
    const preference = vi.spyOn(configManager, 'setPreferredEditor').mockImplementation(() => {});
    const toggle = vi.spyOn(configManager, 'setStatusbarItems').mockImplementation(() => {});
    const test = await harness(24, 100);
    try {
      test.adapter.emit('ui:loadHistory', { messages: [{ role: 'user', content: 'Settings stay below this question' }] });
      await pause();
      test.keyboard('paste', { sequence: '/editor', insertable: true }); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('选择编辑器');
      expect(test.frame).toContain('Settings stay below this question');
      test.keyboard('return'); await pause();
      expect(preference).toHaveBeenCalled();
      test.keyboard('escape'); await pause();
      test.keyboard('d', { ctrl: true }); await pause();
      test.keyboard('paste', { sequence: '/statusbar', insertable: true }); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('状态栏显示项');
      expect(test.frame).toContain('Settings stay below this question');
      for (let i = 0; i < 11; i++) { test.keyboard('down'); await pause(15); }
      await pause(); expect(test.frame).toContain('68,284');
      test.keyboard('space'); await pause(); expect(toggle).toHaveBeenCalled();
      test.keyboard('escape'); await pause();
      expect(test.frame).toContain('/statusbar');
      expect(test.frame).not.toMatch(/^\s*状态栏显示项\s*$/m);
      test.keyboard('d', { ctrl: true }); await pause();
      test.keyboard('paste', { sequence: '/status', insertable: true }); await pause(200);
      test.keyboard('down'); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('/statusbar');
      expect(test.frame).not.toMatch(/^\s*当前会话状态\s*$/m);
      test.keyboard('d', { ctrl: true }); await pause();
      test.keyboard('paste', { sequence: '/status', insertable: true }); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('当前会话状态');
      expect(test.frame).toContain('synthetic-three-pane-acp');
      expect(test.frame).toContain('Settings stay below this question');
      expect(test.messages.filter(m => m.content === '/status')).toHaveLength(0);
      test.keyboard('escape'); await pause();
      expect(test.frame).not.toMatch(/^\s*当前会话状态\s*$/m);
    } finally { test.close(); }
  });

  it('opens effort settings while busy and preserves the queue through selection and send failure', async () => {
    const test = await harness(24, 100);
    try {
      test.lifecycle({ type: 'processing_started', animation_control: 'start' });
      await pause();
      test.keyboard('paste', { sequence: 'Continue the queued task', insertable: true }); await pause();
      test.keyboard('return'); await pause();
      const queued = promptQueueStore.getSnapshot();
      expect(queued).toHaveLength(1);
      const notifications = vi.spyOn(SiadaACPAdapter.prototype, 'sendNotification');
      notifications.mockClear();
      const sentBefore = test.sent.mock.calls.length;
      test.sent.mockImplementation(async request => {
        if (request.params?.prompt === '/effort') {
          test.adapter.emit('ui:showEffortSelector', {
            model: 'synthetic', efforts: ['low', 'medium', 'high'], current: 'medium',
          });
        }
      });
      test.keyboard('paste', { sequence: '/effort', insertable: true }); await pause();
      test.keyboard('return'); await pause();
      expect(test.sent.mock.calls).toHaveLength(sentBefore + 1);
      expect(test.sent).toHaveBeenLastCalledWith(expect.objectContaining({
        method: 'agent/execute', params: { prompt: '/effort' },
      }));
      expect(test.frame).toContain('推理强度');
      expect(promptQueueStore.getSnapshot()).toEqual(queued);
      expect(test.messages.filter(message => message.content === '/effort')).toHaveLength(0);
      expect(notifications).not.toHaveBeenCalledWith('session/pullHistory', expect.anything());
      test.keyboard('left'); await pause();
      test.keyboard('return'); await pause();
      expect(test.sent).toHaveBeenLastCalledWith(expect.objectContaining({
        method: 'agent/execute', params: { prompt: '/effort low' },
      }));
      expect(promptQueueStore.getSnapshot()).toEqual(queued);
      expect(test.frame).toContain('可输入下一条消息');

      test.sent.mockRejectedValueOnce(new Error('synthetic effort failure'));
      test.keyboard('paste', { sequence: '/effort high', insertable: true }); await pause();
      test.keyboard('return'); await pause();
      expect(test.frame).toContain('Failed to send command: synthetic effort failure');
      expect(promptQueueStore.getSnapshot()).toEqual(queued);
      expect(test.frame).toContain('可输入下一条消息');
      expect(test.interrupt).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('removes completion state and its notice when the next chat clears the Goal', async () => {
    const test = await harness(24, 100);
    const result = { id: 'completed-before-next-chat', achieved: true, outcome: 'achieved',
      objective: 'Complete the synthetic Goal', reason: 'All checks passed.',
      turns: 2, elapsedSeconds: 62, tokensUsed: 0 };
    try {
      test.adapter.emit('context:goalState', {
        goal: { objective: result.objective, status: 'complete', turns: 2, elapsedSeconds: 62 },
        verifying: false, result, notice: 'Goal reached: Complete the synthetic Goal',
      });
      await pause();
      expect(test.frame).toContain('Achieved (complete · 1m 2s · 2 turns)');
      const sentBefore = test.sent.mock.calls.length;
      test.keyboard('paste', { sequence: 'Discuss another topic', insertable: true });
      await pause();
      test.keyboard('return');
      await pause();
      expect(test.sent.mock.calls.length).toBeGreaterThan(sentBefore);
      test.adapter.emit('context:goalState', { goal: null, verifying: false });
      await pause();
      expect(test.frame).not.toContain('› Goal');
      expect(test.frame).not.toContain('Goal reached:');
      expect(test.messages.filter(message => message.metadata?.subtype === 'goal_result')).toHaveLength(1);
      test.adapter.emit('context:goalState', { goal: null, verifying: false, notice: 'Goal cleared.' });
      await pause();
      expect(test.frame).toContain('Goal cleared.');
    } finally { test.close(); }
  });

  it('archives plan and goal completion and opens the correct same-name agent detail', async () => {
    const test = await harness(43, 100);
    try {
      test.adapter.emit('context:todoState', { todos: [{ content: 'Production task', status: 'in_progress' }] });
      test.adapter.emit('context:goalState', { goal: { objective: 'Production goal', status: 'active', createdAt: '', turns: 0 }, verifying: false });
      test.adapter.emit('context:subAgentState', { items: [
        { id: 'first', title: 'Same name', status: 'failed' },
        { id: 'second', title: 'Same name', status: 'cancelled' },
      ] });
      test.adapter.emit('context:subAgentMessage', { id: 'second', entry: { id: 'second-result', kind: 'message', text: 'Correct second agent detail' } });
      await pause(); expect(test.frame).toContain('Production task');
      test.lifecycle({ type: 'tool_use', delta: '◐  Production task\n○  Later task\n\n[0/2 completed]', is_final: true, chunk_index: 0 });
      await pause();
      expect(test.frame).not.toContain('Todo List');
      expect(test.frame).not.toContain('0/2 completed');
      test.lifecycle({ type: 'tool_use', delta: '✓  Production task\n\n[1/1 completed]', is_final: true, chunk_index: 0 });
      test.adapter.emit('context:todoState', { todos: [{ content: 'Production task', status: 'completed' }] });
      const completedGoal = { goal: { objective: 'Production goal', status: 'complete', turns: 1 }, verifying: false,
        result: { achieved: true, reason: 'Production goal done', turns: 1, objective: 'Production goal', elapsedSeconds: 3, tokensUsed: 0 } };
      test.adapter.emit('context:goalState', completedGoal);
      await pause();
      test.adapter.emit('context:goalState', JSON.parse(JSON.stringify(completedGoal)));
      await pause();
      expect(test.frame).toContain('Plan completed (1/1)');
      expect(test.frame).not.toContain('› Todo');
      expect(test.frame.split('\n').find(line => line.includes('› Goal')))
        .toContain('Achieved (complete · 3s · 1 turn)');
      expect(test.messages.filter(message => message.metadata?.subtype === 'goal_result')).toHaveLength(1);
      expect(test.frame).toContain('Goal Achieved');
      test.keyboard('tab'); await pause(); test.keyboard('return'); await pause();
      expect(test.frame).toContain('Goal · Objective and verification');
      expect(test.frame).toContain('Status: Achieved');
      test.keyboard('escape'); await pause();
      test.keyboard('tab'); await pause();
      test.keyboard('tab'); await pause(); test.keyboard('return'); await pause();
      expect(test.frame).toContain('Agents · 子智能体');
      test.keyboard('down'); await pause(); test.keyboard('return'); await pause();
      expect(test.frame).toContain('Correct second agent detail');
      test.keyboard('escape'); await pause(); test.keyboard('escape'); await pause();
      expect(test.frame).toContain('输入消息');
      test.adapter.emit('context:goalState', { goal: null, verifying: false, notice: 'Goal cleared.' });
      await pause();
      expect(test.frame).toContain('Goal cleared.');
      expect(test.frame).not.toContain('› Goal');
    } finally { test.close(); }
  });
  it('keeps the last plugin and marketplace visible in the embedded manager', async () => {
    const test = await harness(24, 100);
    try {
      test.adapter.emit('ui:showPluginManager', {
        installed: Array.from({ length: 12 }, (_, i) => ({ name: `skill-${i}`, description: 'Synthetic skill',
          scope: 'user', path: `synthetic/skill-${i}` })),
        discover: [], errors: [],
        marketplaces: Array.from({ length: 12 }, (_, i) => ({ name: `market-${i}`, repo: `synthetic/market-${i}`,
          available: 1, installed: 0 })),
      });
      await pause(); test.keyboard('right'); await pause();
      for (let i = 0; i < 11; i++) { test.keyboard('down'); await pause(20); }
      await pause(); expect(test.frame).toContain('skill-11');
      test.keyboard('right'); await pause();
      for (let i = 0; i < 12; i++) { test.keyboard('down'); await pause(20); }
      await pause(); expect(test.frame).toContain('market-11');
      expect(test.frame.split('\n').length).toBeLessThanOrEqual(23);
      test.keyboard('escape'); await pause(); expect(test.frame).toContain('输入消息');
    } finally { test.close(); }
  });
  it.each([false, true])('copies the real App draft and status without interrupting, interactive=%s', async interactive => {
    clipboard.copy.mockClear();
    clipboard.copy.mockResolvedValue('native');
    const test = await harness(43);
    try {
      if (interactive) {
        test.update({ reason: 'interactive_input_request', content: 'Synthetic confirmation',
          metadata: { inputType: 'confirmation', isPassword: false } });
        await pause();
        expect(test.frame).toContain('需要你输入');
      }
      test.keyboard('paste', { sequence: 'Draft 中文 input', insertable: true });
      await pause();
      await test.selectText('中文', 4);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('中文');
      test.keyboard('c', { ctrl: true });
      await pause();
      expect(test.frame).toContain('Draft 中文 input');
      expect(test.app.getSelection().isCollapsed).toBe(true);

      await test.selectText('synthetic', 9);
      expect(clipboard.copy.mock.calls.at(-1)?.[0]).toBe('synthetic');
      test.keyboard('c', { ctrl: true });
      await pause();
      expect(test.interrupt).not.toHaveBeenCalled();
      expect(test.onExit).not.toHaveBeenCalled();
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      if (interactive) expect(test.frame).toContain('需要你输入');
      test.keyboard('return');
      await pause();
      expect(test.sent).toHaveBeenCalledWith(expect.objectContaining({
        method: 'agent/execute', params: { prompt: 'Draft 中文 input' },
      }));
    } finally { test.close(); }
  });

  it.each([20, 24, 43])('renders restored history and recovers from a runtime error at %i rows', async rows => {
    const test = await harness(rows);
    try {
      test.adapter.emit('ui:loadHistory', { messages: [
        { role: 'user', content: 'Restored question' },
        { role: 'agent', content: 'Reasoning body', subtype: 'thinking' },
        { role: 'agent', content: 'Read the file `src/first.ts`', subtype: 'tool_use' },
        { role: 'agent', content: 'Read the file `src/second.ts`', subtype: 'tool_use' },
        { role: 'agent', content: 'Restored answer', subtype: 'answer' },
      ] });
      await pause();
      key('end', { ctrl: true }); await pause();
      expect(test.screen.display()).toContain('Restored answer');
      expect(test.frame).toContain('Read 2 files');
      expect(test.frame).toContain('● Reasoning body');
      test.lifecycle({ type: 'task_start', category: 'slash_command', command: '/synthetic', task_id: 'error-command' });
      test.lifecycle({ type: 'task_error', command: '/synthetic', error: 'Recoverable command error',
        error_type: 'synthetic' });
      await pause();
      expect(test.frame).toContain('Recoverable command error');
      expect(test.frame).toContain('输入消息');
      expect(test.frame).not.toContain('启动失败');
      key('paste', { sequence: 'Continue after error', insertable: true }); await pause();
      key('return'); await pause();
      expect(test.sent).toHaveBeenCalledWith(expect.objectContaining({
        method: 'agent/execute', params: { prompt: 'Continue after error' },
      }));
      expect(test.frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
    } finally { test.close(); }
  });

  it('updates a long answer and an unfinished code block before the stream finishes', async () => {
    const test = await harness(24);
    try {
      test.lifecycle({ type: 'processing_started', animation_control: 'start' });
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'long-answer' });
      test.lifecycle({ type: 'content_delta', delta: 'Intro\n', is_final: false, stream_start_id: 'long-answer' });
      const longContent = Array.from({ length: 70 }, (_, index) => `line ${index + 1}`).join('\n');
      test.lifecycle({ type: 'content_delta', delta: longContent, is_final: false, stream_start_id: 'long-answer' });
      await pause();
      key('end', { ctrl: true }); await pause();
      expect(test.frame).toContain('line 70');
      test.lifecycle({ type: 'content_delta', delta: '\n```ts\nconst streamingCode = true;\n',
        is_final: false, stream_start_id: 'long-answer' });
      await pause();
      expect(test.screen.display()).toContain('streamingCode');
      expect(test.frame).toContain('可输入下一条消息');
      expect(test.frame.split('\n').length).toBeLessThanOrEqual(23);
      test.lifecycle({ type: 'content_delta', delta: '', is_final: true, stream_end: true, stream_start_id: 'long-answer' });
      test.lifecycle({ type: 'message_end', message_id: 'long-answer', message_type: 'answer' });
      test.lifecycle({ type: 'input_ready', animation_control: 'stop' });
      await pause();
      expect(test.frame).toContain('streamingCode');
      expect(test.frame).toContain('输入消息');
    } finally { test.close(); }
  });

  it('finishes Thought on message_end and keeps two consecutive reasoning streams separate', async () => {
    const test = await harness(43);
    try {
      test.lifecycle({ type: 'processing_started', animation_control: 'start' });
      test.lifecycle({ type: 'message_start', message_type: 'thinking', message_id: 'reasoning-first' });
      test.lifecycle({ type: 'content_delta', delta: 'First reasoning', is_final: false,
        stream_start_id: 'reasoning-first' });
      test.lifecycle({ type: 'content_delta', delta: ' last token.', is_final: false,
        stream_start_id: 'reasoning-first' });
      // Python ends reasoning without a final content_delta before starting its answer.
      test.lifecycle({ type: 'message_end', message_type: 'thinking', message_id: 'reasoning-first' });
      await pause();
      expect(test.frame).toContain('● First reasoning');
      expect(test.messages.filter(message => message.metadata?.subtype === 'thinking'))
        .toMatchObject([{ content: 'First reasoning last token.', metadata: { streamEnd: true, isStreaming: false } }]);

      test.lifecycle({ type: 'message_start', message_type: 'thinking', message_id: 'reasoning-second' });
      test.lifecycle({ type: 'content_delta', delta: 'Second reasoning.', is_final: false,
        stream_start_id: 'reasoning-second' });
      test.lifecycle({ type: 'message_end', message_type: 'thinking', message_id: 'reasoning-second' });
      await pause();
      expect(test.messages.filter(message => message.metadata?.subtype === 'thinking').map(message => message.content))
        .toEqual(['First reasoning last token.', 'Second reasoning.']);
    } finally { test.close(); }
  });

  it.each([false, true])('retains the last answer delta exactly once with message_end=%s', async messageEnd => {
    const test = await harness();
    try {
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'final-answer' });
      test.lifecycle({ type: 'content_delta', delta: 'First part. ', is_final: false,
        stream_start_id: 'final-answer' });
      test.lifecycle({ type: 'content_delta', delta: 'Final token.', is_final: true, stream_end: true,
        stream_start_id: 'final-answer' });
      if (messageEnd) test.lifecycle({ type: 'message_end', message_type: 'answer', message_id: 'final-answer' });
      test.lifecycle({ type: 'input_ready', animation_control: 'stop' });
      await pause();
      const answers = test.messages.filter(message => message.metadata?.subtype === 'answer');
      expect(answers).toHaveLength(1);
      expect(answers[0]).toMatchObject({
        content: 'First part. Final token.', metadata: { streamEnd: true, isStreaming: false },
      });
    } finally { test.close(); }
  });

  it('accepts an empty final delta and a complete answer contained in its first delta', async () => {
    const test = await harness();
    try {
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'empty-final' });
      test.lifecycle({ type: 'content_delta', delta: 'Complete body.', is_final: false,
        stream_start_id: 'empty-final' });
      test.lifecycle({ type: 'content_delta', delta: '', is_final: true, stream_end: true,
        stream_start_id: 'empty-final' });
      await pause();
      expect(test.messages.filter(message => message.metadata?.subtype === 'answer'))
        .toMatchObject([{ content: 'Complete body.', metadata: { streamEnd: true, isStreaming: false } }]);
      test.lifecycle({ type: 'message_end', message_type: 'answer', message_id: 'empty-final' });
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'one-shot-answer' });
      test.lifecycle({ type: 'content_delta', delta: 'Second complete answer.', is_final: true, stream_end: true,
        stream_start_id: 'one-shot-answer' });
      test.lifecycle({ type: 'message_end', message_type: 'answer', message_id: 'one-shot-answer' });
      await pause();
      expect(test.messages.filter(message => message.metadata?.subtype === 'answer').map(message => message.content))
        .toEqual(['Complete body.', 'Second complete answer.']);
    } finally { test.close(); }
  });

  it('ignores a delayed end for an older answer while the next answer is streaming', async () => {
    const test = await harness();
    try {
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'older-answer' });
      test.lifecycle({ type: 'content_delta', delta: 'Older answer.', is_final: false,
        stream_start_id: 'older-answer' });
      test.lifecycle({ type: 'message_end', message_type: 'answer', message_id: 'older-answer' });
      test.lifecycle({ type: 'message_start', message_type: 'answer', message_id: 'new-answer' });
      test.lifecycle({ type: 'content_delta', delta: 'New', is_final: false, stream_start_id: 'new-answer' });
      test.adapter.emit('stream:end', {
        messageId: 'older-answer', messageType: 'answer', totalContent: 'Older answer.',
      });
      test.lifecycle({ type: 'content_delta', delta: ' answer.', is_final: false, stream_start_id: 'new-answer' });
      await pause();
      const answers = test.messages.filter(message => message.metadata?.subtype === 'answer');
      expect(answers).toHaveLength(2);
      expect(answers[0]).toMatchObject({ content: 'Older answer.', metadata: { streamEnd: true } });
      expect(answers[1]).toMatchObject({ content: 'New answer.', metadata: { streamEnd: false, isStreaming: true } });
      test.lifecycle({ type: 'message_end', message_type: 'answer', message_id: 'new-answer' });
      await pause();
      expect(test.messages.filter(message => message.metadata?.subtype === 'answer')[1].metadata)
        .toMatchObject({ streamEnd: true, isStreaming: false });
    } finally { test.close(); }
  });

  it('preserves a legacy final snapshot without appending the whole response twice', async () => {
    const test = await harness();
    try {
      test.update({ reason: 'message_chunk', content: 'Legacy complete response.',
        metadata: { chunkType: 'answer', isStreaming: true, streamEnd: false } });
      test.update({ reason: 'message_chunk', content: 'Legacy complete response.',
        metadata: { chunkType: 'answer', isStreaming: false, streamEnd: true } });
      await pause();
      expect(test.messages.filter(message => message.metadata?.subtype === 'answer'))
        .toMatchObject([{ content: 'Legacy complete response.', metadata: { streamEnd: true, isStreaming: false } }]);
    } finally { test.close(); }
  });

  it('appends each ACP history batch once through the real App', async () => {
    const test = await harness(43);
    try {
      test.adapter.emit('ui:appendHistory', { messages: [
        { role: 'user', content: 'Appended question' },
        { role: 'agent', content: 'Appended answer', subtype: 'answer' },
      ] });
      await pause();
      expect(test.messages.map(message => message.content)).toEqual(['Appended question', 'Appended answer']);
    } finally { test.close(); }
  });

  it('expires the exit shortcut without leaving an active shortcut hint in history', async () => {
    const test = await harness();
    try {
      test.lifecycle({ type: 'processing_started', animation_control: 'start' });
      await pause();
      key('c', { ctrl: true, sequence: '\x03' });
      await pause();
      expect(test.frame).toContain('已停止 · 再按 Ctrl+C 退出');
      expect(test.messages.filter(message => message.type === 'system').map(message => message.content))
        .toEqual(['Execution interrupted']);
      await pause(1100);
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      expect(test.onExit).not.toHaveBeenCalled();
    } finally { test.close(); }
  });

  it('stops once and exits on the second press even when pending input is restored', async () => {
    const test = await harness();
    try {
      key('paste', { sequence: 'Unanswered prompt', insertable: true }); await pause();
      key('return'); await pause();
      test.lifecycle({ type: 'processing_started', animation_control: 'start' });
      await pause();
      key('c', { ctrl: true, sequence: '\x03' }); await pause();
      expect(test.interrupt).toHaveBeenCalledOnce();
      expect(test.onExit).not.toHaveBeenCalled();
      expect(test.frame).toContain('已停止 · 再按 Ctrl+C 退出');
      key('c', { ctrl: true, sequence: '\x03' }); await pause();
      expect(test.onExit).toHaveBeenCalledWith('synthetic-three-pane-acp');
      expect(test.interrupt).toHaveBeenCalledOnce();
    } finally { test.close(); }
  });

  it('lets an ACP model picker close without stopping or arming process exit', async () => {
    const test = await harness();
    try {
      test.adapter.emit('ui:showModelSelector', { models: ['synthetic'], currentModel: 'synthetic' });
      await pause();
      expect(test.frame).toContain('切换模型');
      key('c', { ctrl: true }); await pause();
      expect(test.frame).toContain('输入消息');
      expect(test.frame).not.toContain('再按 Ctrl+C 退出');
      expect(test.interrupt).not.toHaveBeenCalled();
      expect(test.onExit).not.toHaveBeenCalled();
    } finally { test.close(); }
  });
});