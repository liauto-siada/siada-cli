import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const root = fileURLToPath(new URL('../', import.meta.url));
const rows = Number(process.env.PICKER_TEST_ROWS || 30);
const columns = Number(process.env.PICKER_TEST_COLUMNS || 100);
const state = mkdtempSync(join(tmpdir(), 'siada-picker-pty-'));
const sessions = join(state, '.siada-cli/data/tmp', createHash('sha256').update('.').digest('hex'), 'sessions');
for (let i = 0; i < 40; i++) {
  const directory = join(sessions, `session-${i}`);
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, 'metadata.json'), JSON.stringify({
    created_at: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z`,
    last_updated: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z`,
    message_count: 10, first_user_message: `Saved session ${i} 中文 ${'long title '.repeat(10)}`,
  }));
}
let screen = new TerminalScreen(rows, columns);
let raw = '', stderr = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['PICKER_TEST_ROWS']),int(os.environ['PICKER_TEST_COLUMNS']),0,0))
args=[os.environ['PICKER_TEST_NODE'],'--import','./tests/fixtures/picker-test-home.mjs',
 'bundle/siada-ui.js','--siada-path',os.environ['PICKER_TEST_NODE'],
 '--siada-args','tests/fixtures/picker-acp-server.mjs','--log-level','debug','.']
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
    if line.startswith(b'resize '):
     _,r,c=line.split()
     fcntl.ioctl(m,termios.TIOCSWINSZ,struct.pack('HHHH',int(r),int(c),0,0))
     os.killpg(p.pid,signal.SIGWINCH)
    elif line:os.write(m,bytes.fromhex(line.decode()))
except EOFError:pass
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], {
  cwd: root,
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
    PICKER_TEST_ROWS: String(rows), PICKER_TEST_COLUMNS: String(columns), PICKER_TEST_NODE: process.execPath,
    PICKER_TEST_HOME: state, SIADA_UI_LOG_DIR: join(state, 'logs'), SSH_CONNECTION: 'synthetic-picker-pty' },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', chunk => { raw += chunk; screen.feed(chunk); });
driver.stderr.on('data', chunk => { stderr += chunk.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const wait = async (predicate, label, timeout = 12000) => {
  const end = Date.now() + timeout;
  while (!predicate()) {
    assert(Date.now() < end && driver.exitCode === null, `Missing ${label}\n${screen.display()}\n${stderr}`);
    await pause(40);
  }
};
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const key = async sequence => { send(sequence); await pause(100); };
const submit = async command => {
  send(command); await pause(500); await key('\x1b'); await key('\r');
};
const input = () => /Type a message|输入消息/.test(screen.display());
const evidence = [];
async function check(title, hint) {
  let display = screen.display();
  assert(display.includes(title) && display.includes(hint), `Picker is clipped: ${title}\n${display}`);
  const historyLine = lines => lines.findIndex(line => /Picker history (stays visible|question)|^> \//.test(line));
  if (historyLine(display.split('\n')) < 0) {
    for (let i = 0; i < 12 && historyLine(display.split('\n')) < 0; i++) {
      await key('\x1b[<65;3;4M'); display = screen.display();
    }
    assert(display.includes(title) && display.includes(hint), 'history wheel must not move the picker');
  }
  assert(historyLine(display.split('\n')) >= 0, `Picker replaced history: ${title}\n${display}`);
  const lines = display.split('\n');
  assert(lines.findIndex(line => line.includes(title)) > historyLine(lines),
    'picker must stay below history');
  evidence.push({ title, screen: display });
}
try {
  await wait(() => input() && screen.display().includes('Picker history stays visible.'), 'banner and history');
  const bootLog = readFileSync(join(state, 'logs/siada-ui.log'), 'utf8');
  assert(bootLog.includes('"version": "1.7.37-test"') && raw.includes('▆') && !raw.includes(' vdev'),
    'bundle bootstraps with backend banner');
  await submit('/model'); await wait(() => screen.display().includes('Switch Model'), 'model picker');
  await check('Switch Model', 'Enter confirm');
  for (let i = 0; i < 40; i++) await key('\x1b[B');
  await wait(() => screen.display().includes('› model-39'), 'last model');
  await check('Switch Model', 'Esc back');
  await key('\r'); await wait(input, 'model confirmation'); assert(screen.display().includes('model-39'), 'selected model is applied');

  await submit('/effort'); await wait(() => screen.display().includes('Reasoning Effort'), 'effort picker');
  if (columns >= 60) {
    await wait(() => screen.display().split('\n').some(line => /[*•·]/.test(line.slice(43))),
      'effort particle canvas');
  }
  await check('Reasoning Effort', '←→ select'); await key('\x1b[C'); await key('\r'); await wait(input, 'effort confirmation');
  assert(screen.display().includes('high'), 'effort choice reaches backend');

  await submit('/theme'); await wait(() => screen.display().includes('Switch Theme'), 'theme picker');
  await check('Switch Theme', 'Enter confirm'); await key('\x1b[B'); await key('\r'); await wait(input, 'theme confirmation');
  await submit('/theme'); await wait(() => /light.*\(current\)/.test(screen.display()), 'saved theme');
  await check('Switch Theme', 'Esc back'); await key('\x1b'); await wait(input, 'theme cancel');

  await submit('/editor'); await wait(() => screen.display().includes('Editor Selection'), 'editor picker');
  await check('Editor Selection', 'Enter confirm'); await key('\x1b'); await key('\x15'); await wait(input, 'editor cancel');
  await submit('/statusbar'); await wait(() => screen.display().includes('Status Bar Items'), 'status picker');
  await check('Status Bar Items', 'Space/Enter'); await key(' '); await key('\r');
  assert(screen.display().includes('Status Bar Items'), 'multi-select stays open'); await key('\x1b'); await key('\x15'); await wait(input, 'status cancel');

  await submit('/task-list'); await wait(() => screen.display().includes('Pending Tasks'), 'task picker');
  for (let i = 0; i < 40; i++) await key('\x1b[B');
  await wait(() => /›.*Task 39/.test(screen.display()), 'last task'); await check('Pending Tasks', 'Enter execute');
  await key('\x1b'); await wait(input, 'task cancel');

  await submit('/plugin'); await wait(() => screen.display().includes('Plugins'), 'plugin picker');
  await check('Plugins', 'Esc back'); await key('\t');
  for (let i = 0; i < 40; i++) await key('\x1b[B');
  await wait(() => screen.display().includes('› [x] skill-39'), 'last grouped skill'); await check('Plugins', 'Esc back');
  await key('\x1b'); await wait(input, 'plugin cancel');

  await submit('/resume'); await wait(() => screen.display().includes('Resume Session'), 'session picker');
  await check('Resume Session', 'Enter resume'); await key('\x1b[6~');
  await check('Resume Session', 'Esc back'); await key('/'); await pause(150);
  await check('Resume Session', 'Esc back'); await key('\x1b'); await key('\x1b'); await wait(input, 'session cancel');

  await submit('/configure'); await wait(() => screen.display().includes('Sign In'), 'configure picker');
  await check('Sign In', 'Esc back'); await key('\r');
  await wait(() => screen.display().includes('Choose Provider'), 'provider picker');
  for (let i = 0; i < 40; i++) await key('\x1b[B');
  await wait(() => screen.display().includes('› Provider 39'), 'last provider'); await check('Configure API Key', 'Esc back');
  await key('\r'); await wait(() => screen.display().includes('Choose Model'), 'wizard model');
  await check('Provider 39', 'Esc back'); await key('\x1b'); await key('\x1b'); await key('\x1b'); await wait(input, 'configure cancel');

  await submit('/model'); await wait(() => screen.display().includes('Switch Model'), 'picker before resize');
  for (const [resizedRows, resizedColumns] of [[24, 48], [32, 120]]) {
    if (screen.rows === resizedRows && screen.columns === resizedColumns) continue;
    screen = new TerminalScreen(resizedRows, resizedColumns);
    driver.stdin.write(`resize ${resizedRows} ${resizedColumns}\n`);
    await wait(() => screen.display().includes('Switch Model') && screen.display().includes('› model-39'),
      `resized ${resizedRows}x${resizedColumns} picker`);
    await check('Switch Model', 'Esc back');
  }
  await key('\x1b'); await wait(input, 'resize cancel');

  await submit('/language'); await wait(() => screen.display().includes('Interface language'), 'language picker');
  await check('Interface language', 'Enter confirm'); await key('\x1b[B'); await key('\r');
  await wait(() => screen.display().includes('输入消息'), 'Chinese input');
  await submit('/theme'); await wait(() => screen.display().includes('切换主题'), 'Chinese picker');
  await check('切换主题', 'Enter 确定'); await key('\x1b');
  assert(!/Traceback|TypeError|ReferenceError/.test(raw + stderr), 'no runtime errors');
  writeFileSync(join(state, 'screens.json'), JSON.stringify(evidence, null, 2));
  writeFileSync(join(state, 'terminal.raw'), raw);
  console.log(`PASS ${rows}x${columns}: 10 command pickers, selection, cancellation, scrolling, both themes and languages`);
  console.log(`EVIDENCE: ${state}`);
} catch (error) {
  writeFileSync(join(state, 'terminal.raw'), raw);
  writeFileSync(join(state, 'failure-screen.txt'), screen.display());
  console.error(error.stack); console.error(`EVIDENCE: ${state}`); process.exitCode = 1;
} finally {
  if (driver.exitCode === null) {
    driver.stdin.end('quit\n');
    await new Promise(resolve => driver.once('exit', resolve));
  }
}