// Real production input and key parsing; no clipboard, subprocess or Ink mocks.
// Bundle this harness beside native-clipboard/ and run it under an isolated Xvfb.
import React from 'react';
import { render } from '@jrichman/ink';
import { KeypressProvider } from '../src/contexts/KeypressContext.js';
import { AppProvider } from '../src/store/context.js';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { readFileSync } from 'node:fs';

render(
  <KeypressProvider><AppProvider>
    <MainLayout workingDir="." model="native-test" isCollapsed
      messages={[{ id: 'native-test', type: 'agent', author: 'Test', timestamp: '',
        content: 'Native clipboard test history.', metadata: { subtype: 'answer' } }]}
      onSendMessage={(text, paths) => {
        const images = (paths ?? []).map(path => readFileSync(path).toString('base64'));
        process.stdout.write(`\nNATIVE_SUBMIT:${JSON.stringify({ text, paths, images })}\n`);
      }} />
  </AppProvider></KeypressProvider>,
  { exitOnCtrlC: false, patchConsole: false, maxFps: 0 },
);