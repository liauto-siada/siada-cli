import { createInterface } from 'node:readline';

// Exercise the production UI entry point and wire protocol without external services.
const timers = new Set();
let running = false;
let sequence = 0;
let currentStream = null;
let pendingInput = null;
let pendingFrame = null;
const queue = [];
const sessionId = 'synthetic-three-pane-wire-session';
let activeModel = 'synthetic', activeTheme = 'dark', activeEffort = 'medium';
let goalObjective = null;
let goalRecords = [];

const notify = (method, params) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
const update = params => notify('session/update', params);
const lifecycle = params => update({ reason: 'lifecycle_event', ...params });
const schedule = (delay, action) => {
  const timer = setTimeout(() => { timers.delete(timer); action(); }, delay);
  timers.add(timer);
};
const finishStream = (finalDelta = '\n') => {
  if (!currentStream) return;
  if (currentStream.type === 'answer') {
    lifecycle({ type: 'content_delta', delta: finalDelta, is_final: true, stream_end: true,
      stream_start_id: currentStream.id });
  }
  lifecycle({ type: 'message_end', message_id: currentStream.id, message_type: currentStream.type });
  currentStream = null;
};
const startStream = type => {
  finishStream();
  currentStream = { id: `wire-${++sequence}`, type };
  lifecycle({ type: 'message_start', message_type: type, message_id: currentStream.id });
};
const delta = text => lifecycle({
  type: 'content_delta', delta: text, is_final: false, stream_start_id: currentStream.id,
});
const ready = () => lifecycle({ type: 'input_ready', animation_control: 'stop' });
const interrupt = () => {
  if (!running && !pendingInput) return;
  for (const timer of timers) clearTimeout(timer);
  timers.clear();
  finishStream();
  running = false;
  pendingInput = null;
  queue.length = 0;
  ready();
};
process.on('SIGINT', interrupt);

const banner = () => update({ reason: 'banner_info', content: JSON.stringify({
  version: 'wire-test', working_dir: '.', agent: 'coder', provider: 'synthetic',
  model: activeModel, session_id: sessionId, theme: activeTheme, reasoning_effort: activeEffort,
  slash_commands: [
    { name: 'fixture', description: 'Offline ACP integration checks' },
    { name: 'model', description: 'Open model selector' },
    { name: 'effort', description: 'Open effort selector' },
    { name: 'theme', description: 'Open theme selector' },
    { name: 'task-list', description: 'Open task selector' },
    { name: 'plugin', description: 'Open plugin manager' },
    { name: 'goal', description: 'Set an offline goal' },
    { name: 'btw', description: 'Open side question' },
  ],
}) });

function run(prompt) {
  running = true;
  lifecycle({ type: 'processing_started', animation_control: 'start' });
  notify('context/todoState', { todos: [{ content: 'Wire integration task', status: 'in_progress' }] });
  notify('context/subAgentState', { items: [{ id: 'wire-agent', title: 'Wire verifier', status: 'running' }] });
  notify('context/subAgentMessage', { id: 'wire-agent', entry: {
    id: 'wire-thought', kind: 'thinking', text: 'Verifying production UI notifications.', isComplete: false,
  } });
  startStream('thinking');
  delta('Wire reasoning first line.\n中文流式推理内容。');
  schedule(250, () => {
    finishStream();
    for (const file of ['src/first.ts', 'src/中文.ts']) {
      lifecycle({ type: 'tool_use', delta: `Read the file \`${file}\` from line 1 to line 20`,
        chunk_index: 0, is_final: true });
    }
  });
  schedule(500, () => {
    startStream('answer');
    delta(`Wire response: ${prompt}\n\n`);
    const text = Array.from({ length: 45 }, (_, index) => `Stream line ${index + 1}: 中文与原有 Markdown 一起阅读。`).join('\n') +
      '\n\n```ts\nconst productionViewport = true;\n```\n\n';
    let offset = 0;
    const stream = () => {
      const next = Math.min(text.length, offset + 60);
      delta(text.slice(offset, next));
      offset = next;
      if (offset < text.length) schedule(40, stream);
      else {
        finishStream('Final wire response.');
        running = false;
        lifecycle({ type: 'tool_use', delta: '✓  Wire integration task\n\n[1/1 completed]', is_final: true, chunk_index: 0 });
        notify('context/todoState', { todos: [{ content: 'Wire integration task', status: 'completed' }] });
        notify('context/subAgentState', { items: [{ id: 'wire-agent', title: 'Wire verifier', status: 'completed' }] });
        notify('context/subAgentMessage', { id: 'wire-agent', entry: {
          id: 'wire-answer', kind: 'message', text: 'Wire verification completed.',
        } });
        if (goalObjective) {
          notify('context/goalState', { goal: { objective: goalObjective, status: 'complete', turns: 1 },
            verifying: false, result: { objective: goalObjective, achieved: true, turns: 1,
              reason: 'Wire goal completed.', elapsedSeconds: 3, tokensUsed: 10 } });
        }
        ready();
        const nextPrompt = queue.shift();
        if (nextPrompt) {
          update({ reason: 'queue_item_consumed', content: nextPrompt.prompt, metadata: { queue_id: nextPrompt.id } });
          run(nextPrompt.prompt);
        }
      }
    };
    stream();
  });
}

function handle(frame) {
  if (frame.includes('\x03')) { interrupt(); return; }
  let message;
  try { message = JSON.parse(frame); } catch { return; }
  if (message.method === 'session/pullHistory') {
    notify('session/pullHistoryDone', { messages: [] });
    return;
  }
  if (message.method === 'queue/cancelPending') { queue.length = 0; return; }
  const prompt = message.prompt;
  if (typeof prompt !== 'string') return;
  if (pendingInput) {
    pendingInput = null;
    update({ reason: 'message_chunk', content: `Interactive wire reply: ${prompt}`,
      metadata: { chunkType: 'process', isStreaming: false, streamEnd: true } });
    ready();
  } else if (prompt === '/model') {
    notify('ui/showModelSelector', { models: ['synthetic', 'synthetic-fast'], currentModel: 'synthetic' });
    ready();
  } else if (prompt.startsWith('/model ')) {
    activeModel = prompt.slice(7); banner(); ready();
  } else if (prompt === '/effort') {
    notify('ui/showEffortSelector', { model: activeModel, efforts: ['low', 'medium', 'high'], current: activeEffort });
    ready();
  } else if (prompt.startsWith('/effort ')) {
    activeEffort = prompt.slice(8); banner(); ready();
  } else if (prompt === '/theme') {
    notify('ui/showThemeSelector', { themes: ['dark', 'light'], current: activeTheme }); ready();
  } else if (prompt.startsWith('/theme ')) {
    activeTheme = prompt.slice(7); banner(); ready();
  } else if (prompt === '/task-list') {
    notify('ui/showTaskSelector', { tasks: [{ id: 'wire-task', title: 'Wire original task', description: 'Wire task body',
      priority: 'low', category: 'test', confidence: 0.9 }] }); ready();
  } else if (prompt === '/plugin') {
    notify('ui/showPluginManager', { installed: [], discover: [], errors: [], marketplaces: [] }); ready();
  } else if (prompt.startsWith('/goal ')) {
    goalObjective = prompt.slice(6) === 'clear' ? null : prompt.slice(6);
    notify('context/goalState', { goal: goalObjective ? { objective: goalObjective, status: 'active', turns: 0,
      createdAt: '2026-01-01T00:00:00Z' } : null, verifying: false }); ready();
  } else if (prompt.startsWith('/fixture goal ')) {
    const phase = prompt.slice('/fixture goal '.length);
    const goal = { objective: 'Check Goal UI evidence', status: phase === 'blocked' ? 'blocked'
      : phase === 'complete' ? 'complete' : 'active', createdAt: '2026-01-01T00:00:00Z', turns: 1 };
    if (phase === 'active' || phase === 'restored') {
      notify('ui/loadHistory', { messages: [{ role: 'agent', content: 'Goal UI evidence is ready.' }] });
      notify('context/todoState', { todos: [{ content: 'Check evidence', status: 'in_progress' }] });
      notify('context/subAgentState', { items: [] });
      if (phase === 'active') goalRecords = [];
    }
    let result;
    if (['continuing', 'blocked', 'error', 'complete'].includes(phase)) {
      result = { id: `goal-ui-${phase}`, objective: goal.objective, achieved: phase === 'complete',
        outcome: phase === 'continuing' ? 'not_achieved' : phase === 'error' ? 'system_error'
          : phase === 'blocked' ? 'blocked' : 'achieved',
        continuing: phase === 'continuing' || phase === 'error', turns: 1, elapsedSeconds: 3, tokensUsed: 0,
        reason: phase === 'complete' ? 'All evidence is available.' : 'Missing Windows evidence.',
        nextAction: 'Run Windows checks.' };
      goalRecords.push(result);
    }
    if (phase === 'complete') notify('context/todoState', { todos: [] });
    const snapshot = { goal: phase === 'cleared' ? null : goal, verifying: phase === 'verifying',
      ...(goalRecords.length && phase !== 'cleared' ? { latestResult: goalRecords.at(-1) } : {}),
      ...(result ? { result } : {}),
      ...(phase === 'restored' ? { results: goalRecords } : {}),
      ...(phase === 'cleared' ? { notice: 'Goal cleared.' } : {}) };
    notify('context/goalState', snapshot);
    if (phase === 'restored') notify('context/goalState', snapshot);
    ready();
  } else if (prompt.startsWith('/btw ')) {
    notify('ui/showSideQuestion', { question: prompt.slice(5), answer: 'Wire side question reply.' });
  } else if (prompt === '/fixture input') {
    pendingInput = 'confirmation';
    update({ reason: 'interactive_input_request', content: 'Wire confirmation: enter yes',
      metadata: { inputType: 'confirmation', isPassword: false } });
    ready();
  } else if (prompt === '/fixture lifecycle-error') {
    notify('ui/loadHistory', { messages: [] });
    lifecycle({ type: 'tool_use', delta: 'Run the following command:\n```bash\nnpm run build\n```',
      chunk_index: 0, is_final: true });
    lifecycle({ type: 'tool_use', delta: 'Read the file `src/app.ts` from line 1 to line 20',
      chunk_index: 0, is_final: true });
    lifecycle({ type: 'error', content: 'The system is currently experiencing high demand and cannot process your request. ' +
      'Your request exceeds the maximum usage size allowed during peak load. CAPACITY_RETRY_END' });
    ready();
  } else if (prompt === '/fixture error') {
    lifecycle({ type: 'task_start', category: 'slash_command', command: prompt, task_id: 'wire-error' });
    lifecycle({ type: 'task_error', command: prompt, error: 'Recoverable wire error', error_type: 'synthetic' });
    ready();
  } else if (prompt === '/fixture resume') {
    banner();
    notify('ui/loadHistory', { messages: [
      { role: 'user', content: 'Wire restored question' },
      { role: 'agent', content: 'Wire restored reasoning', subtype: 'thinking' },
      { role: 'agent', content: 'Read the file `src/restored.ts`', subtype: 'tool_use' },
      { role: 'agent', content: 'Wire restored answer', subtype: 'answer' },
    ] });
    ready();
  } else if (prompt === '/fixture search-layout') {
    notify('ui/loadHistory', { messages: [
      { role: 'user', content: 'Review search display.' },
      { role: 'agent', content: 'Search for: timeout: in src with file pattern *.tsx in /tmp/project',
        subtype: 'tool_use' },
      { role: 'agent', content: 'Search for: ● in src with file pattern *.{ts,tsx} in /tmp/project',
        subtype: 'tool_use' },
      { role: 'agent', content: 'Search results: 2 matches\nsrc/a.ts:12: needle', subtype: 'tool_use' },
      { role: 'agent', content: 'Search layout scene ready.', subtype: 'answer' },
    ] });
    ready();
  } else if (prompt === '/fixture markdown' || prompt === '/fixture markdown-history') {
    const source = '```text\n' + 'literal **code** `value`\n'.repeat(270) + '## CODE_TAIL';
    const tail = '\n```\n## MARKDOWN_TAIL\n**BOLD_TAIL** `INLINE_TAIL`\n- **LIST_TAIL**';
    if (prompt.endsWith('-history')) {
      notify('ui/loadHistory', { messages: [
        { role: 'user', content: 'Synthetic Markdown restoration check.' },
        { role: 'agent', content: source + tail + '\nHISTORY_TAIL', subtype: 'answer' },
      ] });
      ready();
    } else {
      startStream('answer');
      delta(source);
      schedule(1200, () => {
        finishStream(tail);
        ready();
      });
    }
  } else if (prompt === '/fixture mermaid' || prompt === '/fixture mermaid-history') {
    const source = '```mermaid\nsequenceDiagram\n' +
      '%% padding to cross the presentation fragment boundary\n'.repeat(70) +
      'participant A as Parent\nparticipant B as Child\n' +
      'A->>B: MERMAID_REQUEST\nB-->>A: MERMAID_RESULT\n%% MERMAID_PENDING';
    const tail = '\n```\nMERMAID_COMPLETE';
    if (prompt.endsWith('-history')) {
      notify('ui/loadHistory', { messages: [
        { role: 'user', content: 'Synthetic Mermaid restoration check.' },
        { role: 'agent', content: source + tail + '\nMERMAID_HISTORY', subtype: 'answer' },
      ] });
      ready();
    } else {
      startStream('answer');
      delta(source);
      schedule(1200, () => {
        finishStream(tail);
        ready();
      });
    }
  } else if (prompt === '/fixture presentation') {
    notify('ui/loadHistory', { messages: [
      { role: 'user', content: 'Review summaries and spacing.' },
      { role: 'agent', content: 'Inspect summaries and spacing.\nReasoning body on a surface.\n\nFinal reasoning line.',
        subtype: 'thinking' },
      { role: 'agent', content: 'Run the following command:\n```bash\npwd\n```\ntimeout:60s', subtype: 'tool_use' },
      { role: 'agent', content: 'Check grouped tool details.\nKeep their full text visible.', subtype: 'thinking' },
      { role: 'agent', content: 'Run the following command:\n```bash\nfind prototypes -type f | head -50\n```\ntimeout:60s',
        subtype: 'tool_use' },
      { role: 'agent', content: 'Run the following command:\n```bash\nfind prototypes -type f \\( -name "*.tsx" -o -name "*.ts" \\) | xargs grep -l "presentation" | head -50\necho done\n```\ntimeout:60s',
        subtype: 'tool_use' },
      { role: 'agent', content: 'Read the file `src/presentation.ts` from line 1 to line 20', subtype: 'tool_use' },
      { role: 'agent', content: 'Presentation check completed.', subtype: 'answer' },
    ] });
    ready();
  } else if (running) {
    queue.push({ prompt, id: message.queue_id });
  } else {
    run(prompt);
  }
}

const input = createInterface({ input: process.stdin });
input.on('line', line => {
  if (line.includes('\x03')) { interrupt(); return; }
  if (line === '<<<SIADA_MSG_START>>>') pendingFrame = [];
  else if (line === '<<<SIADA_MSG_END>>>') {
    if (pendingFrame) handle(pendingFrame.join('\n'));
    pendingFrame = null;
  } else if (pendingFrame) pendingFrame.push(line);
});
input.on('close', () => { interrupt(); process.exit(0); });
schedule(60, banner);
schedule(80, () => notify('ui/startupComplete', {}));