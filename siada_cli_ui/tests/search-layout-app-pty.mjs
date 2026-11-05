import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Verify the shipping bundle, ACP history loading, and App's real key bindings.
const rows = 30;
const columns = Number(process.env.SEARCH_COLUMNS || 100);
const temporaryHome = mkdtempSync(join(tmpdir(), 'siada-search-app-'));
const logDirectory = join(temporaryHome, 'logs');
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',30,int(os.environ['SEARCH_COLUMNS']),0,0))
# Override Node's home lookup in this child only, without altering HOME.
preload="data:text/javascript,import os from 'node:os';import{syncBuiltinESMExports}from'node:module';os.homedir=()=>process.env.SEARCH_TEST_HOME;syncBuiltinESMExports();"
p=subprocess.Popen(['node','--import',preload,'bundle/siada-ui.js',
 '--siada-path',os.environ['SEARCH_NODE'],'--siada-args','tests/fixtures/three-pane-acp-server.mjs',
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
    SEARCH_COLUMNS: String(columns), SEARCH_TEST_HOME: temporaryHome, SEARCH_NODE: process.execPath,
    SIADA_UI_LOG_DIR: logDirectory, SSH_CONNECTION: 'synthetic-search-layout' },
});
const screen = new TerminalScreen(rows, columns);
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
  await pause(150);
};
const cwdCount = () => (screen.display().match(/cwd:/g) || []).length;
const checkQueries = () => {
  const text = screen.display();
  assert(text.includes('Search "timeout:" in src'), text);
  assert(text.includes('Search "●" in src'), text);
  assert.equal((text.match(/timeout:/g) || []).length, 1, text);
  assert(text.includes('Search results: 2 matches'), text);
  assert(text.includes('src/a.ts:12'), text);
};

try {
  await wait(() => /Type a message|输入消息/.test(screen.display()), 'input ready');
  send('\x1b[200~/fixture search-layout\x1b[201~');
  await pause(350); send('\x1b'); await pause(250); send('\r');
  await wait(() => screen.display().includes('Search layout scene ready.'), 'ACP search scene');
  checkQueries();
  assert.equal(cwdCount(), 0, screen.display());
  const lines = screen.display().split('\n');
  const row = lines.findIndex(line => line.includes('Search "timeout:"'));
  const x = lines[row].indexOf('Search') + 2;
  send(`\x1b[<0;${x};${row + 1}M`);
  await pause(80);
  send(`\x1b[<0;${x};${row + 1}m`);
  await wait(() => cwdCount() === 1, 'individual mouse expansion');
  checkQueries();
  send('\x0f');
  await wait(() => cwdCount() === 2, 'Ctrl+O expansion');
  checkQueries();
  send('\x0f');
  await wait(() => cwdCount() === 0, 'Ctrl+O collapse');
  checkQueries();
  assert(!/Error:|Traceback/.test(raw), raw.slice(-1200));
  console.log(screen.display().split('\n').filter(line => line.trim()).join('\n'));
  console.log(`PASS ${rows}x${columns}: shipping bundle + ACP + mouse + Ctrl+O + results`);
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.once('exit', resolve));
  rmSync(temporaryHome, { recursive: true, force: true });
}