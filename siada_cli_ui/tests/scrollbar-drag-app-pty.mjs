import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Exercise SGR input through the production bundle and an offline ACP process.
const rows = Number(process.env.SCROLL_ROWS || 30);
const columns = Number(process.env.SCROLL_COLUMNS || 100);
const temporaryHome = mkdtempSync(join(tmpdir(), 'siada-scrollbar-drag-'));
const screen = new TerminalScreen(rows, columns);
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['SCROLL_ROWS']),int(os.environ['SCROLL_COLUMNS']),0,0))
preload="data:text/javascript,import os from 'node:os';import{syncBuiltinESMExports}from'node:module';os.homedir=()=>process.env.SCROLL_TEST_HOME;syncBuiltinESMExports();"
p=subprocess.Popen(['node','--import',preload,'bundle/siada-ui.js',
 '--siada-path',os.environ['SCROLL_NODE'],'--siada-args','tests/fixtures/three-pane-acp-server.mjs',
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
    SCROLL_ROWS: String(rows), SCROLL_COLUMNS: String(columns), SCROLL_TEST_HOME: temporaryHome,
    SCROLL_NODE: process.execPath, SIADA_UI_LOG_DIR: join(temporaryHome, 'logs'),
    SSH_CONNECTION: 'synthetic-scrollbar-drag' },
});
let raw = '';
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.on('data', data => { raw += data.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
const wait = async (condition, label) => {
  const deadline = Date.now() + 15000;
  while (!condition()) {
    assert(Date.now() < deadline && driver.exitCode === null,
      `${label}\n${screen.display()}\n${raw.slice(-1200)}`);
    await pause(30);
  }
  await pause(150);
};
const mouse = async (button, x, y, release = false) => {
  send(`\x1b[<${button};${x};${y}${release ? 'm' : 'M'}`);
  await pause(150);
};
try {
  await wait(() => /Type a message|输入消息/.test(screen.display()), 'input ready');
  assert(has('wire-test'), 'ACP banner received');
  send('\x1b[200~scrollbar verification\x1b[201~');
  await pause(500); send('\r');
  await wait(() => has('Final wire response.'), 'streamed long reply');
  let lines = screen.display().split('\n');
  const thumbRow = lines.findIndex(line => line[columns - 1] === '│');
  assert(thumbRow >= 0, `right scrollbar visible\n${screen.display()}`);
  await mouse(0, columns, thumbRow + 1);
  await mouse(32, Math.floor(columns / 2), 1);
  await wait(() => screen.display().split('\n')[0].includes('Siada CLI vwire-test'), 'drag reaches banner at top');
  await mouse(32, Math.floor(columns / 2), rows);
  await wait(() => has('Final wire response.'), 'drag reaches reply tail');
  await mouse(0, Math.floor(columns / 2), rows, true);
  await mouse(35, columns, 1);
  assert(has('Final wire response.'), 'released gesture does not scroll');
  assert(!has('Copied'), 'scrollbar does not copy text');
  // Clicking the empty track at the top jumps immediately.
  await mouse(0, columns, 1);
  await mouse(0, columns, 1, true);
  await wait(() => screen.display().split('\n')[0].includes('Siada CLI vwire-test'), 'track click reaches top');
  await mouse(65, Math.floor(columns / 2), 5);
  await wait(() => !screen.display().split('\n')[0].includes('Siada CLI vwire-test'), 'wheel still scrolls after dragging');
  assert(!/Error:|Traceback/.test(raw), raw.slice(-1200));
  console.log(`PASS ${columns}x${rows}: bundle + ACP, thumb drag, outside capture, endpoints, release, track and wheel`);
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.exitCode === null ? driver.once('exit', resolve) : resolve());
  rmSync(temporaryHome, { recursive: true, force: true });
}