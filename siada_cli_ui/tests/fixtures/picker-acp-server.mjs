import { createInterface } from 'node:readline';

// An offline backend exercises production command routing without credentials.
const notify = (method, params) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
const update = params => notify('session/update', params);
const ready = () => update({ reason: 'lifecycle_event', type: 'input_ready', animation_control: 'stop' });
let model = 'model-0', effort = 'medium', theme = 'dark', pending = null;
const providers = Array.from({ length: 40 }, (_, i) => ({
  id: `provider-${i}`, name: `Provider ${i}`, baseUrl: 'https://example.com/v1', apiKeyHint: 'Synthetic key only',
  models: [{ id: `model-${i}`, name: 'Synthetic model', context: 10 }],
}));
const banner = () => update({ reason: 'banner_info', content: JSON.stringify({
  version: '1.7.37-test', working_dir: process.cwd(), agent: 'coder', provider: 'synthetic',
  model, reasoning_effort: effort, theme, session_id: 'picker-test-session',
  slash_commands: ['model', 'effort', 'theme', 'editor', 'statusbar', 'resume', 'task-list', 'plugin', 'configure']
    .map(name => ({ name, description: `Open ${name} picker` })),
}) });
const history = () => notify('ui/loadHistory', { messages: [
  { role: 'user', content: 'Picker history question' },
  { role: 'agent', content: 'Picker history stays visible.', subtype: 'answer' },
] });

function handle(frame) {
  let message;
  try { message = JSON.parse(frame); } catch { return; }
  if (message.method === 'session/pullHistory') {
    notify('session/pullHistoryDone', { messages: [] }); return;
  }
  if (message.method === 'ui/loginChoice') {
    notify('ui/loginDismiss', {}); ready(); return;
  }
  const prompt = message.prompt;
  if (typeof prompt !== 'string') return;
  if (prompt === '/model') {
    notify('ui/showModelSelector', { models: Array.from({ length: 40 }, (_, i) => `model-${i}`), currentModel: model });
  } else if (prompt.startsWith('/model ')) {
    model = prompt.slice(7); banner();
  } else if (prompt === '/effort') {
    notify('ui/showEffortSelector', { model, efforts: ['low', 'medium', 'high', 'xhigh', 'max'], current: effort });
  } else if (prompt.startsWith('/effort ')) {
    effort = prompt.slice(8); banner();
  } else if (prompt === '/theme') {
    notify('ui/showThemeSelector', { themes: ['dark', 'light'], current: theme });
  } else if (prompt.startsWith('/theme ')) {
    theme = prompt.slice(7); banner();
  } else if (prompt === '/task-list') {
    notify('ui/showTaskSelector', { tasks: Array.from({ length: 40 }, (_, i) => ({
      id: `task-${i}`, title: `Task ${i} 中文 ${'long title '.repeat(10)}`, description: 'Description '.repeat(100),
      priority: 'high', category: 'test', confidence: 0.9, needs_confirmation: false,
    })) });
  } else if (prompt === '/plugin') {
    notify('ui/showPluginManager', {
      installed: Array.from({ length: 40 }, (_, i) => ({
        name: `skill-${i}`, description: 'Skill description '.repeat(20), path: '.', scope: 'user', plugin_name: 'Grouped',
      })),
      discover: Array.from({ length: 40 }, (_, i) => ({
        name: `skill-${i}`, description: 'Skill description '.repeat(20), installed: true,
        marketplace: 'synthetic', marketplaceName: 'Synthetic',
      })),
      marketplaces: [{ name: 'Synthetic', repo: 'test/repo', available: 40, installed: 40 }], errors: [],
    });
  } else if (prompt === '/resume') {
    notify('ui/showSessionBrowser', { scope: 'current' });
  } else if (prompt.startsWith('/resume ')) {
    history();
  } else if (prompt === '/configure') {
    notify('ui/showLoginSelector', { requestId: 'picker-login', cancelable: true, liidDisabled: true, providers });
  } else if (prompt.startsWith('/plugin ')) {
    // Acknowledge only; tests never change external plugin state.
  } else {
    history();
  }
  ready();
}
const input = createInterface({ input: process.stdin });
input.on('line', line => {
  if (line.startsWith('__LOGIN_CHOICE__:')) {
    notify('ui/loginDismiss', {}); ready();
  } else if (line === '<<<SIADA_MSG_START>>>') pending = [];
  else if (line === '<<<SIADA_MSG_END>>>') {
    if (pending) handle(pending.join('\n'));
    pending = null;
  } else if (pending) pending.push(line);
});
input.on('close', () => process.exit(0));
setTimeout(banner, 60);
setTimeout(() => notify('ui/startupComplete', {}), 80);
setTimeout(history, 200);