import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Test the packaged CLI and real bracketed-paste parser over a PTY. The
// synthetic ACP server keeps this check independent of credentials and models.
const directory = mkdtempSync(join(tmpdir(), 'siada-no-alt-screen-'));
const screen = new TerminalScreen(24, 80);
let raw = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys,shutil
master,slave=pty.openpty()
fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0))
command=['node',os.environ.get('SIADA_TEST_UI_BUNDLE','bundle/siada-ui.js'),
         '--no-alt-screen','--siada-path',shutil.which('node'),
         '--siada-args','tests/fixtures/three-pane-acp-server.mjs','.']
process=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
pending=b''
try:
 while True:
  ready,_,_=select.select([master,sys.stdin.fileno()],[],[],0.05)
  if process.poll() is not None and master not in ready:break
  if master in ready:
   try:data=os.read(master,65536)
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
    if line==b'resize':
     fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,72,0,0))
     os.killpg(process.pid,signal.SIGWINCH)
    elif line:os.write(master,bytes.fromhex(line.decode()))
except EOFError:pass
finally:
 if process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=2)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGKILL);process.wait()
 os.close(master);os.close(slave)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: '',
    SSH_CONNECTION: 'synthetic-native-history', SIADA_UI_CONFIG_DIR: directory,
    SIADA_UI_LOG_DIR: directory },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const wait = async (condition, label) => {
  const deadline = Date.now() + 12_000;
  while (!condition()) {
    if (Date.now() >= deadline) throw Error(`${label}\n${screen.display()}`);
    await pause(30);
  }
};
const has = text => screen.display().includes(text);
const command = async text => {
  send(`\x1b[200~${text}\x1b[201~`);
  await pause(600);
  if (text.startsWith('/')) { send('\x1b'); await pause(300); }
  send('\r');
};
const pointerEnable = /\x1b\[\?(?:1000|1002|1003|1006|1007|1049)h/;

try {
  await wait(() => has('Type a message'), 'editable startup');
  assert(!pointerEnable.test(raw));
  send('\x1b[200~SSH 粘贴探针\x1b[201~');
  await wait(() => has('SSH 粘贴探针'), 'terminal paste enters the composer');
  send('\x1b[<64;3;3M\x1b[<65;3;3M\x1b[<2;3;3M');
  await pause(200);
  await wait(() => has('SSH 粘贴探针'), 'stray mouse reports preserve the draft');
  assert(!raw.includes('\x1b]52;'), 'stray right click does not copy');
  send('\x04'); await pause(200);
  const start = raw.length;
  await command('Native scrollback PTY check');
  await wait(() => raw.slice(start).includes('Stream line 30:'), 'streaming beyond one screen');
  await wait(() => screen.history().includes('Stream line 1:'), 'early streaming lines enter native scrollback without keys');
  await wait(() => screen.transcript().includes('Final wire response.'), 'long reply finished and archived');
  await wait(() => has('Type a message'), 'composer returns after reply');
  await pause(500);
  for (let index = 1; index <= 45; index++) {
    const marker = `Stream line ${index}:`;
    assert.equal(screen.transcript().split(marker).length - 1, 1, `${marker} is preserved exactly once`);
  }
  assert(screen.transcript().includes('productionViewport'), 'code block is retained');
  const history = screen.history();
  await command('/model');
  await wait(() => has('synthetic-fast'), 'keyboard model picker');
  assert(!pointerEnable.test(raw), 'picker cannot capture mouse or change buffer');
  send('\x1b'); await pause(400);
  await wait(() => has('Type a message'), 'picker closes to composer');
  driver.stdin.write('resize\n'); await pause(400);
  assert(screen.history().startsWith(history), 'resize preserves native scrollback');
  assert.equal(screen.transcript().split('Stream line 1:').length - 1, 1, 'resize does not replay history');
  assert(!/\x1b\[(?:2|3)J|\x1bc/.test(raw.slice(start)), 'updates never clear terminal history');
  send('\x03'); await pause(150);
  send('\x03');
  await wait(() => raw.includes('To continue this session'), 'clean exit retains session hint');
  assert(!pointerEnable.test(raw));
  console.log('PASS: packaged no-alt-screen CLI, native scrollback while streaming, all 45 lines preserved once, SSH paste, ignored mouse, picker, resize, and clean exit');
} catch (error) {
  console.error(screen.display());
  throw error;
} finally {
  if (!driver.killed) {
    driver.stdin.end('quit\n');
    await new Promise(resolve => {
      if (driver.exitCode !== null) return resolve();
      const timer = setTimeout(() => { driver.kill(); resolve(); }, 3500);
      driver.once('exit', () => { clearTimeout(timer); resolve(); });
    });
  }
}