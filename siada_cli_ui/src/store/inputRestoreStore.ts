/**
 * One-shot store carrying text the backend asked to restore into the input
 * box (reason 'restore_input'): user input that was interrupted by Ctrl+C
 * before it was persisted to the session would otherwise be lost.
 *
 * Module-level state — outside React lifecycle, same pattern as
 * promptQueueStore. The input component subscribes via useSyncExternalStore
 * and consume()s the pending text once applied to its buffer.
 */

const _listeners = new Set<() => void>();
let _pendingText: string | null = null;
let _lastRequest: { text: string; at: number } | null = null;

/** Window in which an identical restore request is treated as a duplicate. */
const DEDUPE_WINDOW_MS = 5000;

export const inputRestoreStore = {
  subscribe(listener: () => void): () => void {
    _listeners.add(listener);
    return () => _listeners.delete(listener);
  },

  getSnapshot(): string | null {
    return _pendingText;
  },

  request(text: string): void {
    _pendingText = text;
    _lastRequest = { text, at: Date.now() };
    _listeners.forEach(l => l());
  },

  /**
   * Whether the same text was requested moments ago. The App-level Ctrl+C
   * handler restores the last user bubble synchronously, and the backend's
   * 'restore_input' notification for the same interrupt arrives shortly
   * after — applying both would reset the input box a second time and clobber
   * whatever the user started typing in between.
   */
  wasRecentlyRequested(text: string): boolean {
    return (
      _lastRequest !== null &&
      _lastRequest.text === text &&
      Date.now() - _lastRequest.at < DEDUPE_WINDOW_MS
    );
  },

  /** Return the pending text and clear it (one-shot semantics). */
  consume(): string | null {
    const text = _pendingText;
    _pendingText = null;
    return text;
  },
};
