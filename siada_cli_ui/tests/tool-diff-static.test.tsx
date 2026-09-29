import React, { useRef, type SetStateAction } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { Message as MessageType } from '../src/types/index.js';
import { useStreamingMessages } from '../src/hooks/useAcp/streaming/index.js';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    Text: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
    Static: ({ items, children }: { items: unknown[]; children: (item: unknown, index: number) => React.ReactNode }) => (
      <section data-area="static">{items.map((item, index) => children(item, index))}</section>
    ),
    useStdout: () => ({ stdout: { rows: 24, columns: 80 } }),
  };
});

vi.mock('../src/components/Chat/Message.js', () => ({
  Message: ({ message }: { message: MessageType }) => <p data-id={message.id}>{message.content}</p>,
}));

import { MessageList } from '../src/components/Chat/MessageList.js';
import { FileChangeSetView } from '../src/components/diff/FileChangeSetView.js';
import { parseApplyPatchContent } from '../src/utils/diff.js';

const EDIT = 'In the file `src/a.ts``, replace the string:\n```ts\nold\n```\nwith:\n```ts\nnew\n```';
const PATCH = `Apply patch: 1 file changed

<!-- siada-apply-patch:start -->
### Update \`src/a.ts\`
\`\`\`diff
--- a/src/a.ts
+++ b/src/a.ts
@@ -1 +1 @@
-old
+new
\`\`\`
<!-- siada-apply-patch:end -->`;

function toolMessage(id: string, content: string, streamEnd: boolean): MessageType {
  return {
    id,
    type: 'agent',
    content,
    timestamp: '2026-01-01T00:00:00.000Z',
    author: 'Siada',
    metadata: { subtype: 'tool_use', streamEnd, isStreaming: !streamEnd },
  };
}

function renderList(messages: MessageType[], noStatic = false, isCollapsed = false): string {
  return renderToStaticMarkup(<MessageList messages={messages} noStatic={noStatic} isCollapsed={isCollapsed} />);
}

describe('completed tool diff placement', () => {
  it.each([['edit', EDIT], ['apply_patch', PATCH]])(
    'commits a short completed %s diff directly to Static', (_name, content) => {
      const output = renderList([toolMessage('diff', content, true)]);
      expect(output).toMatch(/<section data-area="static">[\s\S]*data-id="diff"[\s\S]*<\/section>/);
    },
  );

  it.each([['edit', EDIT], ['apply_patch', PATCH]])(
    'keeps an unfinished %s tool stream dynamic even when the text is parseable', (_name, content) => {
      const output = renderList([toolMessage('diff', content, false)]);
      expect(output).toMatch(/<\/section><p data-id="diff">/);
    },
  );

  it.each([['edit', EDIT], ['apply_patch', PATCH]])(
    'keeps an unfinished %s diff dynamic in compact mode', (_name, content) => {
      const output = renderList([toolMessage('diff', content, false)], false, true);
      expect(output).toMatch(/<\/section><p data-id="diff">/);
    },
  );

  it('keeps short non-diff tool boxes dynamic, but commits a diff before the next message', () => {
    const output = renderList([
      toolMessage('diff', PATCH, true),
      toolMessage('notice', 'Read the file `src/a.ts`', true),
    ]);
    expect(output).toMatch(/data-id="diff"[\s\S]*<\/section><p data-id="notice">/);
  });

  it('does not commit an incomplete patch protocol even if its tool event has ended', () => {
    const output = renderList([toolMessage('incomplete', 'Apply patch: 1 file changed', true)]);
    expect(output).toMatch(/<\/section><p data-id="incomplete">/);
  });

  it('does not use Ink Static in noStatic mode', () => {
    const output = renderList([toolMessage('diff', EDIT, true)], true);
    expect(output).not.toContain('data-area="static"');
    expect(output).toContain('data-id="diff"');
  });

  it.each([['edit', EDIT], ['apply_patch', PATCH]])(
    'keeps completed %s diffs independent of later aggregated tool calls in compact mode', (_name, content) => {
      const output = renderList([
        toolMessage('diff', content, true),
        toolMessage('notice', 'Read the file `src/a.ts`', true),
      ], false, true);
      expect(output).toMatch(/data-id="diff"[\s\S]*<\/section>/);
      expect(output.replace(/<[^>]*>/g, '')).toContain('Read 1 file');
    },
  );

  it('renders a resumed patch diff without a submitted-history notice', () => {
    const historyText = PATCH.replace(
      '<!-- siada-apply-patch:start -->',
      '<!-- siada-apply-patch:history-preview -->\n<!-- siada-apply-patch:start -->',
    );
    const patch = parseApplyPatchContent(historyText)!;
    const output = renderToStaticMarkup(<FileChangeSetView {...patch} />);
    expect(output).not.toContain('Submitted patch');
    expect(output).toContain('old');
    expect(output).toContain('new');
  });
});

describe('one-shot diff metadata', () => {
  it('marks only completed edit/apply_patch diff boxes, leaving other tools unchanged', () => {
    let messages: MessageType[] = [];
    let handleToolUse: ReturnType<typeof useStreamingMessages>['handleToolUse'] | undefined;
    const setMessages = (update: SetStateAction<MessageType[]>) => {
      messages = typeof update === 'function' ? update(messages) : update;
    };

    function Harness() {
      const pullHistoryTimeoutRef = useRef<NodeJS.Timeout | null>(null);
      const messagesRef = useRef<MessageType[]>([]);
      handleToolUse = useStreamingMessages({
        setMessages,
        setBannerInfo: () => {},
        stdout: null,
        workingDir: '.',
        model: undefined,
        pullHistoryTimeoutRef,
        messagesRef,
        setTodoItems: () => {},
        setTodoMessageRanges: () => {},
      }).handleToolUse;
      return null;
    }

    renderToStaticMarkup(<Harness />);
    expect(handleToolUse).toBeDefined();

    for (const content of [EDIT, PATCH]) {
      handleToolUse!({ content, metadata: { chunkIndex: 0, streamEnd: true } });
    }
    expect(messages[0]?.metadata).toEqual({ subtype: 'tool_use', chunkIndex: 0, streamEnd: true });
    expect(messages[1]?.metadata).toEqual({ subtype: 'tool_use', chunkIndex: 0, streamEnd: true });
    expect(renderList(messages.slice(1))).toMatch(/data-area="static"[\s\S]*data-id=/);

    handleToolUse!({ content: 'Read the file `src/a.ts`', metadata: { chunkIndex: 0, streamEnd: true } });
    expect(messages[2]?.metadata).toEqual({ subtype: 'tool_use', chunkIndex: 0 });
    handleToolUse!({ content: 'In the file `src/a.ts``, replace ', metadata: { chunkIndex: 0, streamEnd: false } });
    expect(messages[3]?.metadata).toEqual({ subtype: 'tool_use', chunkIndex: 0 });
    handleToolUse!({ content: 'the string:\n```ts\nold\n```\nwith:\n```ts\nnew\n```', metadata: { chunkIndex: 1, streamEnd: true } });
    expect(messages[3]?.content).toBe(EDIT);
    expect(messages[3]?.metadata).toEqual({ subtype: 'tool_use', chunkIndex: 1 });
  });
});
