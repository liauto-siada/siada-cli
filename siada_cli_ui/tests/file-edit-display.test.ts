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
  it.each(['md', 'markdown', 'mdown', 'mkd', 'MD'])('parses legacy .%s replacements', extension => {
    const filePath = `docs/notes.${extension}`;
    const oldString = '旧的说明\n\n保留的说明';
    const newString = '新的说明\n\n保留的说明';
    const content = legacyEdit(filePath, oldString, newString);
    expect(parseFileEditContent(content)).toEqual({ filePath, oldString, newString, isComplete: true });
    expect(isRenderableToolDiff(content)).toBe(true);
  });

  it.each(['docs/notes.md', 'src/example.py'])('parses fenced replacements for %s', filePath => {
    const content = fencedEdit(filePath, 'old', 'new');
    expect(parseFileEditContent(content)).toEqual({ filePath, oldString: 'old', newString: 'new', isComplete: true });
    expect(isRenderableToolDiff(content)).toBe(true);
    expect(parseFileEditContent(content.replace('``, replace', '`, replace'))?.newString).toBe('new');
  });

  it('preserves embedded fences and separator lines', () => {
    const oldString = '```ts\nold\n```\nwith:\nold description';
    const newString = '```ts\nnew\n```\nwith:\nnew description';
    expect(parseFileEditContent(fencedEdit('docs/notes.md', oldString, newString, '````'))).toEqual({
      filePath: 'docs/notes.md', oldString, newString, isComplete: true,
    });
    expect(parseFileEditContent(legacyEdit('docs/notes.md', '```ts\nold\n```', '```ts\nnew\n```'))?.oldString)
      .toBe('```ts\nold\n```');
  });

  it.each([legacyEdit, fencedEdit])('preserves whitespace and empty text', format => {
    for (const [oldString, newString] of [['\nold\n\n', '\nnew\n\n'], ['old\n\n', ''], ['', 'new\n\n']]) {
      const content = format('docs/notes.md', oldString, newString);
      expect(parseFileEditContent(content)).toEqual({ filePath: 'docs/notes.md', oldString, newString, isComplete: true });
      expect(isRenderableToolDiff(content)).toBe(true);
    }
    const edit = parseFileEditContent(format('docs/notes.md', 'old', 'new\n\n'))!;
    expect(getSimplePatch(edit.filePath, edit.oldString, edit.newString).flatMap(hunk => hunk.lines)).toContain('+');
  });

  it('recognizes historical empty-old-text placeholders', () => {
    expect(parseFileEditContent(legacyEdit('docs/notes.md', '```\n\n```', 'new'))?.oldString).toBe('');
  });

  it.each([legacyEdit, fencedEdit])('accepts tool markers and CRLF', format => {
    const content = `▶ TOOL USE ${format('docs/notes.md', 'old', 'new')}`.replaceAll('\n', '\r\n');
    expect(parseFileEditContent(content)).toEqual({
      filePath: 'docs/notes.md', oldString: 'old', newString: 'new', isComplete: true,
    });
    expect(isRenderableToolDiff(content)).toBe(true);
  });

  it('rejects ambiguous legacy separators and incomplete protocols', () => {
    for (const content of [
      legacyEdit('docs/notes.md', 'old\nwith:\nold description', 'new'),
      legacyEdit('docs/notes.md', 'old\nwith:', 'new'),
      'In the file `docs/notes.md``, replace the string:\nold',
      'In the file `docs/notes.md``, replace the string:\n```markdown\nold\n```\nwith:\n```markdown\nnew',
      fencedEdit('docs/notes.md', 'old', 'new', '````').slice(0, -1),
      legacyEdit('src/example.py', 'old', 'new'),
      'Read the file `docs/notes.md`.',
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