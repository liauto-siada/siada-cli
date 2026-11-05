import { describe, expect, it } from 'vitest';
import { NativeHistoryBuffer } from '../src/utils/nativeHistory.js';
import type { Message } from '../src/types/index.js';

function answer(content: string, complete = false): Message {
  return { id: 'answer', type: 'agent', content, author: 'Synthetic', timestamp: '',
    metadata: { subtype: 'answer', streamEnd: complete, isStreaming: !complete } };
}

describe('native history source ownership', () => {
  it('commits a completed response once and keeps the source intact', () => {
    const buffer = new NativeHistoryBuffer();
    const message = answer('COMPLETE\nSECOND LINE', true);
    expect(buffer.update([message], 'first', false, 80, 8).appended[0].message.content).toBe(message.content);
    expect(buffer.update([{ ...message }], 'first', false, 60, 4)).toEqual({ appended: [], pending: [] });
    expect(message.content).toBe('COMPLETE\nSECOND LINE');
  });
  it('moves complete lines into history while retaining an editable tail', () => {
    const buffer = new NativeHistoryBuffer();
    const content = Array.from({ length: 100 }, (_, i) => `LINE_${i}\n`).join('');
    const first = buffer.update([answer(content)], 'first', true, 80, 8);
    expect(first.appended[0].message.content).toContain('LINE_0\n');
    expect(first.appended[0].message.content).not.toContain('LINE_99\n');
    expect(first.pending[0].content).toContain('LINE_99\n');
    expect(first.pending[0].metadata?.nativeHistoryContinuation).toBe(true);
    const last = buffer.update([answer(content, true)], 'first', false, 80, 8);
    expect(first.appended[0].message.content + last.appended[0].message.content).toBe(content);
    expect(last.pending).toEqual([]);
    expect(buffer.update([answer(content, true)], 'first', false, 80, 8).appended).toEqual([]);
  });
  it('does not freeze a short incomplete line', () => {
    const buffer = new NativeHistoryBuffer();
    expect(buffer.update([answer('unfinished **bold')], 'first', true, 80, 8).appended).toEqual([]);
    expect(buffer.update([answer('unfinished **bold text**', true)], 'first', false, 80, 8)
      .appended[0].message.content).toBe('unfinished **bold text**');
  });
  it('keeps ordinary code fences around every continuation without repeating source lines', () => {
    const buffer = new NativeHistoryBuffer();
    const content = '```ts\n' + Array.from({ length: 50 }, (_, i) => `const VALUE_${i} = ${i};\n`).join('');
    const first = buffer.update([answer(content)], 'first', true, 80, 8);
    expect(first.appended[0].message.content).toMatch(/^```ts\n[\s\S]+\n```$/);
    expect(first.pending[0].content).toMatch(/^```ts\n/);
    const last = buffer.update([answer(content + '```\nAFTER_CODE', true)], 'first', false, 80, 8);
    const source = [...first.appended, ...last.appended].map(chunk => chunk.message.content).join('\n');
    for (let i = 0; i < 50; i++) expect(source.split(`const VALUE_${i} =`).length - 1).toBe(1);
    expect(source).toContain('AFTER_CODE');
  });
  it('holds an unfinished diagram instead of printing an invalid partial graph', () => {
    const buffer = new NativeHistoryBuffer();
    const content = '```mermaid\nflowchart TD\n' + 'A --> B\n'.repeat(50);
    expect(buffer.update([answer(content)], 'first', true, 80, 8).appended).toEqual([]);
    expect(buffer.update([answer(content + '```', true)], 'first', false, 80, 8)
      .appended[0].message.content).toBe(content + '```');
  });
  it('holds later messages behind an unfinished earlier message', () => {
    const buffer = new NativeHistoryBuffer();
    const earlier = answer('pending');
    const later = { ...answer('LATER', true), id: 'later' };
    expect(buffer.update([earlier, later], 'first', true, 80, 8).appended).toEqual([]);
    expect(buffer.update([answer('pending', true), later], 'first', false, 80, 8)
      .appended.map(chunk => chunk.message.content)).toEqual(['pending', 'LATER']);
  });
  it('distinguishes sessions and prints corrections without erasing old output', () => {
    const buffer = new NativeHistoryBuffer();
    const message = answer('ORIGINAL', true);
    expect(buffer.update([message], 'first', false, 80, 8).appended).toHaveLength(1);
    expect(buffer.update([message], 'second', false, 80, 8).appended).toHaveLength(1);
    expect(buffer.update([message], 'first', false, 80, 8).appended).toEqual([]);
    expect(buffer.update([answer('CORRECTION', true)], 'first', false, 80, 8)
      .appended[0].message.content).toBe('CORRECTION');
  });
});