import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import logUpdate from '../../node_modules/@jrichman/ink/build/log-update.js';
import { displayWidth, initializeWindowsRendering, terminalLayoutColumns } from '../../dist/utils/terminalWidth.js';
import { logger } from '../../dist/utils/logger.js';

assert.equal(process.stdout.isTTY, true);
const originalOutputState = initializeWindowsRendering(
  process.argv[2],
  fileURLToPath(new URL('../../../siada/entrypoint/windows_terminal_probe.py', import.meta.url)),
);
const columns = terminalLayoutColumns(process.stdout.columns);
assert.equal(columns, process.stdout.columns - 1,
  `native calibration did not initialize: ${readFileSync(logger.getLogFile(), 'utf8')}`);
const update = logUpdate.create(process.stdout, {
  alternateBuffer: true, incremental: true, showCursor: true,
  getRows: () => process.stdout.rows, getColumns: () => columns,
});
const frame = (art, progress) => `${art}\nSTATIC\n${progress}\n\n\n\n\nINPUT`;
const paint = (art, progress) => update(frame(art, progress), [], undefined, { row: 7, col: 5 });
paint(`\x1b[38;2;20;100;180m${'▆'.repeat(200)}\x1b[39m`, 'first');
process.stderr.write(JSON.stringify({
  stage: 'initial', columns, blockWidth: displayWidth('▆'), originalOutputState,
}) + '\n');
process.stdin.once('data', () => {
  for (let index = 0; index < 50; index++) paint('A', `● ${index}`);
  process.stderr.write('updated\n');
  process.stdin.once('data', () => {
    update.done();
    process.exit(0);
  });
});