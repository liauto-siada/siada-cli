// Run with: SIADA_TEST_PYTHON=/path/to/isolated/bin/python npx tsx tests/async-controller-app-pty.mjs
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TerminalScreen } from './helpers/terminalScreen.ts';

const repo = fileURLToPath(new URL('../../', import.meta.url));
const state = mkdtempSync(join(tmpdir(), 'siada-async-controller-'));
const cliState = join(state, '.siada-cli');
mkdirSync(cliState);
writeFileSync(join(cliState, '.setup_version'), '1.7.37b3');
writeFileSync(join(cliState, 'conf.yaml'), `
llm_config:
  provider: default
  model: gpt-4.1
fast_llm_config:
  provider: default
  model: gpt-4.1
proactive:
  enabled: false
auto_update:
  enabled: false
memory:
  enabled: false
  holographic:
    enabled: false
sub_agent:
  enabled: false
web:
  enabled: false
enable_notification: false
`);
writeFileSync(join(cliState, 'mcp_config.json'), '{"enabled":false,"servers":{}}');
const screen = new TerminalScreen(43, 100);
let raw = '', errors = '';
const driver = spawn(process.env.SIADA_TEST_PYTHON, ['-u', '-c', String.raw`
import os,pty,fcntl,termios,struct,select,subprocess,signal,sys,json,threading
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
stop=threading.Event()
release_model=threading.Event()
class Model(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  messages=body.get('messages',[])
  with open(os.path.join(os.environ['SIADA_TEST_STATE_DIR'],'model-users.ndjson'),'a') as capture:
   capture.write(json.dumps([m.get('content') for m in messages if m.get('role')=='user'])+'\n')
  last=next((m.get('content','') for m in reversed(messages) if m.get('role')=='user'),'')
  text=json.dumps(last)
  tool=None
  if body.get('response_format'):
   answer=json.dumps({'passed':True,'reason':'Synthetic checks passed','nextAction':''})
  elif messages and messages[-1].get('role')=='tool':answer='PTY_TOOL_DONE'
  elif 'PTY_TOOL_WAIT' in text:
   tool={'index':0,'id':'call-pty-wait','type':'function','function':{'name':'run_cmd',
    'arguments':json.dumps({'command':"python -u -c \"import time;print('PTY_TOOL_RUNNING',flush=True);time.sleep(30)\""})}}
   answer=''
  elif 'PTY_TOOL' in text:
   tool={'index':0,'id':'call-pty-tool','type':'function','function':{'name':'run_cmd',
    'arguments':json.dumps({'command':"python -c \"print('PTY_COMMAND_OUTPUT')\""})}}
   answer=''
  elif 'PTY_WAIT' in text:answer='PTY_WAITING'
  elif 'PTY_SECOND' in text:answer='PTY_SECOND_DONE'
  elif 'PTY_FIRST' in text:answer='PTY_FIRST_DONE'
  else:answer='Synthetic reply'
  self.send_response(200)
  if not body.get('stream'):
   self.send_header('Content-Type','application/json');self.end_headers()
   self.wfile.write(json.dumps({'id':'chatcmpl-pty','object':'chat.completion','created':1,
    'model':'gpt-4.1','choices':[{'index':0,'message':{'role':'assistant','content':answer},
    'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}).encode())
   return
  self.send_header('Content-Type','text/event-stream');self.end_headers()
  def chunk(delta,finish=None):
   item={'id':'chatcmpl-pty','object':'chat.completion.chunk','created':1,'model':'gpt-4.1',
    'choices':[{'index':0,'delta':delta,'finish_reason':finish}]}
   self.wfile.write(('data: '+json.dumps(item)+'\n\n').encode());self.wfile.flush()
  try:
   chunk({'role':'assistant','content':''})
   chunk({'tool_calls':[tool]} if tool else {'content':answer})
   if answer=='PTY_WAITING':
    release_model.wait(30)
    release_model.clear()
    chunk({'content':'PTY_WAIT_FINISHED'})
   chunk({},'tool_calls' if tool else 'stop')
   self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
  except (BrokenPipeError,ConnectionResetError):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Model)
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}/v1'
from pathlib import Path
config=Path(os.environ['SIADA_TEST_STATE_DIR'])/'.siada-cli'/'conf.yaml'
config.write_text(config.read_text().replace('  provider: default',
 '  provider: default\n  base_url: '+base+'\n  api_key: synthetic-pty-key'))
os.environ.update(BASE_URL=base,API_KEY='synthetic-pty-key',OPENAI_API_KEY='synthetic-pty-key',
 OPENAI_AGENTS_DISABLE_TRACING='1')
m,s=pty.openpty()
fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',43,100,0,0))
args=[sys.executable,'-m','siada.entrypoint.launch_ui_with_acp',
 '--workspace',os.environ['SIADA_TEST_STATE_DIR'],'--no-daemon','--no-check-update',
 '--provider','default','--model','gpt-4.1','--set-env','BASE_URL='+base,
 '--set-env','API_KEY=synthetic-pty-key','--set-env','OPENAI_API_KEY=synthetic-pty-key']
p=subprocess.Popen(args,stdin=s,stdout=s,stderr=s,cwd=os.environ['SIADA_TEST_STATE_DIR'],start_new_session=True)
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
    if line==b'release-model':
     release_model.set()
     continue
    if line:os.write(m,bytes.fromhex(line.decode()))
except EOFError:pass
finally:
 stop.set();release_model.set();server.shutdown()
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 os.close(m)
`], {
  cwd: state,
  env: { ...process.env, SIADA_TEST_STATE_DIR: state,
    SIADA_CLI_LOG_DIR: join(state, 'backend-logs'),
    PYTHONPATH: resolve(repo, 'tests/fixtures/async_controller'),
    SIADA_UI_CONFIG_DIR: join(state, 'ui'), SIADA_UI_LOG_DIR: join(state, 'ui'),
    TERM: 'xterm-256color', TERM_PROGRAM: 'WezTerm', FORCE_COLOR: '3',
    SSH_CONNECTION: 'synthetic-async-runtime' },
});
driver.stdout.setEncoding('utf8');
driver.stdout.on('data', data => { raw += data; screen.feed(data); });
driver.stderr.setEncoding('utf8');
driver.stderr.on('data', data => { errors += data; });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const send = text => driver.stdin.write(Buffer.from(text).toString('hex') + '\n');
async function wait(condition, label, timeout = 45000) {
  const end = Date.now() + timeout;
  while (!condition()) {
    if (Date.now() > end || driver.exitCode !== null) throw Error(label);
    await pause(40);
  }
}
async function command(text) {
  send(`\x1b[200~${text}\x1b[201~`); await pause(400);
  if (text.startsWith('/')) { send('\x1b'); await pause(150); }
  send('\r'); await pause(250);
}
const backendLogPath = join(state, 'backend-logs', 'siada_cli.log');
const completedTurns = () => existsSync(backendLogPath)
  ? (readFileSync(backendLogPath, 'utf8').match(/\[TURN_COMPLETE\]/g) || []).length : 0;
const completedCommands = () => existsSync(backendLogPath)
  ? (readFileSync(backendLogPath, 'utf8').match(/\[COMMAND_RESULT\]/g) || []).length : 0;
async function verifyImmediateCommand(text, expected) {
  const commands = completedCommands(), turns = completedTurns(), offset = raw.length;
  const logOffset = readFileSync(backendLogPath, 'utf8').length;
  await command(text);
  await wait(() => completedCommands() > commands &&
    (raw.slice(offset).includes(expected) || screen.display().includes(expected)),
    `${text} responds during model request`, 5000);
  assert.equal(completedTurns(), turns, 'query must not complete or replace the model turn');
  assert(screen.display().includes('Type next message while thinking'),
    'main composer remains in the active-turn state');
  const delta = readFileSync(backendLogPath, 'utf8').slice(logOffset);
  assert(!delta.includes('cancel_current_command'), 'query must not interrupt the model');
}
async function verifyPrompt(text, expected, label) {
  const completed = completedTurns(), offset = raw.length;
  await command(text);
  // Ink may redraw old answers. Require a new backend completion as well.
  await wait(() => completedTurns() > completed && raw.slice(offset).includes(expected), label);
}
try {
  await wait(() => screen.display().includes('Type a message'), 'real launcher ready');
  assert(raw.includes('1.7.37b3') && !raw.includes('vdev'));
  await verifyPrompt('PTY_FIRST', 'PTY_FIRST_DONE', 'first model response');
  console.log('PASS installed launcher, release banner, ACP and first streamed turn');
  await verifyPrompt('PTY_SECOND', 'PTY_SECOND_DONE', 'second model response');
  console.log('PASS consecutive model turns');
  await verifyPrompt('PTY_TOOL', 'PTY_TOOL_DONE', 'command tool result and follow-up');
  console.log('PASS real command tool and model continuation');
  await command('PTY_WAIT');
  await wait(() => raw.includes('PTY_WAITING'), 'long model request entered');
  await verifyImmediateCommand('/status', 'Model: gpt-4.1');
  await verifyImmediateCommand('/help', '/web enable');
  console.log('PASS status and help respond while model is waiting and preserve its indicator');
  send('\x03'); await pause(900);
  await verifyPrompt('PTY_SECOND', 'PTY_SECOND_DONE', 'model cancellation and next turn');
  console.log('PASS model cancellation and next turn');
  const waitingOffset = raw.length;
  await command('PTY_WAIT');
  await wait(() => raw.slice(waitingOffset).includes('PTY_WAITING'), 'second long model request');
  await verifyImmediateCommand('/status', 'Model: gpt-4.1');
  const resumeTurns = completedTurns(), resumeOffset = raw.length;
  driver.stdin.write('release-model\n');
  await wait(() => completedTurns() > resumeTurns && raw.slice(resumeOffset).includes('PTY_WAIT_FINISHED'),
    'model stream resumes and completes after query');
  console.log('PASS model streaming continues to completion after independent status output');
  await verifyPrompt('PTY_SECOND', 'PTY_SECOND_DONE', 'turn after completed model wait');
  const serialWaitOffset = raw.length;
  await command('PTY_WAIT');
  await wait(() => raw.slice(serialWaitOffset).includes('PTY_WAITING'), 'model request before queued clear');
  const serialTurns = completedTurns(), serialLogOffset = readFileSync(backendLogPath, 'utf8').length;
  await command('/clear');
  await wait(() => readFileSync(backendLogPath, 'utf8').slice(serialLogOffset).includes('[COMMAND_QUEUED]'),
    'clear waits in command queue');
  assert.equal(completedTurns(), serialTurns);
  driver.stdin.write('release-model\n');
  await wait(() => completedTurns() >= serialTurns + 2 && screen.display().includes('Type a message'),
    'model completes before queued clear executes');
  await verifyPrompt('PTY_SECOND', 'PTY_SECOND_DONE', 'turn after queued clear');
  console.log('PASS serial clear waits for the model then executes and permits a new turn');
  await command('PTY_TOOL_WAIT');
  await wait(() => raw.includes('PTY_TOOL_RUNNING'), 'long command tool entered');
  await verifyImmediateCommand('/status', 'Model: gpt-4.1');
  console.log('PASS status responds during a running command tool without cancelling it');
  await pause(500); send('\x03'); await pause(900);
  await verifyPrompt('PTY_SECOND', 'PTY_SECOND_DONE', 'command cancellation and next turn');
  console.log('PASS command cancellation and next turn');
  const beforeClear = completedTurns();
  await command('/clear');
  await wait(() => completedTurns() > beforeClear && screen.display().includes('Type a message'),
    'clear returns to input');
  await verifyPrompt('PTY_FIRST', 'PTY_FIRST_DONE', 'new session turn');
  console.log('PASS session clear and subsequent turn');
  send('\x03'); await pause(650); send('\x03');
  await wait(() => driver.exitCode !== null, 'normal terminal exit', 10000);
  assert(raw.includes('\x1b[?1049l'));
  assert(!raw.includes('Event loop is closed') && !raw.includes('cannot be called from a running event loop'));
  console.log('PASS exit restores terminal modes');
  const backendLog = readFileSync(join(state, 'backend-logs', 'siada_cli.log'), 'utf8');
  assert(backendLog.includes('[TURN_START]') && backendLog.includes('[TURN_COMPLETE]'));
  assert(!backendLog.includes('Traceback') && !backendLog.includes('Task was destroyed'));
  assert(!backendLog.includes('cannot be called from a running event loop'));
  console.log('PASS backend lifecycle log without traceback or abandoned tasks');
  const requests = readFileSync(join(state, 'model-users.ndjson'), 'utf8');
  assert(!requests.includes('/status') && !requests.includes('/help') && !requests.includes('/clear'));
  const uiLog = readFileSync(join(state, 'ui', 'siada-ui.log'), 'utf8');
  assert(uiLog.includes('ui/commandResult'));
  console.log('PASS commands stay out of model input and use independent UI result events');
} catch (error) {
  console.error(error.stack); console.error(screen.display()); console.error(errors);
  process.exitCode = 1;
} finally {
  writeFileSync(join(state, 'pty.raw'), raw);
  console.log(`Evidence: ${state}`);
  if (driver.exitCode === null) driver.stdin.end('quit\n');
  await new Promise(resolve => driver.exitCode !== null ? resolve() : driver.once('exit', resolve));
}