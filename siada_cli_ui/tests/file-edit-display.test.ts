import { describe, expect, it } from 'vitest';
import { getSimplePatch, isRenderableToolDiff, parseFileEditContent } from '../src/utils/diff.js';

function legacyEdit(filePath: string, oldString: string, newString: string): string {
  return `In the file \`${filePath}\`\`, replace the string:\n${oldString}\nwith:\n${newString}`;
}

function fencedEdit(filePath: string, oldString: string, newString: string, ticks = '```'): string {
  const language = filePath.endsWith('.py') ? 'python' : 'markdown';
  return legacyEdit(filePath, `${ticks}${language}\n${oldString}\n${ticks}`, `${ticks}${language}\n${newString}\n${ticks}`);
}

describe('file replacement diff protocol', () => {
  it.each(['md', 'markdown', 'mdown', 'mkd', 'MD'])(
    'parses legacy unfenced .%s replacements', extension => {
      const filePath = `docs/notes.${extension}`;
      const oldString = '旧的说明\n\n保留的说明';
      const newString = '新的说明\n\n保留的说明';
      const content = legacyEdit(filePath, oldString, newString);
      expect(parseFileEditContent(content)).toEqual({ filePath, oldString, newString, isComplete: true });
      expect(isRenderableToolDiff(content)).toBe(true);
    },
  );

  it.each(['docs/notes.md', 'src/example.py'])(
    'parses fenced replacements for %s', filePath => {
      const content = fencedEdit(filePath, 'old', 'new');
      expect(parseFileEditContent(content)).toEqual({ filePath, oldString: 'old', newString: 'new', isComplete: true });
      expect(isRenderableToolDiff(content)).toBe(true);
      expect(parseFileEditContent(content.replace('``, replace', '`, replace'))?.newString).toBe('new');
    },
  );

  it('preserves embedded code fences and separator lines in the fenced protocol', () => {
    const oldString = '```ts\nold\n```\nwith:\nold description';
    const newString = '```ts\nnew\n```\nwith:\nnew description';
    const content = fencedEdit('docs/notes.md', oldString, newString, '````');
    expect(parseFileEditContent(content)).toEqual({ filePath: 'docs/notes.md', oldString, newString, isComplete: true });
    expect(isRenderableToolDiff(content)).toBe(true);
  });

  it('keeps code fences that belong to legacy Markdown content', () => {
    const oldString = '```ts\nold\n```';
    const newString = '```ts\nnew\n```';
    expect(parseFileEditContent(legacyEdit('docs/notes.md', oldString, newString))).toEqual({
      filePath: 'docs/notes.md', oldString, newString, isComplete: true,
    });
  });

  it.each([legacyEdit, fencedEdit])('preserves whitespace and supports empty replacement text', format => {
    for (const [oldString, newString] of [
      ['\n旧的说明\n\n', '\n新的说明\n\n'],
      ['old\n\n', ''],
      ['', 'new\n\n'],
    ]) {
      const content = format('docs/notes.md', oldString, newString);
      expect(parseFileEditContent(content)).toEqual({ filePath: 'docs/notes.md', oldString, newString, isComplete: true });
      expect(isRenderableToolDiff(content)).toBe(true);
    }
    const content = format('docs/notes.md', 'old', 'new\n\n');
    const edit = parseFileEditContent(content)!;
    expect(getSimplePatch(edit.filePath, edit.oldString, edit.newString).flatMap(hunk => hunk.lines))
      .toContain('+');
  });

  it('recognizes the historical empty-old-text placeholder', () => {
    expect(parseFileEditContent(legacyEdit('docs/notes.md', '```\n\n```', 'new'))?.oldString).toBe('');
  });

  it.each([legacyEdit, fencedEdit])('accepts tool markers and CRLF protocol lines', format => {
    const content = `▶ TOOL USE ${format('docs/notes.md', 'old', 'new')}`.replaceAll('\n', '\r\n');
    expect(parseFileEditContent(content)).toEqual({ filePath: 'docs/notes.md', oldString: 'old', newString: 'new', isComplete: true });
    expect(isRenderableToolDiff(content)).toBe(true);
  });

  it('does not guess the separator in ambiguous legacy Markdown', () => {
    for (const oldString of ['old\nwith:\nold description', 'old\nwith:']) {
      const content = legacyEdit('docs/notes.md', oldString, 'new');
      expect(parseFileEditContent(content)).toBeNull();
      expect(isRenderableToolDiff(content)).toBe(false);
    }
  });

  it('rejects incomplete, malformed, non-edit, and unfenced non-Markdown content', () => {
    for (const content of [
      'In the file `docs/notes.md``, replace the string:\nold',
      'In the file `docs/notes.md``, replace the string:\n```markdown\nold\n```\nwith:\n```markdown\nnew',
      fencedEdit('docs/notes.md', 'old', 'new', '````').slice(0, -1),
      legacyEdit('src/example.py', 'old', 'new'),
      'Read the file `docs/notes.md`.',
      'In the file `docs/notes.md``, insert the following text after line 1:\nnew',
    ]) {
      expect(parseFileEditContent(content)).toBeNull();
      expect(isRenderableToolDiff(content)).toBe(false);
    }
  });

  it('does not turn unchanged text into a diff', () => {
    expect(isRenderableToolDiff(legacyEdit('docs/notes.md', 'same', 'same'))).toBe(false);
    expect(isRenderableToolDiff(fencedEdit('docs/notes.md', 'same', 'same'))).toBe(false);
  });
});
