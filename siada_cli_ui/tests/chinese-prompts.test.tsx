import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { readFileSync } from 'node:fs';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import stringWidth from 'string-width';
import { slashCommandService } from '../src/services/slashCommandService.js';
import { COMMAND_DESCRIPTIONS } from '../src/constants/commandDescriptions.js';
import { DemoCompletionList } from '../src/components/layouts/DemoCompletionList.js';
import { Banner } from '../src/components/Banner/Banner.js';
import type { Suggestion } from '../src/types/autocomplete.js';

vi.mock('../src/utils/logger.js', () => ({
  logger: { info: vi.fn(), debug: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

afterEach(() => slashCommandService.clear());

describe('Chinese terminal guidance', () => {
  it('keeps every built-in command description Chinese before and after ACP updates', async () => {
    const source = readFileSync(new URL('../../siada/support/slash_commands.py', import.meta.url), 'utf8');
    const names = [...source.matchAll(/^    def cmd_(\w+)\(/gm)]
      .map(match => match[1].replaceAll('_', '-'));
    for (const name of names) expect(COMMAND_DESCRIPTIONS[name], name).toMatch(/[\u4e00-\u9fff]/);
    for (const command of await slashCommandService.getCommands()) {
      expect(command.description).toMatch(/[\u4e00-\u9fff]/);
    }
    slashCommandService.updateCommandsFromBackend(names.map(name => ({
      name, description: 'Legacy English description', argument_hint: '<value>',
    })));
    for (const command of await slashCommandService.getCommands()) {
      expect(command.description).toMatch(/[\u4e00-\u9fff]/);
      if (command.name !== 'language') expect(command.argumentHint).toBe('<value>');
    }
  });

  it('preserves externally supplied command descriptions and names', async () => {
    slashCommandService.updateCommandsFromBackend([
      { name: 'custom-skill', description: 'External skill description', argument_hint: '<url>' },
      { name: 'configure', description: 'Reconfigure provider' },
    ]);
    expect(await slashCommandService.getCommand('custom-skill')).toMatchObject({
      name: 'custom-skill', description: 'External skill description', argumentHint: '<url>',
    });
    expect((await slashCommandService.getCommand('configure'))?.description).toContain('重新配置');
  });

  it.each([48, 80, 120])('renders Chinese command suggestions and banner within %i columns', async columns => {
    slashCommandService.updateCommandsFromBackend([
      { name: 'btw', description: 'Ask a quick side question without polluting main conversation' },
      { name: 'clear', description: 'Start a new task session' },
      { name: 'compact', description: 'Manually compact conversation history' },
      { name: 'compare', description: 'Compare files' },
      { name: 'configure', description: 'Reconfigure provider' },
    ]);
    const commands = await slashCommandService.getCommands();
    const suggestions = commands.map(command => ({
      label: command.name, value: '/' + command.name, description: command.description, type: 'command',
    })) as Suggestion[];
    let frame = '';
    const app = render(<>
      <Banner workingDir="/synthetic/中文目录" agent="coder" provider="example" model="example-model" />
      <DemoCompletionList suggestions={suggestions} activeIndex={0} width={columns} />
    </>, {
      stdout: Object.assign(new PassThrough(), { columns, rows: 30 }),
      stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
      onRender: ({ output }) => { frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
    });
    try {
      await vi.waitFor(() => expect(frame).toContain('命令建议'));
      expect(frame).toContain('临时提问');
      expect(frame).toContain('↑↓ 选择');
      expect(frame).not.toMatch(/Suggestions|Ask a quick|Start a new|Manually compact|Working Directory/);
      for (const line of frame.split('\n')) expect(stringWidth(line), line).toBeLessThanOrEqual(columns);
      expect(frame.split('\n').length).toBeLessThan(30);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });
});