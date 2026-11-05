import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createDemoController } from '../examples/three-pane-demo-controller.mjs';
import { promptQueueStore } from '../src/store/promptQueueStore.js';

let controller: ReturnType<typeof createDemoController>;
beforeEach(() => {
  vi.useFakeTimers();
  promptQueueStore.clear();
  controller = createDemoController({ queue: promptQueueStore, stepMs: 10, chunkMs: 1 });
});
afterEach(() => {
  controller.dispose();
  promptQueueStore.clear();
  vi.useRealTimers();
});

describe('offline three-pane demo flow', () => {
  it('saves one finished plan snapshot for each completed demo run', () => {
    controller.dispose();
    controller = createDemoController({ queue: promptQueueStore, stepMs: 10, chunkMs: 1, presentation: true });
    controller.submit('完成计划');
    vi.runAllTimers();
    const first = controller.getSnapshot();
    const snapshots = first.messages.filter(message => /\[3\/3 completed\]/.test(message.content));
    expect(snapshots).toHaveLength(1);
    expect(snapshots[0].metadata.subtype).toBe('tool_use');
    controller.submit('再次执行');
    vi.runAllTimers();
    expect(controller.getSnapshot().messages.filter(message => /\[3\/3 completed\]/.test(message.content))).toHaveLength(2);
  });
  it('keeps displayed revisions immutable while streaming and completes task records', () => {
    const initial = controller.getSnapshot();
    controller.submit('检查中文输入');
    const started = controller.getSnapshot();
    const thought = started.messages.at(-1)!;
    expect(started.loading).toBe(true);
    expect(started.activeStep).toBe('reasoning');
    expect(started.subAgentItems.at(-1)?.status).toBe('running');
    expect(initial.messages).not.toBe(started.messages);
    vi.advanceTimersByTime(10);
    expect(controller.getSnapshot().activeStep).toBe('tool_execution');
    expect(thought.metadata.isStreaming).toBe(true);
    expect(controller.getSnapshot().messages.find(message => message.id === thought.id)?.metadata.isStreaming).toBe(false);
    vi.advanceTimersByTime(10);
    const partial = controller.getSnapshot().messages.at(-1)!;
    expect(partial.metadata.isStreaming).toBe(true);
    expect(partial.content.length).toBeGreaterThan(0);
    vi.runAllTimers();
    const complete = controller.getSnapshot();
    expect(partial.content.length).toBeLessThan(complete.messages.at(-1)!.content.length);
    expect(complete.messages.at(-1)?.metadata.streamEnd).toBe(true);
    expect(complete.loading).toBe(false);
    expect(complete.todoItems.every(item => item.status === 'completed')).toBe(true);
    expect(complete.subAgentItems.at(-1)?.status).toBe('completed');
    expect(complete.subAgentMessages.get('demo-verifier')?.at(-1)?.kind).toBe('message');
    expect(complete.todoMessageRanges.get('检查流式回复与任务入口')?.endIdx).toBe(complete.messages.length);
  });

  it('runs queued prompts in order and lets Esc skip the current turn', () => {
    const count = controller.getSnapshot().messages.length;
    controller.submit('第一条');
    controller.submit('第二条');
    controller.submit('第三条');
    expect(controller.getSnapshot().promptQueue.map(item => item.content)).toEqual(['第二条', '第三条']);
    controller.stop(false);
    expect(controller.getSnapshot().promptQueue.map(item => item.content)).toEqual(['第三条']);
    vi.runAllTimers();
    const state = controller.getSnapshot();
    expect(state.messages.slice(count).filter(message => message.type === 'user').map(message => message.content))
      .toEqual(['第一条', '第二条', '第三条']);
    expect(state.loading).toBe(false);
    expect(state.promptQueue).toEqual([]);
  });

  it('takes queued text back for editing without running it twice', () => {
    const count = controller.getSnapshot().messages.length;
    controller.submit('/demo queue');
    expect(controller.getSnapshot().promptQueue).toHaveLength(2);
    const editable = promptQueueStore.popAllEditable();
    expect(editable.text).toContain('补充 Markdown');
    expect(controller.getSnapshot().promptQueue).toEqual([]);
    vi.runAllTimers();
    expect(controller.getSnapshot().messages.slice(count).filter(message => message.type === 'user')).toHaveLength(1);
  });

  it('cancels old stream updates and discards the queue on Ctrl+C', () => {
    controller.submit('/demo stream');
    vi.advanceTimersByTime(21);
    controller.submit('排队内容');
    controller.stop();
    const stopped = controller.getSnapshot();
    expect(stopped.loading).toBe(false);
    expect(stopped.promptQueue).toEqual([]);
    expect(stopped.messages.some(message => message.metadata?.isStreaming)).toBe(false);
    vi.runAllTimers();
    expect(controller.getSnapshot()).toBe(stopped);
  });

  it('stops interactive input and goal verification without delayed completion', () => {
    controller.submit('/demo goal');
    controller.submit('/demo input');
    controller.stop();
    const stopped = controller.getSnapshot();
    expect(stopped.interactiveInput).toBeNull();
    expect(stopped.goalState?.verifying).toBe(false);
    vi.runAllTimers();
    expect(controller.getSnapshot().messages.some(message => message.metadata?.subtype === 'goal_result')).toBe(false);
  });

  it('preserves side-question history when hiding and reopening it', () => {
    controller.submit('/btw 能否继续阅读主会话？');
    expect(controller.getSnapshot().sideQuestionPanelVisible).toBe(true);
    expect(controller.getSnapshot().sideQuestions.at(-1)?.answer).toBeNull();
    vi.advanceTimersByTime(10);
    controller.hideSideQuestion();
    expect(controller.getSnapshot().sideQuestionPanelVisible).toBe(false);
    controller.submit('/btw');
    expect(controller.getSnapshot().sideQuestionPanelVisible).toBe(true);
    expect(controller.getSnapshot().sideQuestions).toHaveLength(1);
    expect(controller.getSnapshot().sideQuestions[0].answer).toContain('主会话保留原位置');
  });

  it('does not complete a cleared goal from an old verification timer', () => {
    controller.submit('/demo goal');
    expect(controller.getSnapshot().goalState?.verifying).toBe(true);
    controller.submit('/goal clear');
    vi.runAllTimers();
    expect(controller.getSnapshot().goalState).toBeNull();
    expect(controller.getSnapshot().messages.some(message => message.metadata?.subtype === 'goal_result')).toBe(false);
    controller.submit('/demo goal');
    vi.advanceTimersByTime(10);
    expect(controller.getSnapshot().goalState?.goal?.status).toBe('complete');
    expect(controller.getSnapshot().messages.at(-1)?.metadata.goalResult.achieved).toBe(true);
  });

  it('continues queued work after compaction and respects thinking-off', () => {
    const count = controller.getSnapshot().messages.length;
    controller.submit('/thinking off');
    controller.submit('/demo compact');
    controller.submit('压缩后的输入');
    expect(controller.getSnapshot().activeStep).toBe('compaction');
    vi.runAllTimers();
    const state = controller.getSnapshot();
    expect(state.loading).toBe(false);
    expect(state.promptQueue).toEqual([]);
    expect(state.messages.slice(count).some(message => message.metadata?.subtype === 'thinking')).toBe(false);
    expect(state.messages.slice(count).some(message => message.content.includes('压缩演示完成'))).toBe(true);
  });

  it('restores the initial scene and removes every outstanding timer on reset', () => {
    const initialIds = controller.getSnapshot().messages.map(message => message.id);
    controller.submit('/demo queue');
    controller.submit('/btw 测试');
    controller.submit('/demo reset');
    const reset = controller.getSnapshot();
    vi.runAllTimers();
    expect(controller.getSnapshot()).toBe(reset);
    expect(reset.messages.map(message => message.id)).toEqual(initialIds);
    expect(reset.sideQuestions).toEqual([]);
    expect(reset.promptQueue).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });
});