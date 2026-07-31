import { useEffect, useRef } from 'react';
import { promptQueueStore } from '../store/promptQueueStore.js';

/**
 * Safety-net cleanup of the UI preview queue when the agent becomes idle.
 *
 * Messages sent while loading=true are delivered to the backend immediately
 * (StdinInterruptMonitor intercepts and either injects mid-turn or queues for
 * the next turn).  In the normal flow every queued item is removed from the
 * preview the moment the backend consumes it: it emits `queue_item_consumed`,
 * which the events layer turns into "render the prompt into the conversation
 * + removeById from the store".  By the time the agent goes idle the store is
 * therefore already empty.
 *
 * This falling-edge clear() only guards against items that never received a
 * consume notification (e.g. an older backend that does not echo queue_id, or
 * a dropped notification), preventing a stale preview overlay from lingering.
 */

export function usePromptDrain(loading: boolean): void {
  const prevLoadingRef = useRef(loading);

  useEffect(() => {
    const wasLoading = prevLoadingRef.current;
    prevLoadingRef.current = loading;

    // Only act on the falling edge: busy → idle
    if (!wasLoading || loading) return;
    promptQueueStore.clear();
  }, [loading]);
}
