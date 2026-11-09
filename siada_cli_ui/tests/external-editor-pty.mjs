import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

// Run the production entry point with an offline ACP server and a real Vim.
const rows = Number(process.env.TEST_ROWS || 24);
const columns = Number(process.env.TEST_COLUMNS || 80);
const directory = mkdtempSync(join(tmpdir(), 'siada-editor-pty-'));
let screen = new TerminalScreen(rows, columns);
let alternate = false;
let pending = '';
let raw = '';
let ttyModes = null;
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,signal,sys,json
pid,m=pty.fork()
if pid==0:
 fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['TEST_ROWS']),int(os.environ['TEST_COLUMNS']),0,0))
 entry=['bundle/siada-ui.js'] if os.environ.get('TEST_BUNDLE') else ['--import','tsx','src/cli.ts']
 os.execvp('node',['node']+entry+['--siada-path','node',
   '--siada-args','tests/fixtures/three-pane-acp-server.mjs','.'])
pending=b''
try:
 while True:
  ready,_,_=select.select([m,sys.stdin.fileno()],[],[],0.05)
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
    if line==b'modes':
     flags=termios.tcgetattr(m)[3]
     print(json.dumps({'canonical':bool(flags&termios.ICANON),'echo':bool(flags&termios.ECHO),
       'signals':bool(flags&termios.ISIG)}),file=sys.stderr,flush=True)
     continue
    if line:os.write(m,bytes.fromhex(line.decode()))
except EOFError:pass
finally:
 ended,_=os.waitpid(pid,os.WNOHANG)
 if not ended:
  try:os.kill(pid,signal.SIGTERM)
  except ProcessLookupError:pass
  os.waitpid(pid,0)
 os.close(m)
`], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  env: { ...process.env, TEST_ROWS: String(rows), TEST_COLUMNS: String(columns),
    TERM: 'xterm-256color', TERM_PROGRAM: process.env.TEST_TERM_PROGRAM || 'Apple_Terminal',
    VISUAL: '/usr/bin/vim', EDITOR: '/usr/bin/vim', FORCE_COLOR: '3',
    SIADA_UI_CONFIG_DIR: directory, SIADA_UI_LOG_DIR: directory,
    SSH_CONNECTION: 'synthetic-editor-selection-test' },
});
driver.stderr.setEncoding('utf8');
driver.stderr.on('data', data => {
  for (const line of data.trim().split('\n')) {
    if (line.startsWith('{"canonical"')) ttyModes = JSON.parse(line);
    else console.error(line);
  }
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => {
  raw += data;
  pending += data;
  // Model DEC 1049 switches separately: the existing screen helper only models
  // a single buffer. Clearing on entry also detects stale incremental frames.
  const switches = /\x1b\[\?1049([hl])/g;
  let start = 0;
  for (const match of pending.matchAll(switches)) {
    screen.feed(pending.slice(start, match.index));
    alternate = match[1] === 'h';
    screen = new TerminalScreen(rows, columns);
    start = match.index + match[0].length;
  }
  const tail = pending.slice(start);
  const partial = tail.lastIndexOf('\x1b');
  if (partial >= 0 && /^\x1b(?:\[(?:\?(?:1(?:0(?:4(?:9)?)?)?)?)?)?$/.test(tail.slice(partial))) {
    screen.feed(tail.slice(0, partial));
    pending = tail.slice(partial);
  } else {
    screen.feed(tail);
    pending = '';
  }
});
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
const wait = async (predicate, label) => {
  const deadline = Date.now() + 10000;
  while (!predicate()) {
    if (Date.now() > deadline) throw Error(`${label}\n${screen.display()}`);
    await pause(25);
  }
};
const open = async () => {
  const offset = raw.length;
  send('\x18');
  await wait(() => raw.slice(offset).includes('buffer.txt'), 'Vim opened');
  await pause(200);
};
const quit = async command => {
  send('\x1b'); await pause(80);
  send(command); await pause(100);
  send('\r');
  await pause(500);
};
try {
  await wait(() => has('Type a message'), 'UI ready');
  send('\x1b[200~/fixture error\x1b[201~'); await pause(600);
  send('\x1b'); await pause(200); send('\r');
  await wait(() => has('Recoverable wire error'), 'History ready');
  send('\x1b[200~original draft\x1b[201~'); await pause(250);
  await open();
  send('gg0Cedited draft'); await pause(150);
  await quit(':wq');
  assert(alternate, 'Vim return must restore the UI alternate buffer');
  await wait(() => has('edited draft') && has('Recoverable wire error'), 'Saved draft and history restored');
  send('!'); await pause(200);
  assert(has('edited draft!'), 'Raw keyboard input works immediately after Vim');
  const before = screen.display();
  await open();
  send('gg0Cdiscard this'); await pause(150);
  await quit(':q!');
  assert(alternate, 'Cancel must restore alternate buffer');
  assert.equal(screen.display(), before, 'Cancel repaints the unchanged UI and retains the draft');
  await open(); await quit(':wq');
  assert.equal(screen.display(), before, 'Repeated no-op edit restores every row');
  driver.stdin.write('modes\n');
  await wait(() => ttyModes !== null, 'TTY modes received');
  assert.deepEqual(ttyModes, { canonical: false, echo: false, signals: false });

  // Vim's file newline must not accumulate, or consume an intentional trailing
  // draft newline. Exercise this through the real paste and buffer path.
  send('\x04'); await pause(100);
  send('\x1b[200~中文 first\nsecond line\n\x1b[201~'); await pause(300);
  const multiline = screen.display();
  await open(); await quit(':wq');
  assert.equal(screen.display(), multiline, 'Multiline draft, including final newline, survives');
  const restored = raw.slice(raw.lastIndexOf('\x1b[?1049h'));
  assert(restored.includes('\x1b[?2004h'), 'Bracketed paste restored after Vim');
  assert(restored.includes('\x1b[?1007l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h'),
    'Mouse reporting restored without wheel-to-arrow synthesis after Vim');
  if (['WezTerm', 'iTerm.app'].includes(process.env.TEST_TERM_PROGRAM)) {
    assert(restored.includes('\x1b[>1u'), 'Kitty keyboard protocol restored after Vim');
  }
  const lines = screen.display().split('\n');
  const draftRow = lines.findIndex(line => line.includes('中文 first'));
  const draftColumn = lines[draftRow].indexOf('中文') + 1;
  const copyOffset = raw.length;
  send(`\x1b[<0;${draftColumn};${draftRow + 1}M`); await pause(80);
  send(`\x1b[<32;${draftColumn + 4};${draftRow + 1}M`); await pause(100);
  send(`\x1b[<0;${draftColumn + 4};${draftRow + 1}m`); await pause(150);
  send('\x03');
  if ((process.env.TEST_TERM_PROGRAM || 'Apple_Terminal') === 'Apple_Terminal') {
    // Apple Terminal does not support OSC 52; avoid touching the real clipboard.
    await wait(() => has('Copy failed'), 'Mouse selection reaches clipboard handling after Vim');
  } else {
    await wait(() => raw.slice(copyOffset).includes('\x1b]52;c;'), 'Mouse selection copies after Vim');
  }
  assert(has('中文 first'), 'Selection copy preserves the draft');
  send('\x1b'); await pause(200);
  send('\x03'); await pause(150); send('\x03'); await pause(150); send('\x03');
} finally {
  if (driver.exitCode === null && driver.signalCode === null) {
    const exited = new Promise(resolve => driver.once('exit', resolve));
    driver.stdin.end('quit\n');
    await exited;
  }
  rmSync(directory, { recursive: true, force: true });
}
assert.equal(driver.exitCode, 0, 'PTY driver cleaned up successfully');
console.log(`PASS: actual Vim save/cancel/repeat, multiline, raw input, paste and mouse ${rows}x${columns}`);