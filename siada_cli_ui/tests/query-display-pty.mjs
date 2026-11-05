import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Exercise the compiled production components and real input parser in a PTY.
const rows = 24;
const columns = Number(process.env.QUERY_COLUMNS || 80);
const source = `
import React, {useState} from 'react';
import {Box, Text, render} from '@jrichman/ink';
import {ConversationViewport} from './dist/components/Chat/ConversationViewport.js';
import {KeypressProvider} from './dist/contexts/KeypressContext.js';
import {useKeypress} from './dist/hooks/useKeypress.js';
const query = '终端鼠标选择双击选词拖动选区边界行为中文查询验证';
const cases = [
  ['Searching memory: q7needle'],
  ['Fact memory [search/project] q7needle'],
  ['Search for: q7needle in src with file pattern *.ts'],
  ['Web search: search: q7needle'],
  ['Searching memory: q7needle', 'Searching memory: q7needle'],
  ['Searching memory: ' + query],
  ['Search for: timeout: in src with file pattern *.tsx in /tmp/project',
   'Search for: ● in src with file pattern *.{ts,tsx} in /tmp/project'],
  ['Read the file \`/tmp/project/a.ts\`',
   'Search for: q7needle in src with file pattern *.ts in /tmp/project',
   'Run the following command:\\n\`\`\`bash\\npwd\\n\`\`\`\\ntimeout:60s'],
  ['Search for: ' + query + ' in src with file pattern *.ts in /tmp/project'],
];
function App() {
  const [index, setIndex] = useState(0);
  const [collapsed, setCollapsed] = useState(true);
  const [presentation, setPresentation] = useState(false);
  useKeypress(key => {
    if (/^[1-9]$/.test(key.name)) {setIndex(Number(key.name) - 1); setCollapsed(true);}
    if (key.ctrl && key.name === 'o') setCollapsed(value => !value);
    if (key.name === 'p') setPresentation(value => !value);
  });
  const messages = cases[index].map((content, i) => ({
    id: index + '-' + i, type: 'agent', content, author: 'Synthetic',
    timestamp: '2026-01-01T00:00:00Z', metadata: {subtype: 'tool_use', streamEnd: true},
  }));
  return React.createElement(Box, {height: 23, width: ${columns}, flexDirection: 'column'},
    React.createElement(ConversationViewport, {messages, width: ${columns}, height: 21, isCollapsed: collapsed, presentation}),
    React.createElement(Text, null, 'CASE ' + (index + 1) + ' ' + (collapsed ? 'collapsed' : 'expanded') + ' ' + (presentation ? 'production' : 'interactive')));
}
render(React.createElement(KeypressProvider, null, React.createElement(App)),
  {patchConsole: false, exitOnCtrlC: false, maxFps: 0});
`;
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',24,int(os.environ['QUERY_COLUMNS']),0,0))
p=subprocess.Popen(['node','--input-type=module','-e',sys.argv[1]],stdin=s,stdout=s,stderr=s,start_new_session=True)
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
`, source], { cwd: fileURLToPath(new URL('../', import.meta.url)), env: {
  ...process.env, QUERY_COLUMNS: String(columns), TERM: 'xterm-256color',
  TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3', SIADA_UI_LOG_DIR: `/tmp/siada-query-pty-${Date.now()}`,
} });
const screen = new TerminalScreen(rows, columns);
let raw = '';
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.on('data', data => { raw += data.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const wait = async marker => {
  const deadline = Date.now() + 8000;
  while (!screen.display().includes(marker)) {
    assert(Date.now() < deadline && driver.exitCode === null, `Missing ${marker}\n${screen.display()}\n${raw.slice(-1000)}`);
    await pause(30);
  }
  await pause(100);
};
const checkCount = count => {
  assert.equal((screen.display().match(/q7needle/g) || []).length, count, screen.display());
  assert(!screen.display().includes('query:'), screen.display());
};
try {
  await wait('CASE 1 collapsed interactive');
  for (let index = 1; index <= 5; index++) {
    send(String(index)); await wait(`CASE ${index} collapsed interactive`);
    checkCount(index === 5 ? 2 : 1);
    send('\x0f'); await wait(`CASE ${index} expanded interactive`);
    checkCount(index === 5 ? 2 : 1);
    if (index === 2) assert(screen.display().includes('target: project'));
    send('\x0f'); await wait(`CASE ${index} collapsed interactive`);
    checkCount(index === 5 ? 2 : 1);
  }
  send('p'); await wait('CASE 5 collapsed production');
  checkCount(2);
  for (let index = 1; index <= 4; index++) {
    send(String(index)); await wait(`CASE ${index} collapsed production`);
    checkCount(1);
  }
  send('6'); await wait('CASE 6 collapsed production');
  const query = '终端鼠标选择双击选词拖动选区边界行为中文查询验证';
  assert.equal(screen.display().replace(/\s/g, '').split(query).length - 1, 1, screen.display());
  assert(!screen.display().includes('�'));
  send('7'); await wait('CASE 7 collapsed production');
  assert(screen.display().includes('├─ Search "timeout:" in src ›'), screen.display());
  assert(screen.display().includes('└─ Search "●" in src ›'), screen.display());
  assert(!screen.display().includes('cwd:'), screen.display());
  const lines = screen.display().split('\n');
  const row = lines.findIndex(line => line.includes('Search "timeout:"'));
  const x = lines[row].indexOf('Search') + 2;
  send(`\x1b[<0;${x};${row + 1}M`);
  send(`\x1b[<0;${x};${row + 1}m`);
  await wait('cwd: /tmp/project');
  assert.equal((screen.display().match(/cwd:/g) || []).length, 1, screen.display());
  send('\x0f'); await wait('CASE 7 expanded production');
  assert.equal((screen.display().match(/cwd:/g) || []).length, 2, screen.display());
  send('\x0f'); await wait('CASE 7 collapsed production');
  assert(!screen.display().includes('cwd:'), screen.display());
  console.log(screen.display().split('\n').filter(line => line.trim()).join('\n'));
  send('8'); await wait('CASE 8 collapsed production');
  checkCount(1);
  assert(screen.display().includes('├─ Search "q7needle" in src ›'), screen.display());
  assert(screen.display().includes('pwd'), screen.display());
  // Single-line commands show their body directly in the production tree.
  assert(!screen.display().includes('timeout:60s'), screen.display());
  send('9'); await wait('CASE 9 collapsed production');
  assert.equal(screen.display().replace(/\s/g, '').split(query).length - 1, 1, screen.display());
  assert(!screen.display().includes('cwd:'), screen.display());
  send('\x0f'); await wait('CASE 9 expanded production');
  assert(screen.display().includes('cwd: /tmp/project'), screen.display());
  assert.equal(screen.display().replace(/\s/g, '').split(query).length - 1, 1, screen.display());
  console.log(screen.display().split('\n').filter(line => line.trim()).join('\n'));
  assert(!/Error:|Traceback/.test(raw), raw.slice(-1000));
  console.log(`PASS ${rows}x${columns}: query count, Ctrl+O, mouse disclosure, mixed calls, compact Search and Chinese wrapping`);
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.once('exit', resolve));
}