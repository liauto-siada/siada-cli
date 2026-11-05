import type { Message } from '../types/index.js';
import { isHookMessage } from './hookMessage.js';

/** Use protocol metadata, never prose matching, to identify failures. */
export function isErrorMessage(message: Message): boolean {
  return !isHookMessage(message) && (message.type === 'error' || message.metadata?.subtype === 'error' ||
    message.metadata?.subtype === 'error_box' || message.metadata?.eventType === 'error');
}