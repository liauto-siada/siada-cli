import React from 'react';
import { render } from '@jrichman/ink';
import { fileURLToPath } from 'node:url';
import { MainLayout } from '../../dist/components/layouts/MainLayout.js';
import { AppProvider } from '../../dist/store/context.js';
import { KeypressProvider } from '../../dist/contexts/KeypressContext.js';
import { inputRestoreStore } from '../../dist/store/inputRestoreStore.js';
import { initializeWindowsRendering, terminalLayoutColumns } from '../../dist/utils/terminalWidth.js';
import { createWorkingStdio } from '../../dist/utils/stdio.js';

const originalOutputState = initializeWindowsRendering(process.argv[2],
  fileURLToPath(new URL('../../../siada/entrypoint/windows_terminal_probe.py', import.meta.url)));
const { stdout, stderr } = createWorkingStdio();
const rows = process.stdout.rows;
const columns = terminalLayoutColumns(process.stdout.columns);
const base = {
  demoPresentation: true, fullStatusBar: true, bannerInHistory: true,
  workingDir: '.', model: `MODEL_${'x'.repeat(160)}`, onSendMessage: () => {},
  todoItems: Array.from({ length: 8 }, (_, index) => ({ content: `TASK_${index}`, status: 'in_progress' })),
  subAgentItems: [{ id: 'agent', title: 'AGENT_MARKER', status: 'running' }],
  goalState: { goal: { objective: 'GOAL_MARKER', status: 'active' } },
  messages: [{ id: 'answer', type: 'agent', author: 'Synthetic', timestamp: '',
    content: '正文界●\n'.repeat(80), metadata: { subtype: 'answer' } }],
};
const view = props => React.createElement(KeypressProvider, null,
  React.createElement(AppProvider, null, React.createElement(MainLayout, props)));
const frames = [];
const app = render(view({
  ...base, loading: true, sideQuestionPanelVisible: true,
  sideQuestions: [{ id: 'side', question: 'SIDE_QUESTION', answer: 'SIDE_ANSWER\n'.repeat(50) }],
}), {
  stdout, stderr, stdin: process.stdin, alternateBuffer: true, incrementalRendering: true,
  patchConsole: false, exitOnCtrlC: false, maxFps: 0,
  onRender: ({ output }) => frames.push(output.replace(/\x1b\[[0-9;]*m/g, '')),
});
const pause = () => new Promise(resolve => setTimeout(resolve, 100));
await pause();
process.stderr.write(JSON.stringify({
  stage: 'initial', columns, rows, originalOutputState,
  everyFrameHasInput: frames.length > 0 && frames.every(frame => frame.includes('▸')),
  missingFrames: frames.filter(frame => !frame.includes('▸')).map(frame => frame.slice(-1500)),
}) + '\n');
process.stdin.once('data', async () => {
  app.rerender(view(base));
  await pause();
  inputRestoreStore.request('DRAFT_MARKER界●\nsecond\nthird');
  await pause();
  const inputRow = frames.at(-1).split('\n').findIndex(line => line.includes('DRAFT_MARKER'));
  const start = frames.length;
  for (let index = 0; index < 8; index++) {
    app.rerender(view({
      ...base, loading: index % 2 === 0,
      messages: [{ ...base.messages[0], content: `更新 ${index}\n${'界●正文\n'.repeat(120 + index)}` }],
    }));
    await pause();
  }
  process.stderr.write(JSON.stringify({
    stage: 'updated', inputRow, rows: process.stdout.rows,
    everyFrameHasInput: frames.every(frame => frame.includes('▸')),
    stableInputRow: frames.slice(start).every(frame =>
      frame.split('\n').findIndex(line => line.includes('DRAFT_MARKER')) === inputRow),
  }) + '\n');
  process.stdin.once('data', () => {
    app.unmount();
    app.cleanup();
    setImmediate(() => process.exit(0));
  });
});