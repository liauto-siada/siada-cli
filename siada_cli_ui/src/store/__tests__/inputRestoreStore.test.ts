/**
 * inputRestoreStore Tests
 *
 * Holds a one-shot text payload the backend asked to restore into the input
 * box (e.g. user input that was interrupted before being persisted).
 */

import { describe, it, expect, vi } from 'vitest';
import { inputRestoreStore } from '../inputRestoreStore.js';

describe('inputRestoreStore', () => {
  it('starts empty', () => {
    expect(inputRestoreStore.getSnapshot()).toBeNull();
  });

  it('stores the requested text and notifies listeners', () => {
    let notified = 0;
    const unsubscribe = inputRestoreStore.subscribe(() => { notified += 1; });

    inputRestoreStore.request('fix the bug');

    expect(inputRestoreStore.getSnapshot()).toBe('fix the bug');
    expect(notified).toBe(1);
    unsubscribe();
  });

  it('consume() returns the pending text and clears it', () => {
    inputRestoreStore.request('fix the bug');

    const text = inputRestoreStore.consume();

    expect(text).toBe('fix the bug');
    expect(inputRestoreStore.getSnapshot()).toBeNull();
    expect(inputRestoreStore.consume()).toBeNull();
  });

  it('unsubscribe stops notifications', () => {
    let notified = 0;
    const unsubscribe = inputRestoreStore.subscribe(() => { notified += 1; });
    unsubscribe();

    inputRestoreStore.request('again');

    expect(notified).toBe(0);
  });

  it('wasRecentlyRequested is true for the same text right after request', () => {
    inputRestoreStore.request('restore me');

    expect(inputRestoreStore.wasRecentlyRequested('restore me')).toBe(true);
  });

  it('wasRecentlyRequested is false for different text', () => {
    inputRestoreStore.request('restore me');

    expect(inputRestoreStore.wasRecentlyRequested('something else')).toBe(false);
  });

  it('wasRecentlyRequested is false after the dedupe window passes', () => {
    vi.useFakeTimers();
    try {
      inputRestoreStore.request('restore me');
      vi.advanceTimersByTime(6000);

      expect(inputRestoreStore.wasRecentlyRequested('restore me')).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});
