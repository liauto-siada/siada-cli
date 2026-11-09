import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import stringWidth from 'string-width';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Run the installed production bundle against an offline ACP server. SSH copy
// stays inside this PTY, so the test never reads or changes the desktop clipboard.
const directory = mkdtempSync(join(tmpdir(), 'siada-right-click-pty-'));
const screen = new TerminalScreen(30, 100);
let raw = '';
const driver = spawn(process.env.SIADA_TEST_PYTHON || 'python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
master,slave=pty.openpty()
fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack("HHHH",30,100,0,0))
args=[os.environ["CLIPBOARD_NODE"],os.environ["CLIPBOARD_UI_BUNDLE"],
      "--siada-path",os.environ["CLIPBOARD_NODE"],
      "--siada-args","tests/fixtures/three-pane-acp-server.mjs","."]
child=subprocess.Popen(args,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
os.close(slave)
pending=b""
try:
 while True:
  ready,_,_=select.select([master,sys.stdin.fileno()],[],[],.05)
  if master in ready:
   try:data=os.read(master,65536)
   except OSError:break
   if not data:break
   sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
  if sys.stdin.fileno() in ready:
   data=os.read(sys.stdin.fileno(),65536)
   if not data:break
   pending+=data
   while b"\n" in pending:
    line,pending=pending.split(b"\n",1)
    if line:os.write(master,bytes.fromhex(line.decode()))
finally:
 if child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
 os.close(master)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: {
    ...process.env,
    CLIPBOARD_NODE: process.execPath,
    CLIPBOARD_UI_BUNDLE: process.env.SIADA_TEST_UI_BUNDLE ||
      fileURLToPath(new URL('../bundle/siada-ui.js', import.meta.url)),
    SIADA_UI_CONFIG_DIR: directory, SIADA_UI_LOG_DIR: directory,
    TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', TERMINAL_EMULATOR: '',
    SSH_CONNECTION: 'synthetic-right-click-test', SSH_TTY: '', SSH_CLIENT: '',
    FORCE_COLOR: '3',
  },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const wait = async (condition, label) => {
  const deadline = Date.now() + 15000;
  while (!condition()) {
    if (Date.now() > deadline || driver.exitCode !== null) throw Error(label);
    await pause(50);
  }
};
const paste = text => send(`\x1b[200~${text}\x1b[201~`);
const mouse = (button, x, y, release = false) =>
  send(`\x1b[<${button};${x};${y}${release ? 'm' : 'M'}`);
const copies = () => [...raw.matchAll(/\x1b\]52;c;([A-Za-z0-9+/=]+)(?:\x07|\x1b\\)/g)]
  .map(match => Buffer.from(match[1], 'base64').toString('utf8'));
try {
  await wait(() => screen.display().includes('Type a message'), 'installed bundle ready');
  assert(raw.includes('\x1b[?1006h'), 'production mouse reporting enabled');
  paste('/fixture resume'); await pause(350);
  send('\x1b'); await pause(150); send('\r');
  await wait(() => screen.display().includes('Wire restored answer'), 'offline history ready');
  paste('CLIENT_PASTE'); await pause(300);
  assert(screen.display().includes('CLIENT_PASTE'), 'terminal paste reaches the draft');

  const text = 'Wire restored answer';
  const lines = screen.display().split('\n');
  const row = lines.findIndex(line => line.includes(text));
  const x = stringWidth(lines[row].slice(0, lines[row].indexOf(text))) + 1, y = row + 1;
  mouse(0, x, y);
  mouse(32, x + text.length, y); await pause(150);
  mouse(0, x + text.length, y, true);
  await wait(() => copies().includes(text), 'selection copies original text over OSC 52');
  const beforeCopy = copies().length;
  const visibleHistory = () => screen.display().split('\n').filter(line => line.includes('Wire restored'));
  const readingPosition = visibleHistory();
  mouse(2, x, y);
  await wait(() => copies().length > beforeCopy, 'right click retries an unconfirmed copy');
  assert.equal(copies().at(-1), text);
  assert.deepEqual(visibleHistory(), readingPosition, 'right copy preserves reading position');
  assert(screen.display().includes('CLIENT_PASTE'), 'right copy preserves the draft');
  console.log('PASS installed bundle: right-click copies selected original text and retries OSC 52');

  send('\x1b'); await pause(200);
  const noSelectionCopyCount = copies().length;
  mouse(2, x, y); mouse(2, x, y, true); await pause(350);
  assert.equal(copies().length, noSelectionCopyCount);
  assert(screen.display().includes('CLIENT_PASTE'));
  assert(!screen.display().includes('CLIENT_PASTEWire restored answer'),
    'SSH right click must not paste the session copy cache');
  paste('_FROM_TERMINAL'); await pause(300);
  assert(screen.display().includes('CLIENT_PASTE_FROM_TERMINAL'));
  console.log('PASS installed bundle: SSH right-click fallback is disabled; client terminal paste works');

  const log = readFileSync(join(directory, 'siada-ui.log'), 'utf8');
  assert(!log.includes('Ctrl/Cmd+V detected, reading clipboard'));
  assert(!/uncaughtException|unhandledRejection/.test(log));
  send('\x04'); await pause(150);
  send('\x03'); await pause(150); send('\x03');
  await wait(() => driver.exitCode !== null, 'clean exit');
  assert(raw.includes('\x1b[?1006l'), 'mouse reporting restored on exit');
  console.log('PASS installed bundle: no new UI exceptions; clean exit restores mouse reporting');
} catch (error) {
  console.error(error.stack);
  console.error(screen.display());
  process.exitCode = 1;
} finally {
  if (driver.exitCode === null) driver.stdin.end();
  console.log(`LOG_DIR ${directory}`);
}