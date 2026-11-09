import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const directory = mkdtempSync(join(tmpdir(), 'siada-wheel-pty-'));
const screen = new TerminalScreen(24, 80);
let raw = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack("HHHH",24,80,0,0))
args=["node",os.environ["MOUSE_UI_BUNDLE"],"--siada-path",os.environ["MOUSE_NODE"],
      "--siada-args","tests/fixtures/three-pane-acp-server.mjs","."]
p=subprocess.Popen(args,stdin=s,stdout=s,stderr=s,start_new_session=True)
os.close(s)
pending=b""
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
   while b"\n" in pending:
    line,pending=pending.split(b"\n",1)
    if line:os.write(m,bytes.fromhex(line.decode()))
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: {
    ...process.env, MOUSE_NODE: process.execPath,
    MOUSE_UI_BUNDLE: process.env.SIADA_TEST_UI_BUNDLE ||
      fileURLToPath(new URL('../bundle/siada-ui.js', import.meta.url)),
    SIADA_UI_CONFIG_DIR: directory, SIADA_UI_LOG_DIR: directory,
    TERM: 'xterm-256color', FORCE_COLOR: '3',
    TERM_PROGRAM: process.env.SIADA_TEST_TERM_PROGRAM ?? 'JetBrains-JediTerm',
    TERMINAL_EMULATOR: process.env.SIADA_TEST_TERMINAL_EMULATOR ?? '',
    SSH_CONNECTION: 'synthetic-wheel-test',
  },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const wait = async (condition, label) => {
  const deadline = Date.now() + 12000;
  while (!condition()) {
    if (Date.now() > deadline || driver.exitCode !== null) throw Error(label);
    await pause(50);
  }
};
try {
  await wait(() => screen.display().includes('Type a message'), 'bundled UI ready');
  assert(raw.includes('\x1b[?1007l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h'));
  // Wait for the one-shot welcome hint before comparing hover-only output.
  await pause(3800);
  const bannerFrame = screen.display();
  const costRow = bannerFrame.split('\n').findIndex(line => line.includes('成本费用'));
  assert(costRow >= 0, 'banner link is visible');
  let offset = raw.length;
  send(`\x1b[<3;2;${costRow + 1}M`);
  await wait(() => /\x1b\[[0-9;]*48;[0-9;]*m/.test(raw.slice(offset)), 'JediTerm link hover background');
  assert.equal(screen.display(), bannerFrame, 'link hover preserves text and input position');
  send('\x1b[<3;1;20M'); await pause(200);
  offset = raw.length;
  send('\x1b[<3;20;4M');
  await wait(() => raw.length > offset, 'JediTerm artwork hover repaint');
  assert.equal(screen.display(), bannerFrame, 'artwork hover preserves text and input position');
  send('\x1b[<3;1;20M'); await pause(750);
  console.log('PASS bundled UI handles JediTerm 3M link and artwork hover');
  send('\x1b[200~/fixture markdown-history\x1b[201~'); await pause(350);
  send('\x1b'); await pause(350); send('\r');
  await wait(() => screen.display().includes('HISTORY_TAIL'), 'restored long history');
  send('\x1b[200~DRAFT-A\nDRAFT-B\nDRAFT-C\x1b[201~'); await pause(350);
  const before = screen.display().split('\n');
  const row = before.findIndex(line => line.includes('DRAFT-A'));
  assert(row > 0);
  const composer = before.slice(row - 1).join('\n');
  // Reworked JediTerm pairs nonzero wheel reports with alternate-scroll arrows.
  send('\x1b[<65;3;2M\x1b[B\x1b[B\x1b[B'); await pause(50);
  for (let index = 0; index < 30; index++) {
    send('\x1b[<64;3;2M'); await pause(16);
  }
  await pause(100);
  assert.equal(screen.display(), before.join('\n'), 'touchpad zero-rotation tail cannot leave the bottom');
  assert(screen.display().includes('HISTORY_TAIL'), 'latest message stays visible after the touchpad tail');
  console.log('PASS bundled UI rejects JediTerm phantom upward wheel reports');
  for (let index = 0; index < 4; index++) {
    send('\x1b[<64;3;2M\x1b[A\x1b[A\x1b[A'); await pause(150);
  }
  assert.notEqual(screen.display().split('\n').slice(0, row - 1).join('\n'), before.slice(0, row - 1).join('\n'));
  assert.equal(screen.display().split('\n').slice(row - 1).join('\n'), composer);
  const scrolled = screen.display();
  send(`\x1b[<65;3;${row + 1}M`); await pause(200);
  assert.equal(screen.display(), scrolled, 'composer wheel cannot scroll either region');
  console.log('PASS bundled UI + ACP history + raw wheel preserve the multiline composer');
  send('\x04'); await pause(200);
  send('\x03'); await pause(200); send('\x03');
  await wait(() => driver.exitCode !== null, 'clean exit');
  assert(raw.includes('\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?1006l\x1b[?1007l'));
  console.log('PASS bundled UI restores pointer modes on exit');
} catch (error) {
  console.error(error.stack);
  console.error(screen.display());
  process.exitCode = 1;
} finally {
  if (driver.exitCode === null) driver.stdin.end();
  console.log(`LOG_DIR ${directory}`);
}