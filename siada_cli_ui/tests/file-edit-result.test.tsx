import React, { useRef, type SetStateAction } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Message as MessageType } from '../src/types/index.js';
import { useStreamingMessages } from '../src/hooks/useAcp/streaming/index.js';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children, borderStyle }: { children?: React.ReactNode; borderStyle?: string }) => (
      <div {...(borderStyle ? { 'data-border-style': borderStyle } : {})}>{children}</div>
    ),
    Text: ({ children, color, bold }: { children?: React.ReactNode; color?: string; bold?: boolean }) => (
      <span data-color={color} data-bold={bold}>{children}</span>
    ),
    Static: ({ items, children }: { items: unknown[]; children: (item: unknown, index: number) => React.ReactNode }) => (
      <section data-area="static">{items.map((item, index) => children(item, index))}</section>
    ),
    useStdout: () => ({ stdout: { rows: 48, columns: 120 } }),
  };
});

import { MessageList } from '../src/components/Chat/MessageList.js';
import { Message } from '../src/components/Chat/Message.js';
import { isFileEditAwaitingResult, isRenderableToolDiff, parseFileEditPresentation } from '../src/utils/diff.js';
import { colors } from '../src/utils/colors.js';
import { setActiveTheme } from '../src/themes/index.js';

function content(callId: string, status: string, extra: Record<string, unknown> = {}): string {
  return `File edit: update src/example.rs\n<!-- siada-file-edit:start -->\n${JSON.stringify({
    callId, action: 'update', path: 'src/example.rs', status, ...extra,
  })}\n<!-- siada-file-edit:end -->`;
}

function message(id: string, body: string): MessageType {
  const edit = parseFileEditPresentation(body)!;
  return { id, type: 'agent', content: body, author: 'Siada', timestamp: '2026-01-01T00:00:00.000Z',
    metadata: { subtype: 'tool_use', toolCallId: edit.callId, streamEnd: !isFileEditAwaitingResult(edit) } };
}

const visible = (html: string) => html.replace(/<[^>]*>/g, '');
afterEach(() => setActiveTheme('dark'));

describe('result-aware edit_file display', () => {
  it.each(['dark', 'light'] as const)('uses shared borderless failed tool headings in %s mode', theme => {
    setActiveTheme(theme);
    const body = content('failed', 'failed', {
      error: 'Invalid JSON arguments; no changes applied.', details: 'Incomplete replacement arguments.',
    });
    for (const collapsed of [false, true]) {
      const output = renderToStaticMarkup(<Message message={message('failed', body)} isCollapsed={collapsed} disableTruncation />);
      expect(visible(output)).toContain('● Update src/example.rs');
      expect(visible(output)).toContain('Invalid JSON arguments; no changes applied.');
      expect(output).toContain(`<span data-color="${colors.error}" data-bold="true">Update</span>`);
      expect(output).not.toContain('data-border-style');
      expect(output).not.toContain('siada-file-edit');
      if (!collapsed) expect(visible(output)).toContain('Incomplete replacement arguments.');
    }
  });

  it.each([false, true])('does not show requested diff while awaiting execution, collapsed=%s', collapsed => {
    const body = content('pending', 'pending', { oldString: 'old', newString: 'new' });
    const output = renderToStaticMarkup(<Message message={message('pending', body)} isCollapsed={collapsed} disableTruncation />);
    expect(visible(output)).toContain('Waiting for tool result...');
    expect(visible(output)).not.toContain('(+1 -1)');
    expect(output).not.toContain('data-border-style');
    expect(isRenderableToolDiff(body)).toBe(false);
  });

  it('renders successful replacement, null-normalized deletion, and insert using normal diff view', () => {
    for (const [extra, stats] of [
      [{ oldString: 'old', newString: 'new' }, '(+1 -1)'],
      [{ oldString: 'old', newString: '' }, '(+0 -1)'],
      [{ oldString: '', newString: 'new', insertLine: 42 }, '(+1 -0)'],
      [{ oldString: '', newString: '\n', insertLine: 42 }, '(+1 -0)'],
      [{ oldString: '', newString: 'new\n\n', insertLine: 42 }, '(+2 -0)'],
    ] as const) {
      const body = content('completed', 'completed', extra);
      for (const collapsed of [false, true]) {
        const output = renderToStaticMarkup(<Message message={message('done', body)} isCollapsed={collapsed} disableTruncation />);
        expect(visible(output)).toContain(`● Update src/example.rs ${stats}`);
        expect(output).not.toContain('data-border-style');
      }
      expect(isRenderableToolDiff(body)).toBe(true);
    }
    expect(parseFileEditPresentation(content('insert', 'completed', {
      oldString: '', newString: 'new', insertLine: 42,
    }))?.hunks[0]?.newStart).toBe(43);
  });

  it('keeps unknown historical results unverified instead of inventing an applied diff', () => {
    const body = content('unknown', 'unverified', { details: 'Tool result unavailable; changes not verified.' });
    const output = visible(renderToStaticMarkup(<Message message={message('unknown', body)} disableTruncation />));
    expect(output).toContain('changes not verified');
    expect(output).not.toContain('(+');
  });

  it.each([false, true])('preserves rejection and custom result text in the status view, collapsed=%s', collapsed => {
    for (const [status, extra, reason] of [
      ['failed', { error: 'Hook blocked this tool call.' }, 'Hook blocked this tool call.'],
      ['unverified', { details: 'Tool result not recognized; changes not verified.\nPolicy forbids editing this file.' }, 'Policy forbids editing this file.'],
    ] as const) {
      const body = content('result', status, extra);
      const output = visible(renderToStaticMarkup(<Message message={message('result', body)} isCollapsed={collapsed} disableTruncation />));
      expect(output).toContain(reason);
      expect(output).not.toContain('(+');
      expect(output).not.toContain('Tool result unavailable');
    }
  });

  it('bounds expensive unrelated line diffs without claiming no changes', () => {
    const body = content('large', 'completed', {
      oldString: Array.from({ length: 501 }, (_, i) => `old ${i}\n`).join(''),
      newString: Array.from({ length: 501 }, (_, i) => `new ${i}\n`).join(''),
    });
    const edit = parseFileEditPresentation(body)!;
    expect(edit.status).toBe('completed');
    expect(edit.hunks).toHaveLength(0);
    expect(edit.details).toContain('Diff omitted');
  });

  it('rejects malformed envelopes and preserves embedded protocol markers in escaped JSON', () => {
    for (const body of [content('', 'completed'), content('call', 'bogus'),
      content('call', 'completed', { oldString: null, newString: 'new' }),
      content('call', 'completed', { insertLine: -1 }),
      content('call', 'completed', { newString: 'missing old text' }),
      content('call', 'completed', { argumentsComplete: false }),
      content('call', 'completed', { executionStatus: 'failed' }),
      content('call', 'failed', { argumentsComplete: 'no' }),
      content('call', 'failed', { executionStatus: 'bogus' }), `${content('call', 'failed')}extra`]) {
      expect(parseFileEditPresentation(body)).toBeNull();
    }
    const newString = '<!-- siada-file-edit:end -->\n```\nwith:\n\n';
    const body = content('call', 'completed', { oldString: '', newString }).replaceAll('<', '\\u003c');
    // Escape only the JSON body, as the backend does.
    const escaped = body.replace('\\u003c!-- siada-file-edit:start -->', '<!-- siada-file-edit:start -->')
      .replace(/\\u003c!-- siada-file-edit:end -->$/, '<!-- siada-file-edit:end -->');
    expect(parseFileEditPresentation(escaped)?.hunks.flatMap(h => h.lines)).toContain('+<!-- siada-file-edit:end -->');
  });

  it('keeps pending edits and later records outside append-only Static in chronological order', () => {
    const pending = message('pending', content('pending', 'pending'));
    const later = message('later', content('later', 'completed', { oldString: 'old', newString: 'new' }));
    for (const collapsed of [false, true]) {
      const output = renderToStaticMarkup(<MessageList messages={[pending, later]} isCollapsed={collapsed} />);
      expect(visible(output.slice(0, output.indexOf('</section>')))).not.toContain('Update src/example.rs');
      expect(visible(output.slice(output.indexOf('</section>')))).toContain('Waiting for tool result...');
      expect(visible(output.slice(output.indexOf('</section>')))).toContain('(+1 -1)');
    }
    const done = message('pending', content('pending', 'failed', { error: 'No match.' }));
    const output = renderToStaticMarkup(<MessageList messages={[done, later]} />);
    expect(visible(output.slice(0, output.indexOf('</section>')))).toContain('No match.');
  });

  it('keeps early JSON errors dynamic until the execution result arrives', () => {
    const body = content('invalid', 'failed', {
      argumentsComplete: false, executionStatus: 'pending', error: 'Invalid JSON arguments; no changes applied.',
    });
    expect(isRenderableToolDiff(body)).toBe(false);
    const output = renderToStaticMarkup(<MessageList messages={[message('invalid', body)]} />);
    expect(visible(output.slice(0, output.indexOf('</section>')))).not.toContain('Invalid JSON');
    expect(visible(output.slice(output.indexOf('</section>')))).toContain('Invalid JSON');
  });

  it('updates the matching call once across interleaved calls and a failed-call retry', () => {
    let messages: MessageType[] = [];
    let handleToolUse: ((data: unknown) => void) | undefined;
    const setMessages = (update: SetStateAction<MessageType[]>) => {
      messages = typeof update === 'function' ? update(messages) : update;
    };
    function Harness() {
      handleToolUse = useStreamingMessages({
        setMessages, setBannerInfo: () => {}, stdout: null, workingDir: '.', model: undefined,
        pullHistoryTimeoutRef: useRef(null), messagesRef: useRef([]),
        setTodoItems: () => {}, setTodoMessageRanges: () => {},
      }).handleToolUse;
      return null;
    }
    renderToStaticMarkup(<Harness />);
    const emit = (body: string) => handleToolUse!({ content: body, metadata: { chunkIndex: 0, streamEnd: true } });
    emit(content('a', 'pending'));
    const aId = messages[0]!.id;
    emit(content('b', 'pending'));
    emit(content('b', 'completed', { oldString: 'old', newString: 'new' }));
    emit(content('a', 'failed', { error: 'Invalid JSON arguments; no changes applied.' }));
    emit(content('retry', 'pending'));
    emit(content('retry', 'completed', { oldString: 'old', newString: 'retry' }));
    emit(content('a', 'pending'));
    expect(messages).toHaveLength(3);
    expect(messages[0]!.id).toBe(aId);
    expect(messages.map(m => parseFileEditPresentation(m.content)?.status)).toEqual(['failed', 'completed', 'completed']);
    expect(messages.every(m => m.metadata?.streamEnd === true)).toBe(true);
    // A completed result can arrive without its earlier pending update.
    emit(content('one-shot', 'completed', { oldString: 'old', newString: 'new' }));
    expect(messages).toHaveLength(4);
  });
});
