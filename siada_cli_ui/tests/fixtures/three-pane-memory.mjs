import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { ConversationViewport } from '../../dist/components/Chat/ConversationViewport.js';
import { KeypressProvider } from '../../dist/contexts/KeypressContext.js';

const stdout = Object.assign(new PassThrough(), { columns: 100, rows: 30 });
stdout.resume();
let messages = [];
let frames = 0;
const view = () => React.createElement(KeypressProvider, null,
  React.createElement(ConversationViewport, { messages, width: 100, height: 29, isCollapsed: true, active: false }));
const app = render(view(), {
  stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
  onRender: () => frames++,
});
const wait = () => new Promise(resolve => setTimeout(resolve, 5));
const samples = [];
for (let index = 0; index < 500; index++) {
  const base = { author: 'Synthetic', timestamp: '2026-01-01T00:00:00Z' };
  messages = [...messages,
    { ...base, id: `u${index}`, type: 'user', content: `Question ${index}` },
    { ...base, id: `a${index}`, type: 'agent', content: `Answer ${index}\n` + '中文内容 '.repeat(300),
      metadata: { subtype: 'answer' } }];
  app.rerender(view()); await wait();
  if (index % 100 === 99) {
    global.gc();
    samples.push(Math.round(process.memoryUsage().heapUsed / 1024 / 1024));
  }
}
app.unmount(); app.cleanup();
process.stdout.write(JSON.stringify({ turns: 500, frames, heapMb: samples }) + '\n');
process.exit(0);