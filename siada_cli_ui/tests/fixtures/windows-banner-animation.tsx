/** Inspect real conhost animation without changing application rendering. */
import React from 'react';
import chalk from 'chalk';
import { Box, render } from '@jrichman/ink';
import { fileURLToPath } from 'node:url';
import { BannerArt } from '../../src/components/Banner/BannerArt.js';
import { BannerMotion } from '../../src/components/Banner/bannerMotion.js';
import { BANNER_LINES } from '../../src/constants/banner.js';
import { KeypressProvider } from '../../src/contexts/KeypressContext.js';
import { useKeypress } from '../../src/hooks/useKeypress.js';
import { bannerBlockCharacter, displayWidth, initializeWindowsRendering } from '../../src/utils/terminalWidth.js';
import { createWorkingStdio } from '../../src/utils/stdio.js';
import { initializeWindowsInput, getNativeWindowsInput, getTerminalInput } from '../../src/services/windowsConsole.js';

const python = process.argv[2];
const state = initializeWindowsRendering(python,
  fileURLToPath(new URL('../../../siada/entrypoint/windows_terminal_probe.py', import.meta.url)));
await initializeWindowsInput(python,
  fileURLToPath(new URL('../../../siada/entrypoint/windows_console_input.py', import.meta.url)), Boolean(state));
chalk.level = 3;
const { stdout, stderr } = createWorkingStdio();
const artwork = new BannerMotion(stdout.columns - 3);
const report = (stage: string, values = {}) => process.stderr.write(JSON.stringify({ stage, ...values }) + '\n');
let baseline = '';
let frames = 0;
let animated = false;
let fading = false;
let settled = false;
function Observer() {
  useKeypress(key => {
    if (key.sequence === '\x1b[<35;1;1M') fading = true;
    if (key.sequence === '\x04') {
      app.unmount(); app.cleanup(); getNativeWindowsInput()?.stop();
      setImmediate(() => process.exit(0));
    }
  });
  return null;
}
const app = render(<KeypressProvider><Observer /><Box paddingLeft={3} paddingTop={2}>
  <BannerArt columns={stdout.columns - 3} interactive />
</Box></KeypressProvider>, {
  stdin: getTerminalInput(), stdout, stderr, alternateBuffer: true,
  incrementalRendering: true, exitOnCtrlC: false, patchConsole: false, maxFps: 0,
  onRender: ({ output }) => {
    if (!baseline && output.includes(bannerBlockCharacter())) {
      baseline = output;
      setImmediate(() => report('ready', {
        columns: stdout.columns, rows: stdout.rows,
        selectedBlock: bannerBlockCharacter(),
        widths: [...new Set(BANNER_LINES.join(''))].map(character => [character.codePointAt(0), displayWidth(character)]),
        artWidths: [...new Set(artwork.lines.flat())].map(character => [character.codePointAt(0), displayWidth(character)]),
        letterStarts: artwork.lines.map(line => [2, 10, 13, 21, 29, 41, 49, 57].map(index =>
          displayWidth(line.slice(0, index).join('')))),
        point: { x: 3 + displayWidth(artwork.lines[2].slice(0, 24).join('')), y: 4 },
      }));
    } else if (output !== baseline) {
      if (++frames >= 3 && !animated) {
        animated = true;
        setImmediate(() => report('animated', { frames }));
      }
    } else if (fading && animated && !settled) {
      settled = true;
      setImmediate(() => report('settled', { frames }));
    }
  },
});