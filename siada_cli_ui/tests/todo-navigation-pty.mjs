import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const rows = Number(process.env.DEMO_ROWS || 24);
const columns = Number(process.env.DEMO_COLUMNS || 80);
const screen = new TerminalScreen(rows, columns);
const fixture = `
import React, { useState } from 'react';
import { render } from '@jrichman/ink';
import { MainLayout } from './dist/components/layouts/MainLayout.js';
import { AppProvider } from './dist/store/context.js';
import { KeypressProvider } from './dist/contexts/KeypressContext.js';
import { useKeypress } from './dist/hooks/useKeypress.js';
import { createPresentationDemoState } from './examples/three-pane-demo-data.mjs';
function Fixture() {
  const [current, setCurrent] = useState(3);
  useKeypress(key => { if (key.name === 'p') setCurrent(6); });
  const state = createPresentationDemoState();
  const tasks = Array.from({ length: 8 }, (_, index) => ({
    content: 'Task ' + (index + 1),
    status: index < current ? 'completed' : index === current ? 'in_progress' : 'pending',
  }));
  return React.createElement(MainLayout, { ...state, todoItems: tasks, goalState: null,
    demoPresentation: true, workingDir: '.', onSendMessage: () => {},
    loading: true, activeStep: 'reasoning' });
}
render(React.createElement(KeypressProvider, null,
  React.createElement(AppProvider, null, React.createElement(Fixture))),
  { alternateBuffer: true, incrementalRendering: true, patchConsole: false, exitOnCtrlC: false });
`;
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['DEMO_ROWS']),int(os.environ['DEMO_COLUMNS']),0,0))
p=subprocess.Popen(['node','--input-type=module','-e',os.environ['TODO_FIXTURE']],stdin=s,stdout=s,stderr=s,start_new_session=True)
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
  ...process.env, DEMO_ROWS: String(rows), DEMO_COLUMNS: String(columns), TODO_FIXTURE: fixture,
  TERM: 'xterm-256color', FORCE_COLOR: '3', SSH_CONNECTION: 'synthetic-todo-navigation',
  SIADA_UI_LOG_DIR: `/tmp/siada-todo-navigation-${rows}x${columns}-${Date.now()}`,
} });
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => screen.feed(data));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
const wait = async (condition, label) => {
  const deadline = Date.now() + 9000;
  while (!condition()) {
    if (Date.now() > deadline || driver.exitCode !== null) throw Error(`${label}\n${screen.display()}`);
    await pause(30);
  }
};
const key = async text => { send(text); await pause(180); };
const click = async text => {
  const lines = screen.display().split('\n');
  const y = lines.findIndex(line => line.includes('› Todo'));
  const x = lines[y].indexOf(text) + 1;
  assert(x > 0 && y >= 0);
  await key(`\x1b[<0;${x};${y + 1}M`);
  await key(`\x1b[<0;${x};${y + 1}m`);
};
try {
  await wait(() => has('Todo 3/8') && has('Thinking'), 'startup');
  const lines = screen.display().split('\n');
  assert.equal(lines.find(line => line.includes('› Todo')).indexOf('›'),
    lines.find(line => line.includes('Thinking')).indexOf('◉'), 'Todo aligns with thinking');
  await click('Todo');
  assert(!has('Todo ·'), 'title does not open a panel');
  await key('\t');
  await wait(() => has('▶ ◐ Task 4'), 'Tab focuses the running task');
  await key('\r');
  assert(!has('Todo ·'), 'Enter stays in place');
  await key('\x1b[A');
  assert(has('▶ ✓ Task 3'));
  await key('\x1b[B');
  assert(has('▶ ◐ Task 4'));
  await key('\x1b');
  assert(!has('▶ '));
  await key('p');
  await wait(() => has('◐ Task 7'), 'unfocused Todo follows progress');
  assert(!has('Task 4'));
  await click('▲');
  await wait(() => has('▶ ✓ Task 6') && has('Task 5'), 'click scrolls up one row');
  await click('▼');
  await wait(() => has('▶ ◐ Task 7') && !has('Task 5'), 'click scrolls down one row');
  await click('▼');
  assert(has('▶ ◐ Task 7') && !has('Task 5'), 'disabled down arrow stays at the end');
  await key('\x1b');
  assert(has('◐ Task 7') && !has('▶ '));
  assert(!has('Copied'), 'buttons do not select text');
  console.log(`PASS ${columns}×${rows}: alignment, Tab/↑/↓/Enter/Esc, progress following, mouse scroll and bounds`);
  console.log(screen.display().split('\n').filter(line => /Todo|Task [5-8]|Thinking/.test(line)).join('\n'));
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.exitCode === null ? driver.once('exit', resolve) : resolve());
}