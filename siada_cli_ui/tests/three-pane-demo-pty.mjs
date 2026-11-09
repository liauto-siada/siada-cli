import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import stringWidth from 'string-width';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const rows = Number(process.env.DEMO_ROWS || 43);
const columns = Number(process.env.DEMO_COLUMNS || 100);
const logDirectory = `/tmp/siada-demo-e2e-${rows}x${columns}-${Date.now()}`;
const screen = new TerminalScreen(rows, columns);
let raw = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',int(os.environ['DEMO_ROWS']),int(os.environ['DEMO_COLUMNS']),0,0))
p=subprocess.Popen(['node','examples/three-pane-demo.mjs'],stdin=s,stdout=s,stderr=s,start_new_session=True)
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
  ...process.env, DEMO_ROWS: String(rows), DEMO_COLUMNS: String(columns),
  TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
  SSH_CONNECTION: 'synthetic-demo-e2e', SIADA_UI_LOG_DIR: logDirectory,
} });
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
const wait = async (condition, label, timeout = 9000) => {
  const end = Date.now() + timeout;
  while (!condition()) {
    if (Date.now() > end || driver.exitCode !== null) throw Error(label);
    await pause(25);
  }
};
const command = async text => {
  send(`\x1b[200~${text}\x1b[201~`); await pause(350);
  if (text.startsWith('/')) { send('\x1b'); await pause(350); }
  send('\r'); await pause(200);
};
const escape = async () => { send('\x1b'); await pause(180); };
const scrollHistoryWithPanel = async label => {
  const before = screen.display().split('\n').slice(1, 3).join('\n');
  send('\x1b[<64;3;2M'); await pause(180);
  send('\x1b[<64;3;2M'); await pause(180);
  assert(screen.display().split('\n').slice(1, 3).join('\n') !== before,
    `${label}: exposed history responds to the wheel`);
  assert(has(label), `${label}: panel remains visible`);
  console.log(`PASS history wheel while ${label} is active`);
};
const verifyComposerWheel = async () => {
  assert(raw.includes('\x1b[?1007l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h'),
    'pointer capture disables arrow synthesis and enables every mode separately');
  send('\x1b[200~DRAFT-A\nDRAFT-B\nDRAFT-C\x1b[201~'); await pause(350);
  const draftScreen = screen.display().split('\n');
  const draftRow = draftScreen.findIndex(line => line.includes('DRAFT-A'));
  assert(draftRow > 0, 'multiline draft is visible');
  const composerFrame = draftScreen.slice(draftRow - 1).join('\n');
  const historyFrame = draftScreen.slice(0, draftRow - 1).join('\n');
  send('\x1b[<64;3;2M'); await pause(180);
  send('\x1b[<64;3;2M'); await pause(180);
  assert.notEqual(screen.display().split('\n').slice(0, draftRow - 1).join('\n'), historyFrame);
  assert.equal(screen.display().split('\n').slice(draftRow - 1).join('\n'), composerFrame,
    'wheel input keeps the draft text and composer position unchanged');
  send('\x04'); await pause(180);
  console.log('PASS message wheel preserves the multiline composer');
};
const hoverWork = async () => {
  await wait(() => raw.lastIndexOf('\x1b[?1006h') >
    raw.lastIndexOf('\x1b[?1006l'), 'mouse tracking ready');
  for (const [label, tip] of [
    ['› Goal', 'Click to view Goal'],
    ['› Agents', 'Click to view Agents'],
  ]) {
    const lines = screen.display().split('\n');
    const row = lines.findIndex(line => line.includes(label));
    assert(row >= 0, `Missing hover label ${label}`);
    assert(raw.lastIndexOf('\x1b[?1006h') > raw.lastIndexOf('\x1b[?1006l'),
      'terminal still reports mouse movement');
    const x = lines[row].indexOf(label) + 1, offset = raw.length;
    send(`\x1b[<35;${x};${row + 1}M`);
    await wait(() => has(tip), `hover tip ${label}`);
    assert(raw.slice(offset).includes('\x1b[38;2;208;215;223m'), `soft hover color ${label}`);
    const current = screen.display().split('\n');
    const tipRow = current.findIndex(line => line.includes(tip));
    const inputRow = current.findIndex(line => line.includes('Type a message'));
    assert(tipRow === inputRow - 2, 'hover tip stays beside input');
    send(`\x1b[<35;1;${rows}M`);
    await wait(() => !has(tip), `clear hover ${label}`);
  }
};
const click = async text => {
  const lines = screen.display().split('\n');
  const row = text.startsWith('推理步骤')
    ? lines.findIndex(line => line.startsWith('● ') && line.includes(text))
    : lines.findLastIndex(line => line.includes(text));
  assert(row >= 0, `Missing ${text}`);
  const x = lines[row].indexOf(text) + 1;
  send(`\x1b[<35;${x};${row + 1}M`); await pause(70);
  send(`\x1b[<0;${x};${row + 1}M`); await pause(70);
  send(`\x1b[<0;${x};${row + 1}m`); await pause(180);
};
const select = async (text, cells = text.length) => {
  const lines = screen.display().split('\n'), row = lines.findLastIndex(line => line.includes(text));
  assert(row >= 0, `Missing selectable ${text}`);
  const x = lines[row].indexOf(text) + 1, offset = raw.length;
  send(`\x1b[<0;${x};${row + 1}M`); await pause(70);
  send(`\x1b[<32;${x + cells};${row + 1}M`); await pause(100);
  send(`\x1b[<0;${x + cells};${row + 1}m`);
  await wait(() => raw.slice(offset).includes(`\x1b]52;c;${Buffer.from(text).toString('base64')}\x07`), `copy ${text}`);
  await escape(); await pause(2100);
};
try {
  await wait(() => has('Type a message'), 'ready');
  assert(has('Todo') && has('Agents'));
  assert(screen.display().split('\n').at(-1).trim() === '', 'bottom slack row remains empty');
  const initialLines = screen.display().split('\n');
  const todoStart = initialLines.findIndex(line => line.includes('› Todo'));
  const todoPreview = initialLines.slice(todoStart + 1, todoStart + 4);
  assert.equal(todoPreview.filter(line => /^\s+[✓◐○] /.test(line)).length, 3,
    'Todo preview occupies exactly three task rows');
  assert(todoPreview[2].includes('检查流式回复与任务入口'), 'current task remains visible');
  console.log('PASS startup, persistent work surface and three-item previews');
  if (process.env.DEMO_MOUSE_WHEEL_ONLY) await verifyComposerWheel();
  if (process.env.DEMO_THINKING_ONLY) {
    send('\x1b[1;5H'); await pause(350);
    await wait(() => has('推理步骤 1'), 'Thought preview');
    const before = screen.display().split('\n');
    const row = before.findIndex(line => line.startsWith('● ') && line.includes('推理步骤 1'));
    assert(row >= 0, 'Thought opening visible');
    const preview = before[row].replace(/\s*[█▄]\s*$/u, '').trimEnd();
    assert(stringWidth(preview) <= 64, 'Thought preview stays compact');
    await click('推理步骤 1');
    await wait(() => screen.display().replace(/\s+/g, '').includes('推理步骤2：'), 'Thought expanded');
    const after = screen.display().split('\n');
    assert(after[row].includes('● 推理步骤'), 'Thought expands from its original opening row');
    assert(screen.display().replace(/[\s⌄█▄]/gu, '').match(/推理步骤1：/gu)?.length === 1,
      'Thought opening appears once');
    assert(has('Type a message'), 'input remains visible');
    await click('推理步骤');
    await wait(() => !screen.display().replace(/\s+/g, '').includes('推理步骤2：'), 'Thought collapsed');
    assert(screen.display().split('\n')[row].replace(/\s*[█▄]\s*$/u, '').trimEnd() === preview,
      'Thought returns to its original compact preview');
    console.log('PASS compact Thought preview, in-place expansion, unique opening and mouse collapse');
  }
  if (!process.env.DEMO_EXIT_ONLY && !process.env.DEMO_THINKING_ONLY && !process.env.DEMO_MOUSE_WHEEL_ONLY) {
  await hoverWork();
  console.log('PASS clickable work labels highlight and update right-side tips');
  await select('Goal');
  assert(!has('Goal · Objective and verification'));
  send('\x1b[200~Copy 中文 draft\x1b[201~'); await pause(300);
  await select('中文', 4);
  assert(has('Copy 中文 draft'));
  send('\x03'); await pause(180); assert(has('Type a message'));
  send('\x1b[200~A fairly long draft to delete\x1b[201~'); await pause(220);
  for (let index = 0; index < 5; index++) { send('\x7f'); await pause(55); }
  await wait(() => has('Ctrl+U deletes to line start'), 'repeated deletion tip');
  send('\x04'); await wait(() => has('Type a message'), 'Ctrl+D clears draft');
  console.log('PASS proactive deletion shortcut in the terminal footer');
  send('\x1b[D'); await pause(100);
  console.log('PASS work-summary and Chinese draft selection copy exact text');
  await select('检查流式回复与任务入口', 22);
  assert(!has('Task ·'));
  console.log('PASS Todo preview text copies without opening a record');
  send('\t'); await pause(150); send('\r');
  await wait(() => has('Goal · Objective and verification'), 'Tab Goal');
  assert(!has('› Todo')); await escape();
  send('\t'); await pause(150); send('\t'); await pause(150); send('\r');
  await wait(() => has('▶ ○ 检查流式回复与任务入口'), 'Tab Todo focuses the current task');
  await scrollHistoryWithPanel('▶ ○ 检查流式回复与任务入口');
  assert(!has('Todo · Task list'), 'Enter keeps Todo in place');
  send('\x1b[A'); await pause(150);
  assert(has('▶ ✓ 体验原有展示组件'), 'Up selects the preceding Todo');
  send('\x1b[B'); await pause(150);
  assert(has('▶ ○ 检查流式回复与任务入口'), 'Down selects the following Todo');
  send('\r'); await pause(150); assert(!has('Task ·'));
  await escape();
  await click('Agents'); await wait(() => has('Agents · Sub agents'), 'Agents');
  await click('配色检查'); await wait(() => has('Agent · 配色检查'), 'agent detail');
  assert(has('对比度')); await escape();
  assert(has('Agents · Sub agents')); await escape();
  await hoverWork();
  console.log('PASS closing nested agent detail preserves mouse hover and tips');
  console.log('PASS Tab, Enter, Esc, read-only Todo and agent detail navigation');
  send('\x1b[1;5H'); await pause(250);
  await wait(() => has('查看当前消息渲染链路'), 'history start');
  await click(columns < 100 ? '↓ Bottom' : 'Back to bottom');
  await wait(() => !has('Back to bottom') && !has('↓ Bottom'), 'click return to bottom');
  assert(has('/demo reset'), 'return to bottom reveals the last history paragraph');
  send('\x1b[1;5H'); await pause(250);
  await pause(350);
  {
    const lines = screen.display().split('\n');
    const row = lines.findIndex(line => line.startsWith('● ') && line.includes('推理步骤 1'));
    assert(row >= 0, 'Thought heading visible for hover');
    const offset = raw.length;
    send(`\x1b[<35;2;${row + 1}M`);
    await wait(() => has('Click to expand Thought') || has('Expand Thought'), 'Thought hover action tip');
    assert(raw.slice(offset).includes('\x1b[38;2;208;215;223m'), 'Thought hover color');
  }
  await click('推理步骤 1');
  if (rows <= 20) {
    await wait(() => has('Click to collapse Thought') || has('推理步骤 2'), 'Thought expanded');
    if (!has('推理步骤 2')) { send('\x1b[<65;10;3M'); await pause(180); }
  }
  await wait(() => has('推理步骤 2'), 'Thought expanded');
  if (rows <= 20) {
    send('\x1b[1;5H'); await pause(250);
  }
  await click('推理步骤 1');
  await wait(() => !has('推理步骤 2'), 'Thought collapsed');
  const wheelStart = screen.display();
  send('\x1b[<65;10;3M'); await pause(180);
  assert(screen.display() !== wheelStart, 'mouse wheel changes history');
  send('\x1b[1;5F'); await pause(250);
  await wait(() => has('Type a message'), 'history end');
  console.log('PASS Thought expansion, mouse wheel and history navigation preserve input');
  await verifyComposerWheel();
  send('\x1b[200~/m\x1b[201~'); await pause(650);
  assert(has('Suggestions'));
  const lines = screen.display().split('\n');
  assert(lines.findIndex(line => line.includes('Todo')) < lines.findIndex(line => line.includes('Suggestions')));
  await escape(); assert(!has('Suggestions'));
  send('\x03'); await pause(150); send('\x1b[D'); await pause(100);
  await command('/model'); await wait(() => has('Model'), 'model');
  await scrollHistoryWithPanel('Model');
  send('\x1b[B'); await pause(150); send('\r'); await wait(() => has('Type a message'), 'model choice');
  await command('/effort'); await wait(() => has('Reasoning Effort'), 'original effort');
  send('\x1b[C'); await pause(150); send('\r'); await wait(() => has('Type a message'), 'effort choice');
  for (const [cmd, title] of [['/theme', 'Theme'], ['/effort', 'Effort'], ['/task-list', 'Tasks']]) {
    await command(cmd); await wait(() => has(title), cmd);
    send('\x03'); await pause(180); assert(has('Type a message'));
    assert(!has('Ctrl+C again to exit'));
  }
  console.log('PASS completion and all selectors; modal Ctrl+C returns without exit');
  await command('/theme light'); assert(has('Todo'));
  await command('/theme dark'); assert(has('Todo'));
  await command('/demo verify'); assert(has('Verifying'));
  await click('Goal'); assert(has('Status: Verifying')); await escape();
  await command('/demo blocked'); await click('Goal'); assert(has('Last check: Not achieved')); await escape();
  await command('/demo complete');
  assert(!has('Goal complete'));
  await wait(() => has('Goal Achieved'), 'completed goal in history');
  console.log('PASS themes and Goal verifying, blocked, completed details');
  await command('/demo input'); await wait(() => has('Enter input'), 'confirmation');
  await command('yes'); assert(has('交互输入已收到'));
  await command('/btw side check'); await wait(() => has('旁路问答的离线示例'), 'side question');
  await scrollHistoryWithPanel('/btw');
  await escape(); assert(has('Type a message'));
  await command('/demo all'); assert(has('Agents'));
  await command('completed stream probe');
  await wait(() => has('Type a message'), 'stream completion');
  await wait(() => has('Plan completed (3/3)'), 'completed plan in history');
  assert(!has('› Todo'));
  await click('Plan completed (3/3)');
  send('\x1b[<65;10;3M'); await pause(200);
  await wait(() => has('检查流式回复与任务入口'), 'expand completed plan');
  assert(!has('› Todo'));
  await command('/demo stream'); await wait(() => has('Thinking') || has('Executing'), 'activity');
  await wait(() => /◉ (?:Thinking|Executing tools)… \([1-9]\d*s\)/.test(screen.display()), 'activity elapsed time');
  send('\x1b[1;5H'); await pause(250);
  {
    const lines = screen.display().split('\n');
    const label = columns < 100 ? '↓ Bottom' : 'Back to bottom';
    const row = lines.findIndex(line => line.includes(label));
    assert(row >= 0, 'return control visible during activity');
    assert(/◉ (?:Thinking|Executing tools)…/.test(lines[row]), 'activity visible before hover');
    const x = lines[row].indexOf(label) + 1;
    send(`\x1b[<35;${x};${row + 1}M`); await pause(150);
    assert(/◉ (?:Thinking|Executing tools)…/.test(screen.display().split('\n')[row]),
      'return-control hover preserves activity');
    await click(label);
    assert(!has(label), 'return control remains clickable during activity');
    console.log('PASS return-control hover preserves activity and elapsed time');
  }
  {
    let checked = 0;
    for (const label of ['Goal', 'Agents']) {
      const lines = screen.display().split('\n');
      const row = lines.findIndex(line => line.includes(label) && !line.includes('Click to'));
      if (row < 0) continue;
      const x = lines[row].indexOf(label) + 1;
      send(`\x1b[<35;${x};${row + 1}M`); await pause(150);
      await wait(() => has(`Click to view ${label}`), `active hover hint ${label}`);
      assert(/◉ (?:Thinking|Executing tools)… \([1-9]\d*s\)/.test(screen.display()),
        `${label} hover preserves activity and elapsed time`);
      checked++;
      send(`\x1b[<35;${columns};1M`); await pause(100);
    }
    assert(checked > 0, 'at least one work-status hover checked while running');
    console.log('PASS changing work-status hover hints preserve activity and elapsed time');
  }
  await command('queued probe'); await wait(() => has('1 queued'), 'queue');
  send('\x03'); await pause(200); assert(driver.exitCode === null);
  assert(!has('1 queued'), 'stop discards the queued turn');
  send('\x1b[D'); await pause(150);
  await command('/compact'); await pause(1400);
  await command('/demo reset'); await wait(() => has('Type a message'), 'reset');
  console.log('PASS confirmation, side question, content scenes, streaming, queue, stop and reset');
  }
  send('\x03'); await pause(150); send('\x03');
  await wait(() => driver.exitCode !== null, 'exit');
  assert(raw.includes('\x1b[?1049l') && raw.includes('\x1b[?1006l'));
  assert(raw.includes('\x1b[?1007l'), 'wheel-to-arrow synthesis is disabled');
  assert(raw.includes('\x1b]22;default\x1b\\'), 'interaction requests an arrow mouse pointer');
  assert(raw.includes('\x1b]22;\x1b\\'), 'exit resets the mouse pointer shape');
  const mainScreenOutput = raw.slice(raw.lastIndexOf('\x1b[?1049l') + '\x1b[?1049l'.length);
  assert(!mainScreenOutput.includes('Type a message') && !mainScreenOutput.includes('Latest reply'),
    'exit must not replay the conversation onto the main screen');
  console.log('PASS normal exit restores alternate screen and mouse modes without replaying messages');
} catch (error) {
  console.error(error.stack); console.error(screen.display()); process.exitCode = 1;
} finally {
  if (driver.exitCode === null) driver.stdin.end('quit\n');
  console.log(`LOG_DIR ${logDirectory}`);
}