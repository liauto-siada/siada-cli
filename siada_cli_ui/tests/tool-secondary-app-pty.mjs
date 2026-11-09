import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Shipping App + real Python formatters, isolated from user state and model APIs.
const columns = Number(process.env.TOOL_COLUMNS || 80);
const rows = 30;
const temporaryHome = mkdtempSync(join(tmpdir(), 'siada-tool-secondary-'));
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',30,int(os.environ['TOOL_COLUMNS']),0,0))
preload="data:text/javascript,import os from 'node:os';import{syncBuiltinESMExports}from'node:module';os.homedir=()=>process.env.TOOL_TEST_HOME;syncBuiltinESMExports();"
p=subprocess.Popen(['node','--import',preload,os.environ.get('TOOL_BUNDLE','bundle/siada-ui.js'),
 '--siada-path',os.path.abspath('../.venv/bin/python'),
 '--siada-args','tests/fixtures/tool-secondary-acp-server.py','.'],
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
  try:p.wait(timeout=1)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], { cwd: fileURLToPath(new URL('../', import.meta.url)), env: {
  ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
  TOOL_COLUMNS: String(columns), TOOL_TEST_HOME: temporaryHome,
  SIADA_UI_LOG_DIR: join(temporaryHome, 'logs'), SSH_CONNECTION: 'synthetic-tool-secondary',
} });
const screen = new TerminalScreen(rows, columns);
let raw = '';
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.on('data', data => { raw += data.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
async function wait(condition, label) {
  const deadline = Date.now() + 12000;
  while (!condition()) {
    assert(Date.now() < deadline && driver.exitCode === null,
      `Missing ${label}\n${screen.display()}\n${raw.slice(-1200)}`);
    await pause(30);
  }
  await pause(120);
}
async function click(label) {
  const lines = screen.display().split('\n');
  const row = lines.findIndex(line => line.includes(label));
  assert(row >= 0, screen.display());
  const column = lines[row].indexOf(lines[row].trimStart()) + 2;
  send(`\x1b[<0;${column};${row + 1}M`);
  await pause(80);
  send(`\x1b[<0;${column};${row + 1}m`);
  await pause(180);
}
try {
  await wait(() => /Type a message|输入消息/.test(screen.display()), 'input ready');
  const legacy = process.env.TOOL_EXPECT_LEGACY === '1';
  const indices = legacy ? [7, 8] : [1, 2, 3, 4, 5, 6, 7, 8];
  for (const index of indices) {
    send(`\x1b[200~/fixture ${index}\x1b[201~`);
    await pause(350); send('\x1b'); await pause(250); send('\r');
    await wait(() => screen.display().includes(`SCENE_${index}_READY`), `scene ${index}`);
    if (index >= 7) {
      send('\x1b[1;5F'); await pause(250);
      if (legacy) {
        const text = screen.display();
        assert(text.includes('Search for:'), text);
        assert(/[╭╮╰╯│]/.test(text), text);
        console.log(`REPRODUCED legacy multiline Search fallback, scene ${index}`);
        continue;
      }
      const text = screen.display();
      assert(!text.includes('Search for:'), text);
      assert.equal(text.replace(/│|\s/g, '').split(index === 7
        ? 'ToolPromptView|ConversationViewport|secondary|expandable'
        : '(?x)secondary|expandable|memory').length - 1, 1, text);
      assert(text.includes('Search "'), text);
      assert(!text.includes('cwd:'), text);
    }
    const expected = index <= 3 ? `REJECTED_${['CREATE', 'UNDO', 'UPDATE'][index - 1]}`
      : index <= 5 ? 'COMPLETE_ARGUMENT_TAIL' : 'cwd: /tmp/project';
    assert(!screen.display().includes(expected), screen.display());
    await click(index <= 3 ? '.ts' : index <= 5 ? '›' : index === 6
      ? 'Search "FIRST_QUERY' : 'Search "');
    await wait(() => screen.display().includes('⌄'), `mouse expansion ${index}`);
    // An expanded block can exceed the visible rows; verify its actual tail
    // through App's scroll binding, as a user would in a short terminal.
    send('\x1b[1;5F');
    await wait(() => screen.display().includes(expected), `complete tail ${index}`);
    if (index === 4 || index === 5) {
      assert.equal((screen.display().match(/FIRST_ARGUMENT/g) || []).length, 1, screen.display());
      assert(!screen.display().includes('�'));
    }
    send('\x0f');
    await wait(() => screen.display().includes(expected), 'global expansion');
    assert(screen.display().includes(expected), screen.display());
    send('\x0f');
    await wait(() => !screen.display().includes(expected), 'global collapse');
  }
  assert(!/Traceback|Error:/.test(raw), raw.slice(-1200));
  console.log(`PASS ${rows}x${columns}: ${legacy ? 'legacy reproduction' : 'shipping bundle, Python formatters, ACP history/live events, mouse and Ctrl+O across eight tool scenes'}`);
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.once('exit', resolve));
  rmSync(temporaryHome, { recursive: true, force: true });
}