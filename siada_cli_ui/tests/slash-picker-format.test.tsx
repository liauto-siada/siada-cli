import React, { useState } from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import stringWidth from 'string-width';
import { BottomPaneContext } from '../src/contexts/BottomPaneContext.js';
import { TerminalScreen } from './helpers/terminalScreen.js';
import type { Key } from '../src/hooks/useKeypress.js';

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
vi.mock('../src/utils/editor.js', () => ({
  EDITOR_DISPLAY_NAMES: { unavailable: 'Unavailable', vim: 'Vim', nano: 'Nano' },
  checkHasEditorType: (type: string) => type !== 'unavailable',
  getEditorDisplayName: (type: string) => type === 'vim' ? 'Vim' : 'Nano',
}));
vi.mock('../src/services/sessionLoader.js', () => ({
  loadSessions: () => Array.from({ length: 40 }, (_, i) => ({
    id: `s-${i}`, sessionId: `s-${i}`, index: i, firstUserMessage: `Session ${i} 中文\n${'long title '.repeat(12)}`,
    messageCount: 10, lastUpdated: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z`,
    startTime: '2026-01-01T00:00:00Z', isCurrentSession: false, projectRoot: '.',
    matchSnippets: ['first match', 'second match', 'third match'],
  })),
  renameSession: vi.fn(),
}));

import { ModelSelector } from '../src/components/ModelSelector/ModelSelector.js';
import { ThemeSelector } from '../src/components/ThemeSelector/ThemeSelector.js';
import { LanguageSelector } from '../src/components/LanguageSelector/LanguageSelector.js';
import { EditorDialog } from '../src/components/EditorDialog/EditorDialog.js';
import { StatusBarDialog } from '../src/components/StatusBarDialog/StatusBarDialog.js';
import { EffortSelector } from '../src/components/EffortSelector/EffortSelector.js';
import { TaskSelector, type TaskItem } from '../src/components/TaskSelector/TaskSelector.js';
import { PluginManager } from '../src/components/PluginManager/PluginManager.js';
import { SessionBrowser } from '../src/components/SessionBrowser/SessionBrowser.js';
import { LoginSelector } from '../src/components/Login/LoginSelector.js';
import { setUiLanguage } from '../src/i18n/index.js';
import { setActiveTheme } from '../src/themes/index.js';
import { PickerFrame, PickerRow, pickerHint } from '../src/components/Picker/Picker.js';

const pause = () => new Promise(resolve => setTimeout(resolve, 45));
function harness(content: React.ReactNode, rows = 12, columns = 80) {
  const stdout = Object.assign(new PassThrough(), { rows, columns });
  const screen = new TerminalScreen(rows, columns);
  let frame = '';
  stdout.on('data', chunk => screen.feed(chunk.toString()));
  const app = render(<BottomPaneContext.Provider value={{ rows, columns }}>{content}</BottomPaneContext.Provider>, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  return {
    get frame() { return frame; },
    screen,
    key(name: string, sequence = '') {
      const event: Key = { name, sequence, ctrl: false, cmd: false, alt: false, shift: false, insertable: !!sequence };
      [...handlers].forEach(handler => handler(event));
    },
    check(title: string) {
      expect(frame).toContain(title);
      expect(screen.display()).toContain(title);
      expect(frame.split('\n').length).toBeLessThanOrEqual(rows - 1);
      expect(frame.split('\n').every(line => stringWidth(line) <= columns)).toBe(true);
      expect(frame.split('\n')[0]).not.toMatch(/[┌┐└┘╭╮╰╯]/);
      const titleLine = frame.split('\n').find(line => line.includes(title))!;
      expect(titleLine.indexOf(title)).toBe(1);
    },
    close() { app.unmount(); app.cleanup(); },
  };
}
afterEach(() => { setUiLanguage('en'); setActiveTheme('dark'); });

const tasks: TaskItem[] = Array.from({ length: 40 }, (_, i) => ({
  id: `task-${i}`, title: `Task ${i} 中文\n${'long title '.repeat(15)}`, description: '中文 description '.repeat(80),
  priority: 'high', category: 'test', confidence: 0.9, needs_confirmation: false,
  status: 'pending', suggested_actions: [],
}));

describe('shared slash picker layout', () => {
  it.each([48, 80, 120])('keeps every picker within a 12-row pane at %i columns', async columns => {
    const noop = () => {};
    const cases: [string, React.ReactNode][] = [
      ['Switch Model', <ModelSelector embedded models={Array.from({ length: 40 }, (_, i) => `model-${i}`)}
        currentModel="model-20" onSelect={noop} onExit={noop} />],
      ['Switch Theme', <ThemeSelector themes={['dark', 'light']} current="dark" onSelect={noop} onExit={noop} />],
      ['Interface language', <LanguageSelector onSelect={noop} onClose={noop} />],
      ['Editor Selection', <EditorDialog currentEditor="vim" onSelect={noop} onCancel={noop} />],
      ['Status Bar Items', <StatusBarDialog visibleItems={['model']} onToggle={noop} onClose={noop} />],
      ['Reasoning Effort', <EffortSelector embedded model="model" efforts={['low', 'medium', 'high', 'xhigh', 'max']}
        current="medium" onSelect={noop} onExit={noop} />],
      ['Pending Tasks', <TaskSelector tasks={tasks} onSelect={noop} onExit={noop} />],
      ['Resume Session', <SessionBrowser projectRoot="." onResume={async () => {}} onExit={noop} />],
      ['Sign In', <LoginSelector cancelable onSelect={noop} />],
      ['Plugins', <PluginManager data={{ installed: [], discover: tasks.map(task => ({
        name: task.id, description: task.description, marketplace: 'test', marketplaceName: 'Test', installed: false,
      })), errors: [], marketplaces: [] }} onAction={noop} onExit={noop} />],
    ];
    for (const theme of ['dark', 'light'] as const) {
      setActiveTheme(theme);
      for (const [title, component] of cases) {
        const test = harness(component, 12, columns);
        try { await pause(); test.check(title); } finally { test.close(); }
      }
    }
  });

  it('keeps saved model separate from focus and selects the last row after scrolling', async () => {
    const select = vi.fn(), exit = vi.fn();
    const test = harness(<ModelSelector embedded models={Array.from({ length: 40 }, (_, i) => `model-${i}`)}
      currentModel="model-0" onSelect={select} onExit={exit} />);
    try {
      await pause();
      expect(test.frame).toContain('› model-0 (current)');
      test.key('down'); await pause();
      expect(test.frame).toContain('› model-1');
      expect(test.frame).toContain('model-0 (current)');
      for (let i = 0; i < 40; i++) { test.key('down'); await pause(); }
      test.check('Switch Model');
      expect(test.screen.display()).toContain('› model-39');
      expect(test.screen.display()).toContain('Enter confirm');
      test.key('return'); test.key('escape');
      expect(select).toHaveBeenCalledWith('model-39');
      expect(exit).toHaveBeenCalledOnce();
    } finally { test.close(); }
  });

  it('skips unavailable editors and marks the saved editor independently', async () => {
    const select = vi.fn();
    const test = harness(<EditorDialog currentEditor="not_set" onSelect={select} onCancel={() => {}} />);
    try {
      await pause(); test.key('down'); await pause();
      expect(test.frame).toContain('› Vim');
      expect(test.frame).toContain('None (current)');
      test.key('return');
      expect(select).toHaveBeenCalledWith('vim');
    } finally { test.close(); }
  });

  it('toggles multiple status items in place with Space and Enter', async () => {
    const toggle = vi.fn();
    function Status() {
      const [items, setItems] = useState(['model']);
      return <StatusBarDialog visibleItems={items} onClose={() => {}} onToggle={item => {
        toggle(item); setItems(previous => previous.includes(item) ? previous.filter(value => value !== item) : [...previous, item]);
      }} />;
    }
    const test = harness(<Status />);
    try {
      await pause(); expect(test.frame).toContain('› [x] Model');
      test.key('space'); await pause(); expect(test.frame).toContain('› [ ] Model');
      test.key('down'); await pause(); test.key('return'); await pause();
      expect(test.frame).toContain('› [x] Balance');
      expect(toggle.mock.calls.map(call => call[0])).toEqual(['model', 'balance']);
      test.check('Status Bar Items');
    } finally { test.close(); }
  });

  it('uses only horizontal navigation for effort and preserves the saved value until confirm', async () => {
    const select = vi.fn();
    const test = harness(<EffortSelector model="model" efforts={['low', 'medium', 'high']} current="medium"
      onSelect={select} onExit={() => {}} />);
    try {
      await pause(); const original = test.frame;
      test.key('down'); await pause(); expect(select).not.toHaveBeenCalled();
      test.key('right'); await pause();
      expect(test.frame).toContain('Current: medium');
      expect(test.frame).not.toBe(original);
      test.key('return'); expect(select).toHaveBeenCalledWith('high');
      expect(test.frame).toContain('←→ select');
    } finally { test.close(); }
  });

  it('renders a max-only effort selector and cannot navigate to another level', async () => {
    const select = vi.fn();
    const test = harness(<EffortSelector model="example-kimi-k3" efforts={['max']} current="max"
      onSelect={select} onExit={() => {}} />);
    try {
      await pause();
      test.key('left'); test.key('right'); await pause();
      expect(test.frame).toContain('max');
      expect(test.frame).not.toMatch(/\b(low|medium|high|xhigh)\b/);
      test.key('return');
      expect(select).toHaveBeenCalledWith('max');
    } finally { test.close(); }
  });

  it('keeps the session search title, active row and cancel hint visible with snippets', async () => {
    const exit = vi.fn(), resume = vi.fn().mockResolvedValue(undefined);
    const test = harness(<SessionBrowser projectRoot="." onResume={resume} onExit={exit} />);
    try {
      await pause(); test.key('/', '/'); await pause();
      test.check('Resume Session');
      expect(test.screen.display()).toContain('Enter confirm');
      expect(test.frame).toContain('› Session');
      test.key('escape'); await pause(); expect(exit).not.toHaveBeenCalled();
      test.key('return'); await pause(); expect(resume).toHaveBeenCalledOnce();
      test.key('escape'); expect(exit).toHaveBeenCalledOnce();
    } finally { test.close(); }
  });

  it('windows provider/model choices and returns to the previous wizard step', async () => {
    const select = vi.fn();
    const test = harness(<LoginSelector cancelable liidDisabled onSelect={select}
      providers={Array.from({ length: 40 }, (_, i) => ({
        id: `p-${i}`, name: `Provider ${i}`, baseUrl: 'https://example.com', apiKeyHint: '',
        models: [{ id: `model-${i}`, name: 'Model', context: 10 }],
      }))} />);
    try {
      await pause(); test.key('return'); await pause();
      for (let i = 0; i < 39; i++) { test.key('down'); await pause(); }
      expect(test.screen.display()).toContain('› Provider 39');
      test.check('Configure API Key');
      test.key('return'); await pause(); expect(test.frame).toContain('› model-39');
      test.key('escape'); await pause(); expect(test.frame).toContain('› Provider 39');
      test.key('escape'); await pause(); test.key('escape');
      expect(select).toHaveBeenCalledWith('cancel');
    } finally { test.close(); }
  });

  it('keeps grouped installed plugins and marketplace focus inside the pane', async () => {
    const action = vi.fn();
    const test = harness(<PluginManager data={{ errors: [], discover: [], installed: tasks.map(task => ({
      name: task.id, description: task.description, scope: 'user', path: '.', plugin_name: 'Grouped',
    })), marketplaces: tasks.map(task => ({ name: task.id, repo: 'test/repo', installed: 1, available: 2 })) }}
      onAction={action} onExit={() => {}} />);
    try {
      await pause(); test.key('tab'); await pause();
      for (let i = 0; i < 39; i++) { test.key('down'); await pause(); }
      test.check('Plugins'); expect(test.screen.display()).toContain('› [x] task-39');
      test.key('d', 'd'); expect(action).toHaveBeenCalledWith('/plugin disable task-39');
      test.key('tab'); await pause();
      for (let i = 0; i < 40; i++) { test.key('down'); await pause(); }
      test.check('Plugins'); expect(test.screen.display()).toContain('› task-39');
      test.key('u', 'u'); expect(action).toHaveBeenCalledWith('/plugin marketplace update task-39');
    } finally { test.close(); }
  });

  it('updates the common chrome when interface language and theme change', async () => {
    const test = harness(<ThemeSelector themes={['dark', 'light']} current="dark" onSelect={() => {}} onExit={() => {}} />);
    try {
      await pause(); setUiLanguage('zh-CN'); setActiveTheme('light'); await pause();
      test.check('切换主题'); expect(test.frame).toContain('Enter 确定');
    } finally { test.close(); }
  });

  it('does not let multiline values increase a picker row height', async () => {
    const test = harness(<PickerFrame title={'Title\ncontinued'} summary={'Summary\ncontinued'} hint={pickerHint('vertical')}>
      <PickerRow active>Value{'\nsecond line'}</PickerRow>
    </PickerFrame>);
    try {
      await pause(); expect(test.frame).toContain('Title continued');
      expect(test.frame).toContain('› Value second line'); test.check('Title');
    } finally { test.close(); }
  });
});