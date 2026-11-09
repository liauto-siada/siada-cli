import './helpers/chineseLocale.js';
import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { AppProvider } from '../src/store/context.js';
import { inputRestoreStore } from '../src/store/inputRestoreStore.js';
import { configureTerminalWidths, displayWidth } from '../src/utils/terminalWidth.js';
import { TerminalScreen } from './helpers/terminalScreen.js';

const dimensions = { rows: 24, columns: 48 };
vi.mock('../src/hooks/useTerminalSize.js', () => ({ useTerminalSize: () => dimensions }));
vi.mock('../src/hooks/useKeypress.js', () => ({ useKeypress: () => {} }));
const pause = () => new Promise(resolve => setTimeout(resolve, 80));
afterEach(() => { configureTerminalWidths(); inputRestoreStore.consume(); });

describe('bottom composer ownership', () => {
  it.each([20, 24, 47])('keeps input inside every frame while panels and streaming grow at %i rows', async rows => {
    dimensions.rows = rows;
    dimensions.columns = rows === 47 ? 174 : 48;
    configureTerminalWidths({ '▆': 2, '●': 2, '☆': 2, '◐': 2 }, true);
    const stdout = Object.assign(new PassThrough(), dimensions);
    const screen = new TerminalScreen(rows, dimensions.columns + 1, displayWidth, true);
    const frames: string[] = [];
    stdout.on('data', chunk => screen.feed(chunk.toString()));
    const base = {
      demoPresentation: true, fullStatusBar: true, workingDir: '.',
      model: `MODEL_${'x'.repeat(160)}`, onSendMessage: () => {},
      todoItems: Array.from({ length: 8 }, (_, index) => ({ content: `TASK_${index}`, status: 'in_progress' as const })),
      subAgentItems: [{ id: 'a', title: 'AGENT_MARKER', status: 'running' as const }],
      goalState: { goal: { objective: 'GOAL_MARKER', status: 'active' } } as any,
      messages: [{ id: 'answer', type: 'agent' as const, author: 'Synthetic', timestamp: '',
        content: '正文界●\n'.repeat(80), metadata: { subtype: 'answer' as const } }],
    };
    const busy = {
      ...base, loading: true,
      sideQuestions: [{ id: 'side', question: 'SIDE_QUESTION', answer: 'SIDE_ANSWER\n'.repeat(50) }] as any,
      sideQuestionPanelVisible: true,
    };
    const view = state => <AppProvider><MainLayout {...state} /></AppProvider>;
    const app = render(view(busy), {
      stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false,
      alternateBuffer: true, incrementalRendering: true, maxFps: 0,
      onRender: ({ output }) => frames.push(output.replace(/\x1b\[[0-9;]*m/g, '')),
    });
    try {
      await pause();
      expect(frames.every(frame => frame.includes('▸'))).toBe(true);
      app.rerender(view(base));
      await pause();
      inputRestoreStore.request('DRAFT_MARKER界●\nsecond\nthird');
      await pause();
      const inputRow = screen.display().split('\n').findIndex(line => line.includes('DRAFT_MARKER'));
      expect(inputRow).toBeGreaterThan(rows / 2);
      expect(screen.display()).toContain('AGENT_MARKER');
      for (let index = 0; index < 8; index++) {
        app.rerender(view({ ...base, loading: index % 2 === 0,
          messages: [{ ...base.messages[0], content: `更新 ${index}\n${'界●正文\n'.repeat(120 + index)}` }] }));
        await pause();
        const lines = screen.display().split('\n');
        expect(lines.findIndex(line => line.includes('DRAFT_MARKER'))).toBe(inputRow);
        expect(lines[inputRow - 1]).toMatch(/^─+$/);
        expect(lines[inputRow + 3]).toMatch(/^─+$/);
        expect(lines[rows - 1]).toBe('');
      }
      expect(frames.every(frame => frame.split('\n').length <= rows - 1)).toBe(true);
    } finally { app.unmount(); app.cleanup(); }
  });
});