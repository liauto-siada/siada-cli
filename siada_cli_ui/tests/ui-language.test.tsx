import React from 'react';
import { PassThrough } from 'node:stream';
import { join } from 'node:path';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';

const storage = vi.hoisted(() => ({
  files: new Map<string, string>(),
  failWrites: false,
}));
vi.mock('os', async importOriginal => ({
  ...await importOriginal<typeof import('os')>(),
  homedir: () => '/synthetic/ui-language-home',
}));
vi.mock('fs', async importOriginal => ({
  ...await importOriginal<typeof import('fs')>(),
  existsSync: (path: string) => storage.files.has(String(path)),
  readFileSync: (path: string) => storage.files.get(String(path)) ?? '',
  mkdirSync: vi.fn(),
  writeFileSync: (path: string, contents: string) => {
    if (storage.failWrites) throw new Error('Synthetic storage failure');
    storage.files.set(String(path), contents);
  },
}));
vi.mock('../src/utils/logger.js', () => ({
  logger: { info: vi.fn(), debug: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));

import { getUiLanguage, saveUiLanguage, setUiLanguage, t } from '../src/i18n/index.js';
import { ConfigManager } from '../src/utils/config.js';
import { slashCommandService } from '../src/services/slashCommandService.js';
import { DemoCompletionList } from '../src/components/layouts/DemoCompletionList.js';
import { ModelSelector } from '../src/components/ModelSelector/ModelSelector.js';
import { INPUT_TIPS } from '../src/constants/tips.js';

afterEach(() => {
  storage.failWrites = false;
  storage.files.clear();
  setUiLanguage('en');
  slashCommandService.clear();
});

describe('UI language', () => {
  it('defaults to English independently of response-language preferences', async () => {
    expect(getUiLanguage()).toBe('en');
    expect(new ConfigManager().get('language')).toBeUndefined();
    expect(t('中文提示', 'English hint')).toBe('English hint');
    expect(INPUT_TIPS.textPasted).toBe('Text pasted');
    slashCommandService.updateCommandsFromBackend([{ name: 'btw', description: 'Original English description' }]);
    expect((await slashCommandService.getCommand('btw'))?.description).toBe('Original English description');
  });

  it('persists the selection and preserves unrelated UI settings across restart', () => {
    const path = join('/synthetic/ui-language-home', '.siada-cli', 'ui-config.json');
    storage.files.set(path, JSON.stringify({ theme: 'light', preferredEditor: 'vim' }));
    saveUiLanguage('zh-CN');
    expect(getUiLanguage()).toBe('zh-CN');
    expect(JSON.parse(storage.files.get(path)!)).toEqual({
      theme: 'light', preferredEditor: 'vim', language: 'zh-CN',
    });
    expect(new ConfigManager().get('language')).toBe('zh-CN');
    saveUiLanguage('en');
    expect(new ConfigManager().get('language')).toBe('en');
  });

  it('does not acknowledge a language change when persistence fails', () => {
    storage.failWrites = true;
    expect(() => saveUiLanguage('zh-CN')).toThrow('Synthetic storage failure');
    expect(getUiLanguage()).toBe('en');
  });

  it.each([48, 80, 120])('updates an open command list and selector in both directions at %i columns', async columns => {
    slashCommandService.updateCommandsFromBackend([
      { name: 'btw', description: 'Ask a quick side question' },
      { name: 'custom-skill', description: '外部技能说明保留原文' },
    ]);
    const commands = await slashCommandService.getCommands();
    const suggestions = commands.map(command => ({
      label: command.name, value: command.name, description: command.description, type: 'command' as const,
    }));
    let frame = '';
    const app = render(<>
      <DemoCompletionList suggestions={suggestions} activeIndex={0} width={columns} />
      <ModelSelector models={['example-model']} currentModel="example-model" embedded
        onSelect={() => {}} onExit={() => {}} />
    </>, {
      stdout: Object.assign(new PassThrough(), { columns, rows: 30 }),
      stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await vi.waitFor(() => expect(frame).toContain('Switch Model'));
      expect(frame).toContain('Suggestions');
      setUiLanguage('zh-CN');
      await vi.waitFor(() => expect(frame).toContain('切换模型'));
      expect(frame).toContain('临时提问');
      expect(frame).toContain('命令建议');
      expect(frame).toContain('外部技能说明保留原文');
      setUiLanguage('en');
      await vi.waitFor(() => expect(frame).toContain('Switch Model'));
      expect(frame).toContain('Ask a quick side');
      expect(frame).not.toContain('命令建议');
      expect(frame).not.toContain('切换模型');
      expect(frame).toContain('外部技能说明保留原文');
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});