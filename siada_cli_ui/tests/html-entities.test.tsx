import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { describe, expect, it, vi } from 'vitest';
import { decodeHtmlEntities } from '../src/utils/htmlEntities.js';
import { TodoDisplay } from '../src/components/Todo/TodoDisplay.js';
import { TodoStatusBar } from '../src/components/Todo/TodoStatusBar.js';
import { TodoPlanView } from '../src/components/Chat/TodoPlanView.js';
import { MarkdownText } from '../src/components/common/MarkdownText.js';
import { getPlainTextLength } from '../src/components/markdown/InlineMarkdownRenderer.js';

vi.mock('../src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

async function frame(element: React.ReactElement, columns = 120): Promise<string> {
  const stdout = Object.assign(new PassThrough(), { columns, rows: 40 });
  let output: string | undefined;
  const app = render(element, {
    stdout, stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: result => { output = result.output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  try {
    await vi.waitFor(() => expect(output).toBeDefined());
    return output!;
  } finally {
    app.unmount();
    app.cleanup();
  }
}

describe('HTML entities at the display boundary', () => {
  it.each([
    ['--resume &lt;id&gt;', '--resume <id>'],
    ['A &amp; B &quot;x&quot; &apos;y&apos;', 'A & B "x" \'y\''],
    ['&#60;id&#x3E; &#x1F600; &#20013;', '<id> 😀 中'],
    ['&nbsp;&mdash;&hellip;', '\u00a0—…'],
    ['&amp;lt;id&amp;gt;', '&lt;id&gt;'],
    ['&unknown; &lt &#xZZ; &#x110000; &#xD800;', '&unknown; &lt &#xZZ; &#x110000; &#xD800;'],
    ['&#0;&#10;&#13;&#27;&#x9b;&#x2028;', '&#0;&#10;&#13;&#27;&#x9b;&#x2028;'],
    ['a < b && c > d', 'a < b && c > d'],
    ['&constructor; &toString; &LT;x&GT;', '&constructor; &toString; <x>'],
  ])('decodes safely: %s', (source, expected) => {
    expect(decodeHtmlEntities(source)).toBe(expected);
  });

  const items = [{ content: '验证 --resume &lt;id&gt; &amp; 工作区', status: 'in_progress' as const }];

  it.each([
    ['task list', <TodoDisplay items={items} activeIndex={0} onSelect={() => {}} onClose={() => {}} />],
    ['status bar', <TodoStatusBar items={items} />],
    ['plan', <TodoPlanView items={items} collapsed={false} />],
  ])('renders decoded %s without mutating task data', async (_name, element) => {
    const output = await frame(element);
    expect(output).toContain('验证 --resume <id> & 工作区');
    expect(output).not.toContain('&lt;');
    expect(items[0].content).toContain('&lt;');
  });

  it('decodes before wrapping a plan in a narrow terminal', async () => {
    const output = await frame(<TodoPlanView
      items={[{ content: '&lt;id&gt;&lt;id&gt;', status: 'pending' }]} collapsed={false}
    />, 16);
    expect(output).toContain('<id><id>');
    expect(output).not.toContain('more lines');
  });

  it('decodes prose, emphasis and links while retaining code entities', async () => {
    const output = await frame(<MarkdownText content={
      '普通 &lt;id&gt; **加粗 &amp;** [文档 &gt;](https://example.com/?a=1&amp;b=2)\n'
      + '`&lt;code&gt;`\n\n```html\n&lt;fenced&gt;\n```'
    } />);
    expect(output).toContain('普通 <id>');
    expect(output).toContain('加粗 &');
    expect(output).toContain('文档 >');
    expect(output).toContain('https://example.com/?a=1&b=2');
    expect(output).toContain('&lt;code&gt;');
    expect(output).toContain('&lt;fenced&gt;');
  });

  it('keeps entity-created markdown markers literal', async () => {
    expect(await frame(<MarkdownText content={'&#42;&#42;literal&#42;&#42; &lt;u&gt;text&lt;/u&gt;'} />))
      .toContain('**literal** <u>text</u>');
    expect(await frame(<MarkdownText content={'&#96;literal&#96;'} />)).toContain('`literal`');
  });

  it('measures decoded prose and literal code as displayed', () => {
    expect(getPlainTextLength('&lt;id&gt;')).toBe(4);
    expect(getPlainTextLength('`&lt;id&gt;`')).toBe(10);
    expect(getPlainTextLength('&#20013;')).toBe(2);
    expect(getPlainTextLength('&#42;&#42;x&#42;&#42;')).toBe(5);
  });
});