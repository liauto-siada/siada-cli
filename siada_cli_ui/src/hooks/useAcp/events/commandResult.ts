import type { Message } from '../../../types/index.js';

export interface CommandResult {
  commandId: string;
  command: string;
  content: string;
  error?: boolean;
  queueId?: string;
}

/** Append query output without touching the active model's streaming state. */
export function appendCommandResult(messages: Message[], result: CommandResult): Message[] {
  if (!result || typeof result.commandId !== 'string' || typeof result.content !== 'string') {
    return messages;
  }
  const id = `command_${result.commandId}`;
  if (messages.some(message => message.id === id)) return messages;
  return [...messages, {
    id, type: result.error ? 'error' : 'agent', content: result.content,
    timestamp: new Date().toISOString(), author: 'Siada',
    metadata: {
      subtype: 'slash_command_result', isStreaming: false, streamEnd: true,
      command: result.command, commandId: result.commandId,
    },
  }];
}