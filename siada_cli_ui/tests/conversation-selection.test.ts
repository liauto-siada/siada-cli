import { Range, Selection } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ConversationSelectionLayout, ConversationTextSelection, createSelectionFrame, SELECTION_FRAME_MS,
} from '../src/utils/conversationSelection.js';

const textNode = (nodeValue: string): any => ({ nodeName: '#text', nodeValue });
afterEach(() => vi.useRealTimers());
describe('conversation selection Unicode boundaries', () => {
  it('uses an exclusive character endpoint like Codex for both drag directions', () => {
    const layout = new ConversationSelectionLayout();
    layout.entries.set('a', { text: '中文内容', fragments: [] });
    const forward = new ConversationTextSelection(['a'], { id: 'a', offset: 0 }, 'character', layout);
    expect(forward.empty).toBe(true);
    forward.extend({ id: 'a', offset: 1 }, layout);
    expect(forward.text()).toBe('中');
    forward.extend({ id: 'a', offset: 0 }, layout);
    expect(forward.empty).toBe(true);
    const backward = new ConversationTextSelection(['a'], { id: 'a', offset: 1 }, 'character', layout);
    backward.extend({ id: 'a', offset: 0 }, layout);
    expect(backward.text()).toBe('中');
  });
  it('keeps emoji sequences and combining marks intact', () => {
    const text = 'A👩‍💻éZ';
    const layout = new ConversationSelectionLayout();
    layout.entries.set('a', { text, fragments: [] });
    const selection = new ConversationTextSelection(['a'], { id: 'a', offset: 2 }, 'character', layout);
    selection.extend({ id: 'a', offset: 7 }, layout);
    expect(selection.text()).toBe('👩‍💻');
    selection.extend({ id: 'a', offset: 8 }, layout);
    expect(selection.text()).toBe('👩‍💻é');
  });
  it('double click selects a word and triple click selects its full logical line', () => {
    const layout = new ConversationSelectionLayout();
    layout.entries.set('a', { text: 'first line\nhello world\nlast', fragments: [] });
    expect(new ConversationTextSelection(['a'], { id: 'a', offset: 13 }, 'word', layout).text()).toBe('hello');
    expect(new ConversationTextSelection(['a'], { id: 'a', offset: 13 }, 'line', layout).text()).toBe('hello world');
  });
  it('retains selected draft text while unselected status text changes', () => {
    const layout = new ConversationSelectionLayout();
    layout.entries.set('composer', { text: 'draft\nmodel one', fragments: [] });
    const selection = new ConversationTextSelection(['composer'], { id: 'composer', offset: 0 }, 'character', layout);
    selection.extend({ id: 'composer', offset: 5 }, layout);
    layout.entries.set('composer', { text: 'draft\nmodel two changed', fragments: [] });
    expect(selection.matchesSource(layout)).toBe(true);
    layout.entries.set('composer', { text: 'new draft\nmodel two changed', fragments: [] });
    expect(selection.matchesSource(layout)).toBe(false);
  });
});
describe('conversation selection block separators', () => {
  it.each([false, true])('keeps tool rows adjacent and separate groups spaced, reverse=%s', reverse => {
    const layout = new ConversationSelectionLayout();
    const entries = [
      ['command', '├─ npm test'],
      ['edit', '└─ Update example.ts'],
      ['answer', 'Done'],
      ['read', '├─ Read example.ts'],
      ['next-command', '└─ npm run build'],
    ];
    for (const [id, text] of entries) layout.entries.set(id, { text, fragments: [] });
    const first = { id: 'command', offset: 0 };
    const last = { id: 'next-command', offset: entries.at(-1)![1].length };
    const selection = new ConversationTextSelection(entries.map(([id]) => id),
      reverse ? last : first, 'character', layout, new Set(), new Set(['edit', 'next-command']));
    selection.extend(reverse ? first : last, layout);
    expect(selection.text()).toBe('├─ npm test\n└─ Update example.ts\n\nDone\n\n├─ Read example.ts\n└─ npm run build');
  });

  it('joins continuous text fragments without adding a newline and preserves logical newlines', () => {
    const layout = new ConversationSelectionLayout();
    layout.entries.set('first', { text: 'first line\nsecond ', fragments: [] });
    layout.entries.set('rest', { text: 'line', fragments: [] });
    const selection = new ConversationTextSelection(['first', 'rest'],
      { id: 'first', offset: 0 }, 'character', layout, new Set(['rest']));
    selection.extend({ id: 'rest', offset: 4 }, layout);
    expect(selection.text()).toBe('first line\nsecond line');
  });
});
describe('selection frame and visible projection', () => {
  it('commits a replacement once and skips identical ranges', () => {
    const node = textNode('hello world'), selection = new Selection();
    const changed = vi.fn();
    selection.onChange(changed);
    const range = new Range();
    range.setStart(node, 0); range.setEnd(node, 5);
    selection.setRange(range);
    expect(changed).toHaveBeenCalledTimes(1);
    const replacement = new Range();
    replacement.setStart(node, 0); replacement.setEnd(node, 5);
    selection.setRange(replacement);
    expect(changed).toHaveBeenCalledTimes(1);
    replacement.setEnd(node, 11);
    selection.setRange(replacement);
    expect(changed).toHaveBeenCalledTimes(2);
    selection.setRange();
    expect(changed).toHaveBeenCalledTimes(3);
    expect(selection.isCollapsed).toBe(true);
  });
  it('replaces queued motion within a frame, flushes on release, and cancels on close', () => {
    vi.useFakeTimers();
    const update = vi.fn(), frame = createSelectionFrame(update);
    for (let x = 0; x < 1000; x++) frame.queue({ x, y: 4 });
    expect(update).not.toHaveBeenCalled();
    vi.advanceTimersByTime(SELECTION_FRAME_MS);
    expect(update).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith({ x: 999, y: 4 });
    frame.queue({ x: 10, y: 5 }); frame.flush();
    expect(update).toHaveBeenLastCalledWith({ x: 10, y: 5 });
    frame.queue({ x: 3, y: 2 }); frame.cancel();
    vi.advanceTimersByTime(SELECTION_FRAME_MS);
    expect(update).toHaveBeenCalledTimes(2);
  });
});