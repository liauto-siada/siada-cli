import { createInitialDemoState, createPresentationDemoState, createMessage, demoHelp, goalResultMessage, showcaseMessages } from './three-pane-demo-data.mjs';

const models = ['offline', 'offline-fast', 'offline-reasoning'];
const efforts = ['low', 'medium', 'high'];

/** Drive the existing UI with immutable offline snapshots and cancellable timers. */
export function createDemoController({ queue, stepMs = 500, chunkMs = 70, presentation = false } = {}) {
  const initialState = presentation ? createPresentationDemoState : createInitialDemoState;
  let state = initialState();
  let sequence = 0, runGeneration = 0, disposed = false;
  const listeners = new Set(), timers = new Set(), runTimers = new Set();
  const publish = patch => {
    if (disposed) return;
    state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) };
    listeners.forEach(listener => listener());
  };
  const schedule = (delay, action, run = false) => {
    if (disposed) return;
    const generation = runGeneration;
    const timer = setTimeout(() => {
      timers.delete(timer); runTimers.delete(timer);
      if (!disposed && (!run || generation === runGeneration)) action();
    }, delay);
    timers.add(timer);
    if (run) runTimers.add(timer);
  };
  const cancelRun = () => {
    runGeneration++;
    for (const timer of runTimers) { clearTimeout(timer); timers.delete(timer); }
    runTimers.clear();
  };
  const id = label => `demo-${label}-${++sequence}`;
  const append = messages => publish(current => ({ messages: [...current.messages, ...messages] }));
  const updateMessage = (messageId, updates) => publish(current => ({
    messages: current.messages.map(message => message.id === messageId ? { ...message, ...updates } : message),
  }));
  const notice = (field, text) => {
    publish({ [field]: text });
    schedule(3000, () => { if (state[field] === text) publish({ [field]: null }); });
  };
  const unsubscribeQueue = queue.subscribe(() => publish({ promptQueue: queue.getSnapshot() }));
  state = { ...state, promptQueue: queue.getSnapshot() };

  const runNext = () => {
    const next = queue.dequeue();
    if (next) run(next.content, next.imagePaths);
    return Boolean(next);
  };
  const verifyGoal = () => {
    if (!state.goalState?.goal || state.goalState.goal.status !== 'active') return;
    const goal = state.goalState.goal, objective = goal.objective;
    publish({ goalState: { ...state.goalState, verifying: true } });
    schedule(stepMs, () => {
      if (state.goalState?.goal !== goal) return;
      const resultMessage = goalResultMessage(id('goal-result'), objective);
      publish({ goalState: { goal: { ...goal, status: 'complete', turns: 1 }, verifying: false,
        result: resultMessage.metadata.goalResult } });
      append([goalResultMessage(id('goal-result'), objective)]);
      notice('goalNotice', 'Goal reached: ' + objective);
      runNext();
    }, true);
  };
  const finishRun = answerId => {
    const answer = state.messages.find(message => message.id === answerId);
    if (answer) updateMessage(answerId, { metadata: { ...answer.metadata, isStreaming: false, streamEnd: true } });
    publish(current => ({
      loading: false, activeStep: null,
      todoItems: current.todoItems.map(item => ({ ...item, status: 'completed' })),
      subAgentItems: current.subAgentItems.map(item => item.id === 'demo-verifier'
        ? { ...item, status: 'completed', summary: '本轮示例回复与任务检查已完成。' } : item),
      subAgentMessages: new Map(current.subAgentMessages).set('demo-verifier', [
        { id: 'run-check', kind: 'thinking', text: '检查回复更新时的输入区与历史阅读。', isComplete: true },
        { id: 'run-result', kind: 'message', text: '本轮示例已完成。可以继续查看任务、复制文字或输入下一条消息。' },
      ]),
      tokenUsage: { ...current.tokenUsage, contextSize: current.tokenUsage.contextSize + 480 },
    }));
    if (presentation && state.todoItems.length > 0) {
      const completed = state.todoItems;
      append([createMessage(id('plan-completed'), 'agent',
        completed.map(item => `✓  ${item.content}`).join('\n') +
          `\n\n[${completed.length}/${completed.length} completed]`, 'tool_use', { streamEnd: true })]);
    }
    if (!runNext()) verifyGoal();
  };
  const run = (content, imagePaths, long = false) => {
    cancelRun();
    const turn = id('turn'), thoughtId = `${turn}-thought`, answerId = `${turn}-answer`;
    const startIdx = state.messages.length;
    const request = createMessage(`${turn}-user`, 'user', content, undefined,
      imagePaths?.length ? { imagePaths: [...imagePaths] } : {});
    publish(current => ({
      messages: [...current.messages, request, ...(current.thinkingEnabled ? [createMessage(thoughtId, 'agent',
        '先检查本轮输入和现有展示组件。', 'thinking', { isStreaming: true, streamStartId: thoughtId })] : [])],
      loading: true, activeStep: 'reasoning',
      goalState: current.goalState ? { ...current.goalState, verifying: false } : null,
      todoItems: current.todoItems.map((item, index) => ({ ...item, status: index === 2 ? 'in_progress' : 'completed' })),
      todoMessageRanges: new Map(current.todoMessageRanges).set('检查流式回复与任务入口', { startIdx, endIdx: null }),
      subAgentItems: current.subAgentItems.map(item => item.id === 'demo-verifier'
        ? { ...item, status: 'running', summary: '正在检查本轮示例。' } : item),
      subAgentMessages: new Map(current.subAgentMessages).set('demo-verifier', [
        { id: 'run-check', kind: 'thinking', text: '检查流式回复、任务状态和输入队列。', isComplete: false },
      ]),
    }));
    schedule(stepMs, () => {
      updateMessage(thoughtId, { content: '先检查本轮输入和现有展示组件。\n再展示工具调用，并在同一条回复中逐步更新文字。',
        metadata: { subtype: 'thinking', streamStartId: thoughtId, isStreaming: false, streamEnd: true } });
      append([
        createMessage(`${turn}-read`, 'agent', 'Read the file `src/components/layouts/MainLayout.tsx` from line 1 to line 40', 'tool_use'),
        createMessage(`${turn}-search`, 'agent', 'Search for: onSubmit in src with file pattern *.tsx in .', 'tool_use'),
      ]);
      publish({ activeStep: 'tool_execution' });
    }, true);
    schedule(stepMs * 2, () => {
      append([createMessage(`${turn}-command`, 'agent', 'Run the following command:\n```bash\nnpm test -- --run\n```', 'tool_use'),
        createMessage(answerId, 'agent', '', 'answer', { isStreaming: true, streamStartId: answerId })]);
      publish({ activeStep: 'reasoning' });
      const answer = `收到：${content}\n\n这是原有 Siada UI 渲染的离线流式回复。\n\n`
        + (long ? Array.from({ length: 18 }, (_, index) => `阅读步骤 ${index + 1}：输入区保持可用，可以滚动历史、选择中文和查看工具详情。`).join('\n\n') + '\n\n' : '')
        + '| 本轮内容 | 状态 |\n| --- | --- |\n| Thought 与工具 | 已展示 |\n| 流式文字与任务 | 已更新 |\n\n'
        + '输入为空时按 Tab 查看任务或子 agent；运行期间输入的新消息会进入队列。';
      const glyphs = [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(answer)].map(part => part.segment);
      let offset = 0;
      const stream = () => {
        offset = Math.min(glyphs.length, offset + (long ? 12 : 10));
        updateMessage(answerId, { content: glyphs.slice(0, offset).join('') });
        if (offset < glyphs.length) schedule(chunkMs, stream, true);
        else {
          const range = state.todoMessageRanges.get('检查流式回复与任务入口');
          publish({ todoMessageRanges: new Map(state.todoMessageRanges).set('检查流式回复与任务入口',
            { ...range, endIdx: state.messages.length }) });
          finishRun(answerId);
        }
      };
      stream();
    }, true);
  };
  const stop = (discardQueue = true) => {
    cancelRun();
    publish(current => ({
      messages: current.messages.map(message => message.metadata?.isStreaming
        ? { ...message, metadata: { ...message.metadata, isStreaming: false, streamEnd: true } } : message),
      loading: false, activeStep: null,
      goalState: current.goalState ? { ...current.goalState, verifying: false } : null,
      interactiveInput: null,
      todoItems: current.todoItems.map(item => item.status === 'in_progress' ? { ...item, status: 'pending' } : item),
      todoMessageRanges: new Map([...current.todoMessageRanges].map(([content, range]) =>
        [content, range.endIdx === null ? { ...range, endIdx: current.messages.length } : range])),
      subAgentItems: current.subAgentItems.map(item => item.status === 'running' ? { ...item, status: 'cancelled' } : item),
    }));
    if (discardQueue) queue.clear();
    const next = queue.dequeue();
    if (next) run(next.content, next.imagePaths);
  };
  const sideQuestion = question => {
    if (!question) {
      if (state.sideQuestions.length) publish({ sideQuestionPanelVisible: true });
      else notice('sideQuestionNotice', 'Usage: /btw <question>');
      return;
    }
    const questionId = id('btw');
    publish(current => ({ sideQuestions: [...current.sideQuestions, { id: questionId, question, answer: null }],
      sideQuestionPanelVisible: true, sideQuestionNotice: null }));
    schedule(stepMs, () => publish(current => ({
      sideQuestions: current.sideQuestions.map(item => item.id === questionId
        ? { ...item, answer: '这是旁路问答的离线示例。主会话保留原位置；Esc 返回，稍后可用 /btw 再次打开。' } : item),
    })));
  };
  const setGoal = objective => {
    if (objective === 'clear') { publish({ goalState: null, goalNotice: null }); return; }
    if (!objective) { notice('goalNotice', 'Usage: /goal <objective> | clear'); return; }
    publish({ goalState: { goal: { objective, status: 'active', createdAt: new Date().toISOString(), turns: 0 }, verifying: false } });
    notice('goalNotice', 'Goal set: ' + objective);
  };
  const demo = section => {
    if (!section || section === 'help') { append([createMessage(id('guide'), 'agent', demoHelp, 'answer')]); return; }
    if (section === 'reset') {
      cancelRun();
      for (const timer of timers) clearTimeout(timer);
      timers.clear(); queue.clear();
      publish({ ...initialState(), sceneId: id('scene') });
      return;
    }
    if (section === 'queue') {
      if (!state.loading) run('检查三栏布局与流式回复。');
      queue.enqueue('补充 Markdown 展示。');
      queue.enqueue('查看任务与验证结果。');
      return;
    }
    if (section === 'stream') {
      if (state.loading) queue.enqueue('继续检查较长回复的阅读。');
      else run('检查较长回复的阅读与文字选择。', undefined, true);
      return;
    }
    if (section === 'input') {
      publish({ interactiveInput: { prompt: '离线交互输入：输入 yes 继续，Esc 返回。', inputType: 'confirmation', isPassword: false } });
      return;
    }
    if (section === 'goal') {
      stop();
      setGoal('完成原有 UI 展示与交互检查');
      verifyGoal();
      return;
    }
    if (['verify', 'blocked', 'complete'].includes(section)) {
      stop();
      const achieved = section === 'complete';
      const objective = '完善目标、任务与子智能体的展示';
      const result = goalResultMessage(id('goal-result'), objective, achieved);
      publish({ goalState: { goal: { objective, status: section === 'blocked' ? 'blocked' : achieved ? 'complete' : 'active',
        createdAt: new Date().toISOString(), turns: 2 }, verifying: section === 'verify',
        ...(section === 'verify' ? {} : { result: result.metadata.goalResult }) } });
      if (section !== 'verify') append([result]);
      return;
    }
    if (section === 'compact') {
      if (state.loading) return;
      cancelRun(); publish({ loading: true, activeStep: 'compaction' });
      schedule(stepMs * 2, () => {
        publish({ loading: false, activeStep: null, tokenUsage: { ...state.tokenUsage, contextSize: 4800 } });
        append([createMessage(id('compact'), 'system', '离线上下文压缩演示完成。', 'process')]);
        runNext();
      }, true);
      return;
    }
    const messages = section === 'all'
      ? ['markdown', 'tools', 'shell', 'error'].flatMap(kind => showcaseMessages(kind, id(kind)))
      : showcaseMessages(section, id(section));
    append(messages.length ? messages : [createMessage(id('unknown'), 'system', '使用 /demo 查看可用的离线示例。')]);
  };
  const submit = (content, imagePaths) => {
    const value = content.trim();
    if (!value) return;
    const command = /^\/([\w-]+)(?:\s+([\s\S]*))?$/.exec(value);
    if (command) {
      const [, name, argument = ''] = command;
      if (name === 'demo' || name === 'help') { demo(argument.trim()); return; }
      if (name === 'btw') { sideQuestion(argument.trim()); return; }
      if (name === 'goal') { setGoal(argument.trim()); return; }
      if (name === 'model') {
        if (models.includes(argument)) publish({ model: argument });
        else publish({ screen: 'model' });
        return;
      }
      if (name === 'theme') { publish({ screen: argument === 'dark' || argument === 'light' ? `theme:${argument}` : 'theme' }); return; }
      if (name === 'effort') {
        if (efforts.includes(argument)) publish({ reasoningEffort: argument });
        else publish({ screen: 'effort' });
        return;
      }
      if (name === 'thinking') { publish({ thinkingEnabled: argument !== 'off' }); return; }
      if (name === 'task-list') { publish({ screen: 'tasks' }); return; }
      if (name === 'compact') { demo('compact'); return; }
    }
    if (state.loading) queue.enqueue(value, imagePaths);
    else run(value, imagePaths);
  };
  return {
    models, efforts, getSnapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); },
    submit, stop, updateMessage,
    addMessage: message => append([message]),
    closeScreen: () => publish({ screen: null }),
    selectModel: model => publish({ model, screen: null }),
    selectEffort: reasoningEffort => publish({ reasoningEffort, screen: null }),
    toggleCollapsed: () => publish({ isCollapsed: !state.isCollapsed }),
    hideSideQuestion: () => publish({ sideQuestionPanelVisible: false }),
    clearSideQuestions: () => publish({ sideQuestions: state.sideQuestions.slice(-1) }),
    removeSideQuestion: questionId => publish({ sideQuestions: state.sideQuestions.filter(item => item.id !== questionId) }),
    forkSideQuestion: item => { publish({ sideQuestionPanelVisible: false }); submit(item.question); },
    sendInteractiveInput: async value => {
      publish({ interactiveInput: null });
      append([createMessage(id('input'), 'system', '交互输入已收到：' + value, 'process')]);
    },
    cancelInteractiveInput: () => publish({ interactiveInput: null }),
    dispose: () => {
      disposed = true; cancelRun();
      for (const timer of timers) clearTimeout(timer);
      timers.clear(); unsubscribeQueue(); listeners.clear();
    },
  };
}