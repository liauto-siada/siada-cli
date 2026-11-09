import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Exercise the built App, streaming/history ACP routes and real keyboard input.
const rows = 32;
const columns = Number(process.env.MARKDOWN_COLUMNS || 100);
const bundle = process.env.MARKDOWN_BUNDLE || 'bundle/siada-ui.js';
const logDirectory = mkdtempSync(join(tmpdir(), 'siada-markdown-logs-'));
const configDirectory = mkdtempSync(join(tmpdir(), 'siada-markdown-config-'));
const screen = new TerminalScreen(rows, columns);
let raw = '';
let stderr = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys,shutil
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',32,int(os.environ['MARKDOWN_COLUMNS']),0,0))
p=subprocess.Popen(['node',os.environ['MARKDOWN_BUNDLE'],'--siada-path',shutil.which('node'),
 '--siada-args','tests/fixtures/three-pane-acp-server.mjs','--log-level','debug','.'],
 stdin=s,stdout=s,stderr=s,start_new_session=True)
pending=b''
try:
 while True:
  ready,_,_=select.select([m,sys.stdin.fileno()],[],[],0.05)
  if p.poll() is not None and m not in ready:break
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
except EOFError:
 pass
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=1)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m);os.close(s)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
    MARKDOWN_COLUMNS: String(columns), MARKDOWN_BUNDLE: bundle,
    SIADA_UI_LOG_DIR: logDirectory, SIADA_UI_CONFIG_DIR: configDirectory,
    SSH_CONNECTION: 'synthetic-markdown-check' },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.on('data', data => { stderr += data.toString(); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
async function wait(condition, label) {
  const end = Date.now() + 12000;
  while (!condition()) {
    if (Date.now() > end) throw Error(`Missing ${label}\n${screen.display()}\n${stderr}`);
    await pause(30);
  }
}
async function command(text) {
  send(`\x1b[200~${text}\x1b[201~`);
  await pause(350);
  send('\x1b');
  await pause(250);
  send('\r');
}
function checkTail(label) {
  const output = screen.display();
  for (const text of ['MARKDOWN_TAIL', 'BOLD_TAIL', 'INLINE_TAIL', 'LIST_TAIL']) {
    assert(output.includes(text), `${label}: missing ${text}\n${output}`);
  }
  for (const text of ['## MARKDOWN_TAIL', '**BOLD_TAIL**', '`INLINE_TAIL`', '**LIST_TAIL**']) {
    assert(!output.includes(text), `${label}: raw Markdown ${text}\n${output}`);
  }
  assert(output.includes('## CODE_TAIL'), `${label}: code content must remain literal\n${output}`);
  assert(!output.includes('\uFFFD'), `${label}: broken Unicode`);
}
function checkDiagram(label) {
  const output = screen.display();
  for (const text of ['Parent', 'Child', 'MERMAID_REQUEST', 'MERMAID_RESULT', 'MERMAID_COMPLETE', '┌']) {
    assert(output.includes(text), `${label}: missing ${text}\n${output}`);
  }
  for (const text of ['sequenceDiagram', 'participant A', 'A->>B:', '%% MERMAID_PENDING']) {
    assert(!output.includes(text), `${label}: diagram fell back to source\n${output}`);
  }
}
try {
  await wait(() => /Type a message|输入消息/.test(screen.display()), 'ready');
  await command('/fixture markdown');
  await wait(() => screen.display().includes('## CODE_TAIL'), 'unfinished code');
  assert(!screen.display().includes('MARKDOWN_TAIL'), 'unfinished stream is observable');
  await wait(() => screen.display().includes('LIST_TAIL'), 'closed stream');
  await pause(200);
  checkTail('streamed answer');
  send('\x0f');
  await pause(350);
  checkTail('Ctrl+O');
  await command('/theme light');
  await pause(350);
  checkTail('light theme');
  await command('/fixture markdown-history');
  await wait(() => screen.display().includes('HISTORY_TAIL'), 'history restoration');
  await pause(350);
  checkTail('restored history');
  await command('/fixture mermaid');
  await wait(() => screen.display().includes('%% MERMAID_PENDING'), 'unfinished Mermaid code');
  assert(!screen.display().includes('MERMAID_COMPLETE'), 'unfinished Mermaid stream is observable');
  await wait(() => screen.display().includes('MERMAID_COMPLETE'), 'closed Mermaid stream');
  await pause(200);
  checkDiagram('streamed oversized diagram');
  send('\x0f');
  await pause(350);
  checkDiagram('diagram after Ctrl+O');
  await command('/fixture mermaid-history');
  await wait(() => screen.display().includes('MERMAID_HISTORY'), 'Mermaid history restoration');
  await pause(350);
  checkDiagram('restored oversized diagram');
  assert(!/Error:|Traceback/.test(raw + stderr), (raw + stderr).slice(-1200));
  console.log(screen.display().split('\n').filter(line => line.trim()).join('\n'));
  console.log(`PASS ${rows}x${columns}: oversized code and Mermaid blocks, unfinished and closed streaming, Ctrl+O, light theme, restored history`);
} finally {
  driver.stdin.end('quit\n');
  await new Promise(resolve => driver.once('exit', resolve));
  console.log(`LOG_DIR: ${logDirectory}`);
}