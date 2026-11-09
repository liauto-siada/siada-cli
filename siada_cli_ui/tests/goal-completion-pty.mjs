import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import stringWidth from 'string-width';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const configDir = mkdtempSync(join(tmpdir(), 'siada-goal-completion-'));
const screen = new TerminalScreen(43, 100);
const objective = 'Verify compatibility and installation evidence for Windows';
let raw = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys,shutil
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',43,100,0,0))
p=subprocess.Popen(['node','bundle/siada-ui.js','--siada-path',shutil.which('node'),
 '--siada-args','tests/fixtures/three-pane-acp-server.mjs',
 '--initial-prompt',os.environ['SIADA_TEST_INITIAL_PROMPT'],'.'],
 stdin=s,stdout=s,stderr=s,start_new_session=True)
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
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
    SIADA_UI_CONFIG_DIR: configDir, SIADA_UI_LOG_DIR: configDir, SSH_CONNECTION: 'synthetic-goal-completion',
    SIADA_TEST_INITIAL_PROMPT: `/goal ${objective}` },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
async function wait(condition, label) {
  const deadline = Date.now() + 10000;
  while (!condition()) {
    if (Date.now() > deadline || driver.exitCode !== null) throw Error(label);
    await pause(30);
  }
}
async function command(text) {
  send(`\x1b[200~${text}\x1b[201~`); await pause(350);
  if (text.startsWith('/')) { send('\x1b'); await pause(200); }
  send('\r'); await pause(180);
}
async function selectText(text) {
  const lines = screen.display().split('\n');
  const row = lines.findLastIndex(line => line.includes(text));
  assert(row >= 0, `Missing selectable text: ${text}`);
  const x = stringWidth(lines[row].slice(0, lines[row].indexOf(text))) + 1;
  const start = raw.length;
  send(`\x1b[<0;${x};${row + 1}M`); await pause(60);
  send(`\x1b[<32;${x + stringWidth(text)};${row + 1}M`); await pause(100);
  send(`\x1b[<0;${x + stringWidth(text)};${row + 1}m`);
  const encoded = Buffer.from(text).toString('base64');
  await wait(() => raw.slice(start).includes(`\x1b]52;c;${encoded}\x07`), `copy ${text}`);
}
try {
  await wait(() => has('Type a message'), 'ready');
  await wait(() => has('› Goal'), 'initial prompt submitted through the production entry point');
  console.log('PASS: initial slash command is submitted automatically and the UI stays open.');
  const liveRow = screen.display().split('\n').find(line => line.includes('› Goal'));
  assert(liveRow?.includes('…') && !liveRow.includes(objective));
  await command('Complete the synthetic Goal check');
  await wait(() => has('Goal Achieved') && has('Plan completed'), 'completion records');
  await wait(() => has('Achieved (complete · 3s · 1 turn)'), 'completed Goal bar stays visible');
  send('\x1b[200~Mouse draft 中文\x1b[201~'); await pause(350);
  await selectText('中文');
  await selectText('Final wire response.');
  assert(has('Mouse draft 中文'), 'returning to messages preserves the draft');
  send('\x1b'); await pause(100); send('\x04'); await pause(150);
  console.log('PASS: mouse selection returns from the composer to messages with the completed Goal bar visible.');
  send('\x1b[200~/mo\x1b[201~');
  await wait(() => has('Suggestions'), 'command suggestions visible');
  const visibleMessage = screen.display().split('\n').map(line => line.trim())
    .find(line => line.startsWith('Stream line'));
  assert(visibleMessage, 'message text is visible outside the command popup');
  await selectText(visibleMessage);
  assert(has('Suggestions') && has('/mo'), 'message selection preserves command completion');
  send('\x1b'); await pause(100); send('\x1b'); await pause(150); send('\x04'); await pause(150);
  console.log('PASS: visible messages remain selectable while command suggestions are open.');
  for (const action of ['Plan completed', 'Goal Achieved']) {
    assert(new RegExp(`\\x1b\\[38;2;6;182;212m[●✓] (?:\\x1b\\[[0-9;]*m)*${action}`).test(raw),
      `${action} must use the tool action color`);
  }
  const lines = screen.display().split('\n');
  const row = lines.findIndex(line => line.includes('Goal Achieved'));
  const summary = lines[row].trimStart().split(/\s{3,}/)[0];
  assert(stringWidth(summary) <= 48);
  assert(lines[row].includes('…') && !lines[row].includes('check'));
  const x = lines[row].indexOf('Goal') + 1;
  send(`\x1b[<0;${x};${row + 1}M`); await pause(80);
  send(`\x1b[<0;${x};${row + 1}m`);
  await wait(() => has(objective), 'expanded full objective');
  send('\x1b[<65;10;30M'); await pause(150);
  send('\x1b[<65;10;30M');
  await wait(() => has('Wire goal completed.'), 'expanded verification reason');
  console.log('PASS: live Goal and completion summaries are short; Plan and Goal actions are blue; full details expand.');
  send('\x1b'); await pause(150);
  await command('/fixture input');
  await wait(() => has('Wire confirmation'), 'interactive input requested');
  send('\x1b[200~Confirm draft 中文\x1b[201~'); await pause(350);
  await selectText('中文');
  await selectText('Final wire response.');
  assert(has('Confirm draft 中文'), 'reading messages preserves pending confirmation');
  send('\x1b'); await pause(100);
  const firstStreamLine = () => screen.display().split('\n').find(line => line.includes('Stream line'));
  const beforeScroll = firstStreamLine();
  send('\x1b[<64;10;10M');
  await wait(() => firstStreamLine() !== beforeScroll, 'mouse scroll works during confirmation');
  send('\r');
  await wait(() => !has('Wire confirmation') && has('Type a message'), 'confirmation accepted');
  send('\x1b[1;5F');
  await wait(() => has('Interactive wire reply: Confirm draft 中文'), 'confirmation still submits normally');
  console.log('PASS: mouse selection returns to messages while interactive input is pending.');
  send('\x03'); await pause(150); send('\x03');
  await wait(() => driver.exitCode !== null, 'exit');
  assert(raw.includes('\x1b[?1049l'));
  console.log('PASS: terminal modes restored on exit.');
} catch (error) {
  console.error(error.stack); console.error(screen.display()); process.exitCode = 1;
} finally {
  if (driver.exitCode === null) driver.stdin.end('quit\n');
  await new Promise(resolve => { if (driver.exitCode !== null) resolve(); else driver.once('exit', resolve); });
  rmSync(configDir, { recursive: true, force: true });
}