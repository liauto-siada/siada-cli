import { describe, expect, it } from 'vitest';

import { SlashCommandService } from '../src/services/slashCommandService.js';
import { renderBannerBlock } from '../src/utils/conversationExport.js';

describe('removed planning modes', () => {
  it('keeps normal commands without advertising planning switches', async () => {
    const commands = await SlashCommandService.getInstance().getCommands();
    const names = commands.map(command => command.name);
    expect(names).not.toContain('mode');
    expect(names).not.toContain('pre-plan-mode');
    expect(names).toContain('run');
  });

  it('exports a normal banner without a planning indicator', () => {
    const banner = renderBannerBlock({
      workingDir: '/synthetic/workspace', agent: 'coder', provider: 'default', model: 'gpt-6-sol',
    });
    expect(banner).toContain('Model: gpt-6-sol');
    expect(banner).not.toContain('pre-plan mode');
    expect(banner).not.toContain('plan mode');
  });
});
