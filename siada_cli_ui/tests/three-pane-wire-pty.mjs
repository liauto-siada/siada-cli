import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const rows = 43;
const columns = 100;
const logDirectory = `/tmp/siada-three-pane-wire-${Date.now()}`;
const configDirectory = mkdtempSync(join(tmpdir(), 'siada-ui-language-'));
const screen = new TerminalScreen(rows, columns);
let raw = '';
const driver = spawn('python3', ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys,shutil
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',43,100,0,0))
args=['node','bundle/siada-ui.js','--siada-path',shutil.which('node'),
      '--siada-args','tests/fixtures/three-pane-acp-server.mjs','--log-level','debug','.']
p=subprocess.Popen(args,stdin=s,stdout=s,stderr=s,start_new_session=True)
pending=b''
try:
 while True:
  ready,_,_=select.select([m,sys.stdin.fileno()],[],[],0.05)
  if p.poll() is not None and m not in ready:break
  if m in ready:
   try:data=os.read(m,65536)
   except OSError:break
   if not data:break
   sys.stdout.buffer.write(data)
   sys.stdout.buffer.flush()
  if sys.stdin.fileno() in ready:
   data=os.read(sys.stdin.fileno(),65536)
   if not data:break
   pending+=data
   while b'\n' in pending:
    line,pending=pending.split(b'\n',1)
    if line==b'quit':raise EOFError()
    if line==b'restart':
     if p.poll() is None:
      os.killpg(p.pid,signal.SIGTERM)
      try:p.wait(timeout=1)
      except subprocess.TimeoutExpired:
       os.killpg(p.pid,signal.SIGKILL)
       p.wait()
     p=subprocess.Popen(args,stdin=s,stdout=s,stderr=s,start_new_session=True)
     continue
    if line:os.write(m,bytes.fromhex(line.decode()))
except EOFError:
 pass
finally:
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=1)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGKILL)
   p.wait()
 os.close(m)
 os.close(s)
`], {
    cwd: fileURLToPath(new URL('../', import.meta.url)),
  // SSH may omit terminal identity even when the client supports OSC 52.
  env: { ...process.env, TERM: 'xterm-256color', TERM_PROGRAM: process.env.SIADA_TEST_TERM_PROGRAM ?? '',
    FORCE_COLOR: '3', SIADA_UI_LOG_DIR: logDirectory,
    SIADA_UI_CONFIG_DIR: configDirectory,
    SSH_CONNECTION: 'synthetic-selection-test' },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
const has = text => screen.display().includes(text);
const hintContains = text => {
  const lines = screen.display().split('\n');
  const border = lines.findIndex(line => /^─+$/.test(line));
  const navigation = lines.findLast(line => /(?:最新回复|回到底部|有新回复|点击|已停止|再按 Ctrl\+C|已清空输入|已复制选中内容|已通过 OSC 52|复制失败)/.test(line));
  return Boolean(navigation?.includes(text));
};
const wait = async (condition, label) => {
  const end = Date.now() + 7000;
  while (!condition()) {
    if (Date.now() > end) throw Error(label);
    await pause(25);
  }
};
const command = async text => {
  send(`\x1b[200~${text}\x1b[201~`);
  await pause(600);
  if (text.startsWith('/')) {
    send('\x1b'); await pause(350);
    await wait(() => !has('命令建议') && !has('Suggestions'), 'completion dismissed before submission');
  }
  send('\r');
  await pause(180);
};
const ctrlC = async () => { send('\x03'); await pause(130); };
const click = async (text, expected) => {
  const lines = screen.display().split('\n');
  const row = lines.findIndex(line => line.includes(text));
  assert(row >= 0, `Missing clickable label: ${text}`);
  const x = lines[row].indexOf(lines[row].trimStart()) + 2;
  send(`\x1b[<35;${x};${row + 1}M`);
  await pause(80);
  send(`\x1b[<0;${x};${row + 1}M`);
  await pause(50);
  send(`\x1b[<0;${x};${row + 1}m`);
  await wait(() => has(expected), `expand ${text}`);
};
const selectText = async (text, cells = text.length) => {
  const lines = screen.display().split('\n');
  const row = lines.findLastIndex(line => line.includes(text));
  assert(row >= 0, `Missing selectable text: ${text}`);
  const x = lines[row].indexOf(text) + 1;
  const start = raw.length;
  send(`\x1b[<0;${x};${row + 1}M`);
  await pause(60);
  send(`\x1b[<32;${x + cells};${row + 1}M`);
  await pause(100);
  send(`\x1b[<0;${x + cells};${row + 1}m`);
  const encoded = Buffer.from(text).toString('base64');
  await wait(() => raw.slice(start).includes(`\x1b]52;c;${encoded}\x07`), `copy ${text}`);
  await wait(() => hintContains('已通过 OSC 52'), `copy feedback ${text}`);
};

try {
  await wait(() => has('Type a message'), 'default English ready');
  await command('/fixture lifecycle-error');
  await wait(() => has('CAPACITY_RETRY_END'), 'lifecycle error body');
  assert(has('● Error'), 'error has its own heading');
  assert(has('└─ app.ts:1-20'), 'tool tree ends before the error');
  assert(!/[└├]─ The system/.test(screen.display()), 'error is not a tool tree child');
  assert(raw.includes('\x1b[38;2;239;68;68m● '), 'error bullet is red');
  console.log('PASS: lifecycle error after tools renders a red bullet, Error heading and wrapped body');
  await command('/language');
  await wait(() => has('Interface language'), 'language picker');
  send('\x1b[B'); await pause(150);
  send('\r');
  await wait(() => has('输入消息'), 'switch to Chinese');
  assert.equal(JSON.parse(readFileSync(join(configDirectory, 'ui-config.json'), 'utf8')).language, 'zh-CN');
  const restartOffset = raw.length;
  driver.stdin.write('restart\n');
  await wait(() => raw.slice(restartOffset).includes('wire-test') && has('输入消息'), 'Chinese restored after restart');
  assert(!has('Type a message'));
  console.log('PASS: default English, language picker, saved Chinese preference, and restart');
  send('/');
  await wait(() => has('命令建议'), 'Chinese suggestions');
  assert(has('选择并切换模型') && !has('Open model selector') && !has('Suggestions'));
  send('\x1b');
  await pause(150);
  send('\x04');
  await pause(150);
  console.log('PASS: English ACP command descriptions display as Chinese in the bundled UI');
  await command('/fixture resume');
  await wait(() => has('Wire restored answer'), 'restore');
  assert(has('● Wire restored reasoning') && has('Read file src/restored.ts'));
  console.log('PASS: bundle startup and ACP restored-history delivery');
  await command('/fixture presentation');
  await wait(() => has('Presentation check completed.'), 'presentation scene');
  assert(has('● Run pwd') && has('● Inspect summaries and spacing.… ›'));
  assert(!has('Run command') && !has('正在思考…'));
  await click('Inspect summaries', 'Final reasoning line.');
  assert(!has('Run command'));
  const commandLines = screen.display().split('\n');
  const pwdHeading = commandLines.findIndex(line => line.includes('● Run pwd'));
  assert(commandLines[pwdHeading].includes('● Run pwd'));
  assert(!screen.display().includes('timeout:60s'), 'inline command hides timeout metadata');
  await click('Check grouped tool details', 'Keep their full text visible.');
  assert(!has('Run command') && has('└─ presentation.ts:1-20'));
  const findRow = screen.display().split('\n').findIndex(line => line.includes('xargs grep'));
  assert(findRow >= 0, 'long command preview visible');
  await click('xargs grep', 'xargs grep');
  await pause(400);
  const expandedLines = screen.display().split('\n');
  assert(expandedLines[findRow].includes('⌄'), 'command expands in place');
  const blockLines = expandedLines.slice(findRow, findRow + 3);
  assert(blockLines.every(line => !line.includes('timeout:60s')),
    'expanded command hides timeout metadata');
  assert(expandedLines.filter(line => line.includes('xargs grep -l "presentation"')).length === 1,
    'command first line appears once when expanded');
  const continuationRow = expandedLines.findIndex((line, index) => index > findRow && line.trim() === 'echo done');
  assert(continuationRow > findRow, 'multi-line command body follows the heading');
  const firstCommandColumn = expandedLines[findRow].indexOf('find prototypes');
  assert(expandedLines[continuationRow].indexOf('echo done') === firstCommandColumn,
    'continuation lines align with the command text, not deeper');
  await click('xargs grep', 'xargs grep');
  await wait(() => screen.display().split('\n')[findRow].includes('›'), 'collapse long command');
  console.log('PASS: command and reasoning previews, surfaced details, and grouped expansion without duplicate headings');
  send('\x1b[200~Wire 中文 draft\x1b[201~');
  await pause(300);
  await selectText('中文', 4);
  await ctrlC();
  assert(has('Wire 中文 draft') && !hintContains('再按 Ctrl+C 退出'));
  send('\x1b'); await pause(120);
  await selectText('synthetic');
  await ctrlC();
  assert(has('Wire 中文 draft') && !hintContains('再按 Ctrl+C 退出'));
  send('\x1b'); await pause(120);
  await ctrlC();
  assert(has('输入消息'));
  send('\x1b[D'); await pause(100);
  console.log('PASS: draft and status selection copy exact text; Ctrl+C preserves the draft');
  await command('/fixture resume');
  await wait(() => has('Wire restored answer'), 'reset presentation scene');
  await command('/fixture error');
  await wait(() => has('Recoverable wire error'), 'runtime error');
  assert(has('输入消息') && !has('启动失败'));
  await command('/model');
  await wait(() => has('切换模型'), 'picker');
  assert(has('Wire restored question'));
  await ctrlC();
  await wait(() => has('输入消息'), 'picker close');
  assert(!hintContains('再按 Ctrl+C 退出'));
  for (const [name, title] of [['effort', '推理强度'], ['theme', '切换主题'], ['task-list', '待处理任务'], ['plugin', '发现']]) {
    await command('/' + name);
    await wait(() => has(title), name);
    assert(has('Wire restored question'));
    await ctrlC(); await wait(() => has('输入消息'), name + ' close');
    assert(!hintContains('再按 Ctrl+C 退出'));
  }
  await command('/btw side check');
  await wait(() => has('Wire side question reply'), 'side question');
  await ctrlC();
  await wait(() => !has('Wire side question reply'), 'side close');
  assert(!hintContains('再按 Ctrl+C 退出'));
  console.log('PASS: runtime errors remain in conversation; model and side-question panels own Ctrl+C');
  await command('/fixture input');
  await wait(() => has('需要你输入'), 'interactive');
  send('\x1b[200~Confirm 中文 input\x1b[201~');
  await pause(300);
  await selectText('中文', 4);
  await ctrlC();
  assert(has('Confirm 中文 input') && has('需要你输入'));
  assert(!hintContains('再按 Ctrl+C 退出'));
  send('\x1b'); await pause(120);
  send('\r');
  await wait(() => has('Interactive wire reply: Confirm 中文 input'), 'confirmation submitted after copy');
  assert(!has('需要你输入'));
  console.log('PASS: confirmation input keeps selection and submits the preserved draft through ACP');
  await command('/fixture input');
  await wait(() => has('需要你输入'), 'interactive interrupt');
  await ctrlC();
  assert(hintContains('已停止 · 再按 Ctrl+C 退出') && !has('需要你输入'));
  send('\x1b[D');
  await pause(120);
  await command('Wire live turn');
  await wait(() => has('可输入下一条消息'), 'live turn');
  await command('Wire queued turn');
  await wait(() => has('1 条消息排队中'), 'queue');
  await ctrlC();
  assert(hintContains('已停止 · 再按 Ctrl+C 退出') && !has('1 条消息排队中'));
  assert(driver.exitCode === null);
  send('\x1b[D');
  await pause(120);
  console.log('PASS: real stdin interrupt stops input and queued turn without exiting the UI');
  await command('/goal Wire objective');
  await command('Complete wire turn');
  await wait(() => has('Final wire response.') && has('输入消息'), 'completed stream');
  assert(has('productionViewport') || has('Stream line 45'));
  console.log('PASS: long streamed answers and Markdown code render in the production viewport');
  await wait(() => has('Plan completed (1/1)') && has('Goal Achieved') && !has('Goal complete') && !has('› Todo'),
    'completed plan and goal messages committed');
  await click('Plan completed', 'Plan completed (1/1) ⌄');
  send('\x1b[<65;10;3M'); await pause(150);
  await wait(() => has('Wire integration task'), 'completed plan body');
  for (const text of ['Wire verifier']) {
    await selectText(text);
    await ctrlC();
    assert(!hintContains('再按 Ctrl+C 退出'));
    send('\x1b'); await pause(100);
  }
  console.log('PASS: task and sub-agent text below the input can be selected and copied');
  if (!process.env.SIADA_TEST_CLIPBOARD_ONLY) {
    send('\t');
    await pause(120);
    send('\r');
    await wait(() => has('Agents · 子智能体'), 'agent list');
    await ctrlC();
    await wait(() => has('输入消息'), 'todo close');
    assert(!hintContains('再按 Ctrl+C 退出'), 'closing details must not arm exit');
    console.log('PASS: finished plan/goal archive and agent list consumes Ctrl+C without arming exit');
    await command('/language en');
    await wait(() => has('Type a message'), 'switch back to English');
    await command('/model');
    await wait(() => has('Switch Model'), 'English model picker');
    assert(!has('切换模型'));
    await ctrlC();
    await wait(() => has('Type a message'), 'English picker close');
    assert.equal(JSON.parse(readFileSync(join(configDirectory, 'ui-config.json'), 'utf8')).language, 'en');
    console.log('PASS: switch back to English without restarting');
    await command('/fixture goal active');
    await wait(() => has('› Goal') && has('In progress'), 'active Goal row');
    const goalRow = screen.display().split('\n').findIndex(line => line.includes('› Goal'));
    await command('/fixture goal verifying');
    await wait(() => has('Verifying'), 'same-row Goal verification');
    assert(!has('Goal verifying...'));
    assert.equal(screen.display().split('\n').findIndex(line => line.includes('› Goal')), goalRow);
    await command('/fixture goal continuing');
    await wait(() => has('Continuing'), 'automatic continuation record');
    await command('/fixture goal verifying');
    await click('› Goal', 'Goal · Objective and verification');
    assert(has('Missing Windows evidence.') && has('Next action: Run Windows checks.'));
    await ctrlC(); assert(!hintContains('Ctrl+C again to exit'));
    await command('/fixture goal blocked');
    await wait(() => has('Automatic continuation stopped'), 'blocked Goal');
    await click('› Goal', 'Goal · Objective and verification');
    assert(has('Send a new message'));
    await ctrlC();
    await command('/fixture goal error');
    await wait(() => has('Verification error'), 'system error classification');
    await command('/fixture goal complete');
    await wait(() => has('Goal Achieved') && !has('› Goal'), 'completed Goal hidden');
    await command('/fixture goal cleared');
    await wait(() => has('Goal cleared.'), 'clear feedback');
    await command('/fixture goal restored');
    await wait(() => has('Goal Not achieved') && has('In progress'), 'restored records and Goal');
    assert.equal(screen.display().split('Goal Not achieved').length - 1, 1);
    console.log('PASS: Goal active, same-row verification, continuation, blocked/error, completion, clear and restored records');
  }
  send('\x03\x03');
  await wait(() => driver.exitCode !== null, 'exit');
  assert(raw.includes('\x1b[?1049l') && raw.includes('\x1b[?1006l'));
  assert(raw.includes('siada-cli --resume synthetic-three-pane-wire-session'));
  console.log('PASS: double Ctrl+C exits and restores terminal modes and the resume session');
} catch (error) {
  console.error(error.stack);
  console.error(screen.display());
  process.exitCode = 1;
} finally {
  if (driver.exitCode === null) driver.stdin.end('quit\n');
  console.log(`LOG_DIR: ${logDirectory}`);
}