/** Native-input integration harness: no model, network, or browser launch. */
import React from 'react';
import { Box, Text, getBoundingBox, render, type DOMElement } from '@jrichman/ink';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { KeypressProvider } from '../../src/contexts/KeypressContext.js';
import { useKeypress } from '../../src/hooks/useKeypress.js';
import { BannerLinkInteraction } from '../../src/components/Banner/BannerHeader.js';
import { withEditorTerminal } from '../../src/utils/editorTerminal.js';
import { initializeWindowsRendering } from '../../src/utils/terminalWidth.js';
import { createWorkingStdio } from '../../src/utils/stdio.js';
import { getNativeWindowsInput, getTerminalInput, initializeWindowsInput } from '../../src/services/windowsConsole.js';

const python = process.argv[2];
const profile = initializeWindowsRendering(python,
  fileURLToPath(new URL('../../../siada/entrypoint/windows_terminal_probe.py', import.meta.url)));
await initializeWindowsInput(python,
  fileURLToPath(new URL('../../../siada/entrypoint/windows_console_input.py', import.meta.url)),
  Boolean(profile));
const nativeInput = getNativeWindowsInput();
const { stdout, stderr } = createWorkingStdio();
let node: DOMElement | null = null;
let ready = false;
let clicked = false;
const report = (stage: string, data = {}) => process.stderr.write(JSON.stringify({ stage, ...data }) + '\n');

function Observer() {
  useKeypress(key => {
    report('key', { name: key.name, sequence: key.sequence, shift: key.shift });
    if (key.sequence === 'e') {
      withEditorTerminal(() => {
        const result = spawnSync(python, ['-I', '-c',
          'import json,sys; print(json.dumps({"stage":"editor"}),file=sys.stderr,flush=True); ' +
          'text=input(); print(json.dumps({"stage":"editor-return","text":text}),file=sys.stderr,flush=True)',
        ], { stdio: 'inherit', timeout: 10000 });
        if (result.status !== 0) throw Error('Synthetic editor failed');
      }, {
        stdin: process.stdin, stdout, alternateBuffer: true,
        kittyKeyboard: false, mouseTracking: true, nativeInput, repaint: () => app.rerender(view),
      });
      report('resumed');
    } else if (key.sequence === '\x04') {
      app.unmount();
      app.cleanup();
      nativeInput?.stop();
      report('finished');
      setImmediate(() => process.exit(0));
    }
  });
  return null;
}

const view = <KeypressProvider>
  <Observer />
  <Box paddingLeft={3} paddingTop={2}>
    <BannerLinkInteraction columns={30} links={[{ id: 'test', url: 'test://native-click' }]}>
      {state => <Box ref={value => {
        node = value;
        if (value) state.nodes.current.set('test', value);
        else state.nodes.current.delete('test');
      }} width={11}><Text>NATIVE_LINK</Text></Box>}
    </BannerLinkInteraction>
  </Box>
</KeypressProvider>;
const app = render(view, {
  stdin: getTerminalInput(), stdout, stderr, alternateBuffer: true,
  incrementalRendering: true, patchConsole: false, exitOnCtrlC: false, maxFps: 0,
  onRender: ({ output }) => {
    if (!ready && node && output.includes('NATIVE_LINK')) {
      ready = true;
      const point = getBoundingBox(node);
      setImmediate(() => report('ready', { native: Boolean(nativeInput), x: point.x, y: point.y }));
    }
    // Unsupported synthetic URLs reject before any browser subprocess starts.
    // The error view proves that the real link's down/up hit test activated.
    if (!clicked && /Could not open link|无法打开链接/.test(output)) {
      clicked = true;
      setImmediate(() => report('clicked'));
    }
  },
});