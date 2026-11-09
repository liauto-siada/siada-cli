import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Verify the one-shot star hint against the shipping bundle in a real PTY.
const rows = Number(process.env.BANNER_TEST_ROWS || 30);
const columns = Number(process.env.BANNER_TEST_COLUMNS || 100);
const colorLevel = process.env.BANNER_TEST_COLOR_LEVEL || '3';
const logDirectory = mkdtempSync(join(tmpdir(), 'siada-star-hint-logs-'));
const screen = new TerminalScreen(rows, columns);
let raw = '';
let stderr = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['BANNER_TEST_ROWS']),int(os.environ['BANNER_TEST_COLUMNS']),0,0))
attributes=termios.tcgetattr(s)
attributes[0] &= ~termios.ICRNL
termios.tcsetattr(s,termios.TCSANOW,attributes)
args=['node','bundle/siada-ui.js','--siada-path',os.environ['BANNER_TEST_NODE'],
 '--siada-args','tests/fixtures/three-pane-acp-server.mjs','--log-level','debug','.']
p=subprocess.Popen(args,stdin=s,stdout=s,stderr=s,start_new_session=True)
os.close(s)
pending=b''
try:
 while True:
  ready,_,_=select.select([m,sys.stdin.fileno()],[],[],.05)
  if m in ready:
   try:data=os.read(m,65536)
   except OSError:break
   if not data:break
   sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
  if sys.stdin.fileno() in ready:
   data=os.read(sys.stdin.fileno(),65536)
   if not data:break
   pending+=data
   while b'\n' in pending:
    line,pending=pending.split(b'\n',1)
    if line==b'quit':raise EOFError()
    if line:os.write(m,bytes.fromhex(line.decode()))
except EOFError:pass
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: process.env.BANNER_TEST_TERM || 'WezTerm',
    FORCE_COLOR: colorLevel, BANNER_TEST_ROWS: String(rows), BANNER_TEST_COLUMNS: String(columns),
    BANNER_TEST_NODE: process.execPath, SIADA_UI_LOG_DIR: logDirectory,
    SSH_CONNECTION: 'synthetic-star-hint-pty-check' },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.on('data', data => { stderr += data.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const wait = async (condition, label, timeout = 12000) => {
  const deadline = Date.now() + timeout;
  while (!condition()) {
    assert(Date.now() < deadline && driver.exitCode === null, `Missing ${label}\n${screen.display()}\n${stderr}`);
    await pause(50);
  }
};

/** Every near-white cell the sweep and the landing glow sent to the terminal. */
const litCells = text => {
  const cells = [];
  const pattern = /\x1b\[38;2;(\d+);(\d+);(\d+)m/g;
  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    if (Number(match[1]) < 220 || Number(match[2]) < 240 || Number(match[3]) < 250) continue;
    let rest = text.slice(pattern.lastIndex);
    for (let sgr = /^\x1b\[[0-9;]*m/.exec(rest); sgr; sgr = /^\x1b\[[0-9;]*m/.exec(rest)) {
      rest = rest.slice(sgr[0].length);
    }
    cells.push({ at: match.index, glyph: rest[0] ?? '' });
  }
  return cells;
};

try {
  await wait(() => /Type a message|输入消息/.test(screen.display()), 'ready input');
  // Startup keeps the single thread busy; let the one-shot cycle finish before judging it.
  await pause(4200);
  const appearsAt = raw.indexOf('☆');
  assert(appearsAt >= 0, 'the banner header reaches the terminal');
  const cells = litCells(raw.slice(appearsAt));
  assert(cells.length > 12, `the hint must light the row, got ${cells.length} cells`);
  const first = cells[0];
  assert(['─', 'S', 'i', 'a', 'd', 'C', 'L', 'I', 'v'].includes(first.glyph),
    `the hint starts on the left rule and title, got ${JSON.stringify(first.glyph)}`);
  const star = cells.findIndex(cell => cell.glyph === '☆');
  assert(star > 0, 'the sweep reaches the star link');
  assert(star > cells.findIndex(cell => cell.glyph === '─'), 'the light travels towards the star, not away from it');
  const afterStar = cells.slice(star).filter(cell => !'☆Star '.includes(cell.glyph));
  assert.equal(afterStar.length, 0, 'nothing past the star label is highlighted');

  await pause(1900);
  const settled = raw.length;
  const display = screen.display();
  assert(/Siada CLI v/.test(display) && display.includes('☆ Star'),
    'the header keeps its title and star link');
  assert.equal(litCells(raw.slice(settled)).length, 0, 'the hint leaves no lit cell behind');
  await pause(300);
  assert.equal(raw.length, settled, 'the settled banner stops rendering');
  assert.equal(screen.display(), display, 'the settled banner keeps every character');
  assert(!/Traceback|Error:/.test(raw + stderr), 'no application errors');
  console.log(`PASS ${rows}x${columns}: star hint sweeps ${cells.length} cells from the left rule into ☆ Star once, then idles`);
  console.log(`LOG_DIR: ${logDirectory}`);
} catch (error) {
  console.error(error.stack);
  console.error(screen.display());
  console.error(stderr);
  process.exitCode = 1;
} finally {
  if (driver.exitCode === null) {
    driver.stdin.end('quit\n');
    await new Promise(resolve => driver.once('exit', resolve));
  }
}
