/**
 * removeLastUserMessage Tests
 *
 * When the backend restores an unpersisted input (reason 'restore_input'),
 * the optimistically-rendered user bubble for that input must disappear from
 * the conversation view — the message never reached the session history.
 */

import { describe, it, expect } from 'vitest';
import { removeLastUserMessage } from '../messageRemoval.js';
import type { Message } from '../../../../types/index.js';

function msg(id: string, type: Message['type'], content: string): Message {
  return { id, type, content, timestamp: '2026-01-01T00:00:00Z', author: 'x' };
}

describe('removeLastUserMessage', () => {
  it('removes the trailing user bubble whose content matches', () => {
    const messages = [
      msg('a1', 'agent', 'previous reply'),
      msg('u1', 'user', 'fix the bug'),
    ];

    const result = removeLastUserMessage(messages, 'fix the bug');

    expect(result.map(m => m.id)).toEqual(['a1']);
  });

  it('removes only the LAST matching user bubble when duplicated', () => {
    const messages = [
      msg('u1', 'user', 'fix the bug'),
      msg('a1', 'agent', 'done'),
      msg('u2', 'user', 'fix the bug'),
    ];

    const result = removeLastUserMessage(messages, 'fix the bug');

    expect(result.map(m => m.id)).toEqual(['u1', 'a1']);
  });

  it('skips non-user messages while scanning from the end', () => {
    const messages = [
      msg('u1', 'user', 'fix the bug'),
      msg('s1', 'system', 'note'),
      msg('a1', 'agent', 'partial'),
    ];

    const result = removeLastUserMessage(messages, 'fix the bug');

    expect(result.map(m => m.id)).toEqual(['s1', 'a1']);
  });

  it('returns the list unchanged when no user message matches', () => {
    const messages = [
      msg('u1', 'user', 'something else'),
      msg('a1', 'agent', 'reply'),
    ];

    const result = removeLastUserMessage(messages, 'fix the bug');

    expect(result).toEqual(messages);
  });

  it('returns the list unchanged for empty content', () => {
    const messages = [msg('u1', 'user', 'fix the bug')];

    const result = removeLastUserMessage(messages, '');

    expect(result).toEqual(messages);
  });
});
