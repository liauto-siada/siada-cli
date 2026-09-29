/**
 * Message-list helpers for the ACP event layer.
 */

import type { Message } from '../../../types/index.js';

/**
 * Remove the LAST user-typed message whose content equals ``content``.
 *
 * Used when the backend hands an interrupted, never-persisted input back to
 * the input box (reason 'restore_input'): the optimistic user bubble that was
 * rendered at submit time must disappear with it, because the message never
 * made it into the session history.
 *
 * Scans from the end so that, when the same text was sent twice in a row,
 * only the newest (unpersisted) bubble is dropped. Returns the original list
 * (same reference semantics as the caller's state updater) when nothing
 * matches.
 */
export function removeLastUserMessage(
  messages: Message[],
  content: string,
): Message[] {
  if (!content) {
    return messages;
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.type === 'user' && message.content === content) {
      return [...messages.slice(0, i), ...messages.slice(i + 1)];
    }
  }
  return messages;
}
