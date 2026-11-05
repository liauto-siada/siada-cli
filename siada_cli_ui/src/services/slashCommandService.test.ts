import { describe, it, expect } from 'vitest';
import { slashCommandService } from './slashCommandService.js';

describe('backend-approved command execution policy', () => {
  it('only bypasses the prompt queue when the backend advertises immediate mode', () => {
    slashCommandService.updateCommandsFromBackend([
      { name: 'status', description: '', execution_mode: 'immediate' },
      { name: 'help', description: '', execution_mode: 'immediate' },
      { name: 'clear', description: '' },
      { name: 'statusbar', description: '' },
    ]);
    expect(slashCommandService.isImmediateCommand(' /status ')).toBe(true);
    expect(slashCommandService.isImmediateCommand('/help')).toBe(true);
    for (const text of ['/stat', '/statusbar', '/clear', '!status', 'plain text']) {
      expect(slashCommandService.isImmediateCommand(text)).toBe(false);
    }
    slashCommandService.updateCommandsFromBackend([{ name: 'status', description: '' }]);
    expect(slashCommandService.isImmediateCommand('/status')).toBe(false);
  });
});