import type { Message } from '../types/index.js';
import stringWidth from './terminalWidth.js';
import { advanceMarkdownFence, type MarkdownCodeFence } from './markdownUtilities.js';

export interface NativeHistoryChunk {
  id: string;
  message: Message;
  continuation: boolean;
  complete: boolean;
}

interface Cursor {
  prefix: string;
  fence?: MarkdownCodeFence;
  complete: boolean;
}

function framedContent(content: string, before?: MarkdownCodeFence, after?: MarkdownCodeFence): string {
  const opener = before ? `${before.marker}${before.language ?? ''}\n` : '';
  const closer = after ? `${content.endsWith('\n') ? '' : '\n'}${after.marker}` : '';
  return opener + content + closer;
}

/** Move complete source lines out of the live frame without splitting diagrams. */
function stablePrefix(content: string, width: number, tailRows: number, before?: MarkdownCodeFence) {
  const lines = content.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  const rows = lines.map(line => Math.max(1, Math.ceil(stringWidth(line.replace(/\r?\n$/, '')) / Math.max(1, width - 4))));
  const overflow = rows.reduce((sum, row) => sum + row, 0) - tailRows;
  if (overflow < 8) return { offset: 0, fence: before };
  let offset = 0, consumed = 0, safeOffset = 0;
  let fence = before, safeFence = before;
  for (let index = 0; index < lines.length - 1 && consumed < overflow; index++) {
    const line = lines[index];
    if (!line.endsWith('\n')) break;
    offset += line.length;
    consumed += rows[index];
    fence = advanceMarkdownFence(line.replace(/\r?\n$/, ''), fence);
    if (fence?.language !== 'mermaid') {
      safeOffset = offset;
      safeFence = fence;
    }
  }
  return { offset: safeOffset, fence: safeFence };
}

/** Own only presentation offsets; the session's original messages remain intact. */
export class NativeHistoryBuffer {
  private cursors = new Map<string, Cursor>();
  private sequence = 0;

  update(messages: Message[], session: string, loading: boolean, width: number, tailRows: number) {
    const appended: NativeHistoryChunk[] = [];
    const pending: Message[] = [];
    let blocked = false;
    for (let index = 0; index < messages.length; index++) {
      const message = messages[index];
      const key = `${session}\0${message.id}`;
      let cursor = this.cursors.get(key);
      if (cursor && !message.content.startsWith(cursor.prefix)) {
        // A correction is new output; never erase previously printed history.
        cursor = undefined;
      }
      cursor ??= { prefix: '', complete: false };
      if (cursor.complete && message.content === cursor.prefix) continue;
      if (cursor.complete) cursor = { ...cursor, complete: false };
      const metadata = message.metadata;
      const complete = !metadata?.sendPending && (
        !loading || metadata?.streamEnd === true || metadata?.isStreaming === false ||
        message.type === 'user' || index < messages.length - 1 &&
          metadata?.isStreaming !== true && metadata?.streamEnd !== false
      );
      const content = message.content.slice(cursor.prefix.length);
      const splittable = message.type === 'agent' &&
        (!metadata?.subtype || metadata.subtype === 'answer');
      const split = complete ? { offset: content.length, fence: undefined } :
        !blocked && splittable ? stablePrefix(content, width, tailRows, cursor.fence) :
          { offset: 0, fence: cursor.fence };
      const offset = blocked ? 0 : split.offset;
      if (offset || complete && !blocked && !cursor.complete) {
        if (content.slice(0, offset).trim() || metadata?.goalResult || metadata?.shellExecution) {
          appended.push({
            id: `native-history-${++this.sequence}`,
            continuation: cursor.prefix.length > 0,
            complete,
            message: {
              ...message,
              content: framedContent(content.slice(0, offset), cursor.fence, split.fence),
              metadata: { ...metadata, streamEnd: true, isStreaming: false },
            },
          });
        }
        cursor = {
          prefix: cursor.prefix + content.slice(0, offset),
          fence: split.fence,
          complete,
        };
        this.cursors.set(key, cursor);
      }
      if (!cursor.complete || blocked) {
        pending.push({
          ...message,
          content: framedContent(message.content.slice(cursor.prefix.length), cursor.fence),
          metadata: { ...metadata, nativeHistoryContinuation: cursor.prefix.length > 0 },
        });
        blocked = true;
      }
    }
    return { appended, pending };
  }
}