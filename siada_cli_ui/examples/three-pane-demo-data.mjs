export const createMessage = (id, type, content, subtype, metadata = {}) => ({
  id, type, content, author: type === 'user' ? 'You' : 'Siada',
  timestamp: '2026-01-01T00:00:00Z',
  metadata: { ...(subtype ? { subtype } : {}), ...metadata },
});

export const editFileExample = [
  'Edit file src/components/layouts/MainLayout.tsx',
  '<!-- siada-file-edit:start -->',
  JSON.stringify({
    callId: 'demo-edit-main-layout', action: 'update',
    path: 'src/components/layouts/MainLayout.tsx', status: 'completed',
    oldString: [
      'const rows = process.stdout.rows || 24;',
      'const historyHeight = rows - 4;',
      '',
      'return (',
      '  <Box flexDirection="column">',
      '    <MessageList messages={messages} />',
      '    <InputPrompt onSubmit={onSendMessage} />',
      '  </Box>',
      ');',
      '',
    ].join('\n'),
    newString: [
      'const { rows } = useTerminalSize();',
      'const safeHeight = Math.max(1, rows - 1);',
      'const historyHeight = Math.max(3, safeHeight - composerHeight);',
      '',
      'return (',
      '  <Box flexDirection="column" height={safeHeight}>',
      '    <ConversationViewport messages={messages} height={historyHeight} />',
      '    <InputPrompt onSubmit={onSendMessage} />',
      '  </Box>',
      ');',
      '',
    ].join('\n'),
  }, null, 2),
  '<!-- siada-file-edit:end -->',
].join('\n');

export const markdownExample = [
  '## 原有 Markdown 展示',
  '',
  '**粗体**、*斜体*、`行内代码`与中文都由原有 Markdown 组件渲染。',
  '',
  '> 会话中的表格、代码和图表可一起滚动，也可以拖选复制。',
  '',
  '| 区域 | 内容 | 交互 |',
  '| --- | --- | --- |',
  '| 顶部 | 当前问题 | 点击查看全文 |',
  '| 中间 | Markdown、工具和结果 | 滚动、展开、选择 |',
  '| 底部 | 输入、状态、任务 | 编辑和查看详情 |',
  '',
  '```typescript',
  'interface ReadingAnchor {',
  '  messageId: string;',
  '  offset: number;',
  '}',
  '',
  'const next: ReadingAnchor = { messageId: "reply-1", offset: 12 };',
  '```',
  '',
  '```json',
  '{ "theme": "dark", "streaming": true, "language": "中文" }',
  '```',
  '',
  '```mermaid',
  'flowchart LR',
  '  Input["输入"] --> Run["处理"]',
  '  Run --> Reply["回复"]',
  '  Reply --> Review["阅读与选择"]',
  '```',
].join('\n');

export const demoHelp = [
  '## 完整 UI 离线体验',
  '',
  '模型、费用、任务和命令结果均使用示例数据，界面复用现有 Siada UI 组件。',
  '',
  '- 输入一句话：查看 Thought、工具调用和逐字流式回复；运行期间可继续输入。',
  '- `/demo markdown`、`/demo tools`、`/demo shell`、`/demo error`：补充相应展示。',
  '- `/demo stream`：较长的流式回复，可在更新期间拖选。',
  '- `/demo compact`：体验上下文压缩的状态提示。',
  '- `/demo queue`：体验排队；↑ 取回编辑，Esc 停止当前回复并运行队列。',
  '- `/btw 问题`：打开旁路问答；Esc 关闭，`/btw` 再次打开已有历史。',
  '- `/goal 目标`：设置目标；`/demo goal` 展示验证与完成结果。',
  '- `/demo input`：体验交互输入。',
  '- `/model`、`/theme`、`/effort`、`/task-list`：打开原有选择器。',
  '- 输入为空时 Tab 切换任务／子 agent，↑↓ 选择，Enter 查看，Esc 返回。',
  '- Ctrl+O 查看详细内容；Ctrl+G 查看用户消息目录；Ctrl+Home / End 跳到首尾。',
  '- Ctrl+C 停止当前执行；1 秒内再按一次退出。其他按键取消退出提示；有草稿时先清空，↑ 可取回。',
  '- `/demo` 查看本说明，`/demo reset` 恢复初始场景。',
].join('\n');

export const demoCommands = [
  { name: 'demo', description: '查看原有 UI 的离线演示', argument_hint: '[markdown | tools | shell | error | stream | queue | input | goal | compact | reset]' },
  { name: 'help', description: '查看离线演示说明' },
  { name: 'btw', description: '打开旁路问答示例', argument_hint: '[<question>]' },
  { name: 'goal', description: '设置目标示例', argument_hint: '[<objective> | clear]' },
  { name: 'model', description: '打开模型选择器', argument_hint: '[offline | offline-fast | offline-reasoning]' },
  { name: 'theme', description: '切换原有主题', argument_hint: '[dark | light]' },
  { name: 'effort', description: '打开推理强度选择器', argument_hint: '[low | medium | high]' },
  { name: 'thinking', description: '切换思考展示', argument_hint: '[on | off]' },
  { name: 'task-list', description: '打开任务选择器' },
  { name: 'compact', description: '演示上下文压缩状态' },
  { name: 'editor', description: '打开原有编辑器设置' },
  { name: 'statusbar', description: '打开原有状态栏设置' },
  { name: 'export', description: '导出当前示例会话', argument_hint: '[<filename>]' },
];

export const demoTasks = [
  { id: 'demo-task-layout', title: '检查三栏布局', description: '检查历史滚动时输入区与顶部问题的显示。',
    priority: 'high', category: 'test', status: 'pending', needs_confirmation: false,
    suggested_actions: ['检查布局与文字选择'], confidence: 0.95 },
  { id: 'demo-task-markdown', title: '查看 Markdown 示例', description: '展示中文表格、代码和 Mermaid 图表。',
    priority: 'medium', category: 'feature', status: 'pending', needs_confirmation: false,
    suggested_actions: ['查看原有 Markdown 展示'], confidence: 0.9 },
  { id: 'demo-task-stream', title: '检查流式回复', description: '查看回复更新、任务进度和消息排队。',
    priority: 'low', category: 'test', status: 'pending', needs_confirmation: false,
    suggested_actions: ['体验流式回复与队列'], confidence: 0.9 },
];

export function goalResultMessage(id, objective, achieved = true) {
  return createMessage(id, 'agent', '', 'goal_result', {
    goalResult: {
      achieved, elapsedSeconds: 3, turns: 1, tokensUsed: 0, objective,
      reason: achieved ? '离线示例的展示与交互检查已完成。' : '还需要检查窄窗口中的布局。',
      ...(!achieved ? { nextAction: '调整窗口宽度后继续检查。' } : {}),
    },
  });
}

export function showcaseMessages(kind, prefix) {
  const item = (suffix, type, content, subtype, metadata) =>
    createMessage(`${prefix}-${suffix}`, type, content, subtype, metadata);
  switch (kind) {
    case 'markdown':
      return [item('markdown', 'agent', markdownExample, 'answer')];
    case 'tools':
      return [
        item('read', 'agent', 'Read the file `src/components/Chat/Message.tsx` from line 1 to line 40', 'tool_use'),
        item('search', 'agent', 'Search for: ConversationViewport in src with file pattern *.tsx in .', 'tool_use'),
        item('memory', 'agent', 'Searching memory: 三栏界面的阅读与输入方式', 'tool_use'),
        item('sub-agent', 'agent', 'Sub-agent task: 检查 Markdown 与工具详情的展示', 'tool_use'),
        item('command', 'agent', 'Run the following command:\n```bash\nnpm test -- --run\n```\nTimeout: 30 seconds', 'tool_use'),
        item('edit', 'agent', editFileExample, 'tool_use'),
        item('result', 'tool', '示例结果：读取、搜索、任务与文件更新的展示已完成。'),
      ];
    case 'shell':
      return [item('shell', 'tool', 'Executed: npm test -- --run', 'shell', {
        shellExecution: { command: 'npm test -- --run', executing: false,
          stdout: '✓ conversation selection\n✓ markdown rendering\n✓ three-pane layout\n\nTests  24 passed (24)\n',
          stderr: '', exitCode: 0, duration: 1280 },
      })];
    case 'error':
      return [
        item('failed-shell', 'tool', 'Executed: npm run check', 'shell', {
          shellExecution: { command: 'npm run check', executing: false,
            stdout: '', stderr: 'example.ts:12: Type mismatch in the sample configuration.\n',
            exitCode: 1, duration: 340 },
        }),
        item('error', 'error', '这是一条错误展示示例。\n调整示例配置后可以继续体验其他内容。', 'error_box'),
        item('notice', 'system', '示例任务已记录；可以继续输入或查看历史。', 'process'),
      ];
    default:
      return [];
  }
}

export function createInitialDemoState() {
  const messages = [
    createMessage('u1', 'user', '查看当前消息渲染链路，找出历史重复渲染的原因。'),
    createMessage('t1', 'agent', Array.from({ length: 25 }, (_, i) =>
      `推理步骤 ${i + 1}：检查布局、缓存和消息更新的边界。`).join('\n'), 'thinking'),
    createMessage('tool1', 'agent', 'Read the file `src/components/Chat/MessageList.tsx` from line 1 to line 80', 'tool_use'),
    createMessage('a1', 'agent', '当前历史消息通过 Static 输出，动态区域持续更新。要固定顶部问题与输入，需要把历史放入独立视口。\n\n保留已有 Markdown、工具详情和任务入口，通过稳定 ID 复用完成的消息。', 'answer'),
    createMessage('u2', 'user', '展示原有 Markdown、命令结果和任务记录。'),
    ...showcaseMessages('markdown', 'initial'),
    ...showcaseMessages('shell', 'initial'),
    createMessage('checkpoint', 'agent', '已检查中文表格、代码高亮、图表和命令输出。', 'answer'),
    createMessage('u3', 'user', '按三分区方案实现。顶部固定最新已发送问题，中间滚动，底部固定输入。'),
    createMessage('t3', 'agent', '先确认三块区域的高度预算。\n再检查中文换行、流式回复和历史导航。\n浏览历史时应保留输入草稿。', 'thinking'),
    createMessage('tool3', 'agent', 'Analyze definitions in `src/components/layouts/MainLayout.tsx`', 'tool_use'),
    createMessage('tool-edit', 'agent', editFileExample, 'tool_use'),
    createMessage('a3', 'agent', '已经接入三分区布局。\n\n- 顶部问题随成功发送的消息更新。\n- 历史通过鼠标滚轮、PgUp/PgDn 独立滚动。\n- Thought 标题可以点击完整展开。\n- Edit file 工具可以点击展开代码 diff。', 'answer'),
    createMessage('demo-guide', 'agent', demoHelp, 'answer'),
  ];
  return {
    sceneId: 'initial',
    messages, loading: false, activeStep: null,
    model: 'offline', reasoningEffort: 'medium', thinkingEnabled: true, isCollapsed: true,
    screen: null, sideQuestions: [], sideQuestionPanelVisible: false, sideQuestionNotice: null,
    interactiveInput: null, promptQueue: [],
    todoItems: [
      { content: '检查三栏会话与文字选择', status: 'completed' },
      { content: '体验原有展示组件', status: 'completed' },
      { content: '检查流式回复与任务入口', status: 'pending' },
    ],
    todoMessageRanges: new Map([
      ['检查三栏会话与文字选择', { startIdx: 0, endIdx: 1 }],
      ['体验原有展示组件', { startIdx: messages.findIndex(message => message.id === 'checkpoint'), endIdx: messages.findIndex(message => message.id === 'checkpoint') + 1 }],
    ]),
    subAgentItems: [
      { id: 'demo-reader', title: '展示检查', status: 'completed', summary: 'Markdown、代码和命令输出已检查。' },
      { id: 'demo-verifier', title: '交互检查', status: 'completed', summary: '文字选择与导航已检查。' },
    ],
    subAgentMessages: new Map([
      ['demo-reader', [
        { id: 'reader-thought', kind: 'thinking', text: '先检查不同类型内容的原有展示组件。', isComplete: true },
        { id: 'reader-tool', kind: 'tool_call', text: 'Read the file `src/components/Chat/Message.tsx` from line 1 to line 40' },
        { id: 'reader-answer', kind: 'message', text: '### 展示检查\n\n- 中文和代码可完整阅读。\n- 表格与图表复用原有组件。\n- 工具详情可独立展开。' },
      ]],
      ['demo-verifier', [
        { id: 'verifier-thought', kind: 'thinking', text: '检查输入、历史导航和任务详情之间的切换。', isComplete: true },
        { id: 'verifier-answer', kind: 'message', text: '### 交互检查\n\n文字选择、滚轮和用户消息目录已就绪。输入新消息后，这个示例任务会继续更新。' },
      ]],
      ['demo-palette', [
        { id: 'palette-error', kind: 'message', text: '### 配色检查未通过\n\n浅色提示文字对比度不足。\n\n下一步：调整提示颜色后重新核对。' },
      ]],
    ]),
    goalState: null, goalNotice: null,
    tokenUsage: { contextSize: 12000, contextMax: 128000, message: 'Offline demo' },
    cacheStatus: {
      model: 'offline', input: 3600, output: 640, cache_read: 8400, cache_write: 1200,
      prompt_total: 12000, hit_rate: 70, accumulated_hit_rate: 70, reason: 'Offline demo', idle_seconds: 0,
      input_cost: 0.0036, output_cost: 0.00128, cache_write_cost: 0.0012, cache_read_cost: 0.00084,
      total_cost: 0.00692, accumulated_input_cost: 0.0036, accumulated_output_cost: 0.00128,
      accumulated_cache_write_cost: 0.0012, accumulated_cache_read_cost: 0.00084, accumulated_total_cost: 0.00692,
      cost_time_seconds: 1.28, accumulated_input: 3600, accumulated_output: 640,
      accumulated_cache_write: 1200, accumulated_cache_read: 8400,
    },
  };
}

export function createPresentationDemoState() {
  const state = createInitialDemoState();
  return { ...state,
    goalState: { goal: { objective: '完善目标、任务与子智能体的展示', status: 'active',
      createdAt: new Date().toISOString(), turns: 1 }, verifying: false },
    subAgentItems: [...state.subAgentItems.map(item => item.id === 'demo-verifier'
      ? { ...item, status: 'running', summary: '正在检查输入与任务详情。' } : item),
      { id: 'demo-palette', title: '配色检查', status: 'failed', summary: '浅色主题中的提示对比度不足，需要调整。' }],
  };
}