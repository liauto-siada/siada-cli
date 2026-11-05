import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const screen = new TerminalScreen(43, 100);
let raw = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',43,100,0,0))
args=[os.environ['SIADA_TEST_PYTHON'],'-m','siada.entrypoint.launch_ui_with_acp',
 '--workspace',os.environ['SIADA_TEST_WORKSPACE'],'--no-daemon','--no-check-update',
 '--provider','default','--model','gpt-4.1','--set-env','BASE_URL=http://127.0.0.1:9/v1',
 '--set-env','API_KEY=synthetic-ui-startup-key','--set-env','OPENAI_API_KEY=synthetic-ui-startup-key']
p=subprocess.Popen(args,stdin=s,stdout=s,stderr=s,cwd=os.environ['SIADA_TEST_WORKSPACE'],start_new_session=True)
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
`], { env: { ...process.env, PYTHONPATH: process.env.SIADA_TEST_INSTALL, TERM: 'xterm-256color',
  BASE_URL: 'http://127.0.0.1:9/v1', API_KEY: 'synthetic-ui-startup-key',
  OPENAI_API_KEY: 'synthetic-ui-startup-key',
  TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3', SSH_CONNECTION: 'synthetic-installed-ui-test' } });
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
const wait = async (condition, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (!condition()) {
    if (Date.now() > end || driver.exitCode !== null) throw Error(label);
    await pause(50);
  }
};
const command = async text => {
  send(`\x1b[200~${text}\x1b[201~`); await pause(600);
  send('\x1b'); await pause(200);
  send('\r'); await pause(400);
};
try {
  await wait(() => has('Type a message'), 'installed Python launcher ready');
  send('\x1b[200~InstalledProbe7\x1b[201~'); await pause(300);
  assert(has('InstalledProbe7'));
  send('\x04'); await pause(150);
  console.log('PASS installed wheel Python launcher -> bundled UI -> Python ACP -> input probe');
  await command('/status');
  await wait(() => has('Status') || has('Session') || has('WorkSpace'), 'real status response');
  console.log('PASS real Python /status response');
  await command('/help'); await wait(() => has('/goal') || has('/model') || has('/theme'), 'real help response');
  console.log('PASS real Python /help response');
  for (const [cmd, title] of [['/model', 'Switch Model'], ['/effort', 'Reasoning Effort'],
    ['/theme', 'Switch Theme'], ['/task-list', 'Tasks'], ['/plugin', 'Discover']]) {
    await command(cmd);
    await wait(() => has(title) || cmd === '/task-list' && has('No tasks found'),
      cmd + ' original bottom view or empty state', 15000);
    assert(screen.display().split('\n').length <= 43);
    send('\x1b'); await pause(400);
    await wait(() => has('Type a message'), cmd + ' return');
    console.log(`PASS real Python ${cmd} bottom view and return`);
  }
  const readUiLog = () => readFileSync(`${process.env.SIADA_UI_LOG_DIR}/siada-ui.log`, 'utf8');
  const logOffset = readUiLog().length;
  await command('/goal clear');
  await wait(() => readUiLog().slice(logOffset).includes('Received context/goalState notification'),
    'real goal clear notification');
  await pause(200);
  assert(!has('› Goal'));
  assert(has('Goal cleared.'));
  console.log('PASS real Python /goal clear without a model request');
  send('\x03'); await pause(150); send('\x03');
  await wait(() => driver.exitCode !== null, 'installed exit', 10000);
  assert(raw.includes('\x1b[?1049l'));
  console.log('PASS installed process exit and terminal restoration');
} catch (error) {
  console.error(error.stack); console.error(screen.display()); process.exitCode = 1;
} finally {
  if (driver.exitCode === null) driver.stdin.end('quit\n');
}