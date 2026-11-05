import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const rows = Number(process.env.INPUT_ROWS || 24);
const columns = Number(process.env.INPUT_COLUMNS || 80);
const temporaryHome = mkdtempSync(join(tmpdir(), 'siada-input-height-'));
const screen = new TerminalScreen(rows, columns);
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['INPUT_ROWS']),int(os.environ['INPUT_COLUMNS']),0,0))
preload="data:text/javascript,import os from 'node:os';import{syncBuiltinESMExports}from'node:module';os.homedir=()=>process.env.INPUT_TEST_HOME;syncBuiltinESMExports();"
p=subprocess.Popen(['node','--import',preload,'bundle/siada-ui.js',
 '--siada-path',os.environ['INPUT_NODE'],'--siada-args','tests/fixtures/three-pane-acp-server.mjs',
 '--log-level','debug','.'],stdin=s,stdout=s,stderr=s,start_new_session=True)
os.close(s);pending=b''
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
  try:p.wait(timeout=1)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
    INPUT_ROWS: String(rows), INPUT_COLUMNS: String(columns), INPUT_TEST_HOME: temporaryHome,
    INPUT_NODE: process.execPath, SIADA_UI_LOG_DIR: join(temporaryHome, 'logs'),
    SSH_CONNECTION: 'synthetic-input-height' },
});
let raw = '';
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.on('data', data => { raw += data.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const wait = async (condition, label) => {
  const deadline = Date.now() + 10000;
  while (!condition()) {
    assert(Date.now() < deadline && driver.exitCode === null,
      `Missing ${label}\n${screen.display()}\n${raw.slice(-1200)}`);
    await pause(30);
  }
  await pause(250);
};
const inputRows = () => screen.display().split('\n').filter(line => /HeightLine\d\d/.test(line));
const borderRows = () => screen.display().split('\n')
  .map((line, index) => /^─{10}/.test(line) ? index : -1).filter(index => index >= 0);
const paste = text => send(`\x1b[200~${text}\x1b[201~`);
try {
  await wait(() => /Type a message|输入消息/.test(screen.display()), 'input ready');
  const emptyBorders = borderRows();
  assert(emptyBorders.length >= 2, screen.display());
  const emptyHeight = emptyBorders.at(-1) - emptyBorders.at(-2);
  paste(Array.from({ length: 10 }, (_, i) => `HeightLine${String(i + 1).padStart(2, '0')}`).join('\n'));
  await wait(() => screen.display().includes('HeightLine10'), 'ten-line input');
  assert.equal(inputRows().length, 10, screen.display());
  const expandedBorders = borderRows();
  assert.equal(expandedBorders.at(-1) - expandedBorders.at(-2), 11, screen.display());
  // Paste only the next line so the large-paste folding threshold does not apply.
  paste('\nHeightLine11');
  await wait(() => screen.display().includes('HeightLine11'), 'overflow follows cursor');
  assert.equal(inputRows().length, 10, screen.display());
  assert(!screen.display().includes('HeightLine01'), screen.display());
  for (let i = 0; i < 10; i++) { send('\x1b[A'); await pause(70); }
  await wait(() => screen.display().includes('HeightLine01'), 'upward cursor scroll');
  assert.equal(inputRows().length, 10, screen.display());
  // Ctrl+C clears the draft in the real App.
  send('\x03');
  await wait(() => /Type a message|输入消息/.test(screen.display()) && inputRows().length === 0, 'clear draft');
  const clearedBorders = borderRows();
  assert.equal(clearedBorders.at(-1) - clearedBorders.at(-2), emptyHeight, screen.display());
  assert(!/Error:|Traceback/.test(raw), raw.slice(-1200));
  console.log(`PASS ${rows}x${columns}: 10 visible lines, overflow, cursor scroll, height recovery; shipping bundle + ACP`);
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.exitCode === null ? driver.once('exit', resolve) : resolve());
  rmSync(temporaryHome, { recursive: true, force: true });
}