import { useSyncExternalStore } from 'react';
import { promptQueueStore } from '../store/promptQueueStore.js';
import type { PromptQueueItem } from '../types/index.js';

export function usePromptQueueSnapshot(): PromptQueueItem[] {
  return useSyncExternalStore(
    promptQueueStore.subscribe,
    promptQueueStore.getSnapshot,
  );
}
