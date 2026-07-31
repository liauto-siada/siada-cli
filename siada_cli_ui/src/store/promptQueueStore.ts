import type { PromptQueueItem } from '../types/index.js';

// Module-level state — outside React lifecycle to avoid Ink batching issues
const _queue: PromptQueueItem[] = [];
const _listeners = new Set<() => void>();

// Immutable snapshot consumed by useSyncExternalStore.
//
// IMPORTANT: useSyncExternalStore bails out of re-rendering whenever
// getSnapshot() returns a value that is Object.is-equal to the previous one.
// `_queue` is mutated in place (push/splice), so returning it directly keeps
// the SAME array reference forever and the preview never updates — which is
// exactly why the queue looked like it "did nothing". We therefore keep a
// frozen copy that is regenerated (new reference) on every mutation, and
// return that stable copy from getSnapshot() between mutations.
let _snapshot: PromptQueueItem[] = [];

function _notify(): void {
  // Regenerate the snapshot reference so useSyncExternalStore detects a change.
  _snapshot = _queue.slice();
  _listeners.forEach(l => l());
}

export const promptQueueStore = {
  subscribe(listener: () => void): () => void {
    _listeners.add(listener);
    return () => _listeners.delete(listener);
  },

  getSnapshot(): PromptQueueItem[] {
    return _snapshot;
  },


  enqueue(content: string, imagePaths?: string[]): PromptQueueItem {
    const item: PromptQueueItem = {
      id: `queue-${Date.now()}-${Math.random()}`,
      content,
      imagePaths,
      addedAt: new Date().toISOString(),
    };
    _queue.push(item);
    _notify();
    return item;
  },

  getById(id: string): PromptQueueItem | undefined {
    return _queue.find(i => i.id === id);
  },

  removeById(id: string): void {
    const idx = _queue.findIndex(i => i.id === id);
    if (idx !== -1) {
      _queue.splice(idx, 1);
      _notify();
    }
  },

  dequeue(): PromptQueueItem | undefined {
    if (_queue.length === 0) return undefined;
    const item = _queue.shift();
    _notify();
    return item;
  },

  clear(): void {
    _queue.length = 0;
    _notify();
  },

  getLength(): number {
    return _queue.length;
  },

  /**
   * Drain all queued items and return their combined content.
   * Mirrors Claude Code's `popAllEditable`: collects all items (every item is
   * considered editable in siada-cli), clears the store, and returns the merged
   * text and collected image paths so the caller can restore them to the input box.
   */
  popAllEditable(): { text: string; imagePaths: string[] } {
    if (_queue.length === 0) return { text: '', imagePaths: [] };
    const items = _queue.splice(0, _queue.length);
    _notify();
    const text = items.map(i => i.content).join('\n');
    const imagePaths = items.flatMap(i => i.imagePaths ?? []);
    return { text, imagePaths };
  },
};
