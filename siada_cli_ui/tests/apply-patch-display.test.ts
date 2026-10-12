import { describe, expect, it } from 'vitest';
import { getSimplePatch, isRenderableToolDiff, parseApplyPatchContent, parseFileCreateContent } from '../src/utils/diff.js';
import { parseToolCall } from '../src/utils/toolCallParser.js';

const MULTI_FILE_PATCH = `Apply patch: 4 files changed

<!-- siada-apply-patch:start -->

### Update \`src/service.py\`
\`\`\`diff
--- a/src/service.py
+++ b/src/service.py
@@ -1,2 +1,2 @@
 one
-old
+new
\`\`\`

### Create \`tests/test_service.py\`
\`\`\`diff
--- /dev/null
+++ b/tests/test_service.py
@@ -0,0 +1 @@
+assert True
\`\`\`

### Delete \`src/obsolete.py\`
\`\`\`diff
--- a/src/obsolete.py
+++ /dev/null
@@ -1 +0,0 @@
-obsolete
\`\`\`

### Move \`src/old_name.py\` → \`src/new_name.py\`
Moved without text changes.
<!-- siada-apply-patch:end -->`;

const FAILED_MOVE_PATCH = `Apply patch: 1 file changed

<!-- siada-apply-patch:start -->

### Failed Move \`src/old_name.py\` → \`src/new_name.py\`
Access to \`src/new_name.py\` is denied by .siadaignore.
<!-- siada-apply-patch:end -->`;

describe('native apply_patch display protocol', () => {
  it('parses multi-file create, update, delete, and move operations', () => {
    const parsed = parseApplyPatchContent(MULTI_FILE_PATCH);

    expect(parsed).not.toBeNull();
    expect(parsed?.fileCount).toBe(4);
    expect(parsed?.changes.map(change => change.action)).toEqual([
      'update',
      'create',
      'delete',
      'move',
    ]);
    expect(parsed?.changes[0]?.hunks).toHaveLength(1);
    expect(parsed?.changes[1]?.hunks).toHaveLength(1);
    expect(parsed?.changes[2]?.hunks).toHaveLength(1);
    expect(parsed?.changes[3]).toMatchObject({
      path: 'src/old_name.py',
      moveTo: 'src/new_name.py',
      hunks: [],
    });
  });

  it('returns null when the text protocol is incomplete or malformed', () => {
    expect(parseApplyPatchContent('Apply patch: 1 file changed')).toBeNull();
    expect(parseApplyPatchContent(`Apply patch: 1 file changed
<!-- siada-apply-patch:start -->
### Update \`src/a.py\`
`)).toBeNull();
  });

  it('parses an update to a Markdown file whose last line has no trailing newline', () => {
    const display = `Apply patch: 1 file changed

<!-- siada-apply-patch:start -->

### Update \`progress.md\`
\`\`\`diff
--- a/progress.md
+++ b/progress.md
@@ -10,4 +10,5 @@
 阶段一已完成
 阶段二正在验证
 下一项是测试
-旧的阶段记录
+新的阶段记录
+新增验证结果
\`\`\`
<!-- siada-apply-patch:end -->`;

    expect(parseApplyPatchContent(display)?.changes[0]).toMatchObject({
      action: 'update',
      path: 'progress.md',
      hunks: [{ lines: [
        ' 阶段一已完成', ' 阶段二正在验证', ' 下一项是测试',
        '-旧的阶段记录', '+新的阶段记录', '+新增验证结果',
      ] }],
    });
    expect(parseApplyPatchContent(display.replace('-旧的阶段记录\n+新的阶段记录', '-旧的阶段记录+新的阶段记录'))).toBeNull();
  });

  it('keeps a failed move as a visible file-operation result', () => {
    expect(parseApplyPatchContent(FAILED_MOVE_PATCH)).toMatchObject({
      fileCount: 1,
      changes: [
        {
          action: 'failed',
          path: 'src/old_name.py',
          moveTo: 'src/new_name.py',
          error: 'Access to `src/new_name.py` is denied by .siadaignore.',
        },
      ],
    });
  });

  it('exposes a compact parser summary for collapsed tool-use rows', () => {
    expect(parseToolCall(MULTI_FILE_PATCH)).toMatchObject({
      type: 'apply_patch',
      summary: 'Patch(4 files)',
      fileCount: 4,
    });
  });
});

describe('create-file diff display protocol', () => {
  it('parses fenced file content as a creation diff', () => {
    const content = 'Create the file `src/new.ts`` with the following content:\n```ts\nexport {};\n```';

    expect(parseFileCreateContent(content)).toEqual({
      filePath: 'src/new.ts',
      newString: 'export {};',
      isComplete: true,
    });
    expect(isRenderableToolDiff(content)).toBe(true);
  });

  it('parses unfenced Markdown content and leaves empty files without a diff', () => {
    const markdown = 'Create the file `docs/new.md`` with the following content:\n# New document\n';
    const fencedMarkdown = 'Create the file `docs/example.md`` with the following content:\n```ts\ncode\n```';
    const empty = 'Create the file `src/empty.ts`';

    expect(parseFileCreateContent(markdown)?.newString).toBe('# New document\n');
    expect(parseFileCreateContent(fencedMarkdown)?.newString).toBe('```ts\ncode\n```');
    expect(isRenderableToolDiff(markdown)).toBe(true);
    expect(parseFileCreateContent(empty)).toBeNull();
    expect(isRenderableToolDiff(empty)).toBe(false);
  });

  it('preserves Chinese Markdown and only its real blank lines through the diff', () => {
    const fileText = '第一行\n\n第二行\n\n';
    const content = `Create the file \`docs/notes.md\`\` with the following content:\n${fileText}`;
    const prefixed = `▶ TOOL USE ${content}`;

    expect(parseFileCreateContent(prefixed)?.newString).toBe(fileText);
    expect(isRenderableToolDiff(prefixed)).toBe(true);
    const added = getSimplePatch('docs/notes.md', '', fileText)
      .flatMap(hunk => hunk.lines).filter(line => line.startsWith('+'));
    expect(added).toEqual(['+第一行', '+', '+第二行', '+']);

    const whitespaceOnly = 'Create the file `docs/blank.md`` with the following content:\n\n';
    expect(isRenderableToolDiff(whitespaceOnly)).toBe(true);
    expect(isRenderableToolDiff('Create the file `docs/empty.md`')).toBe(false);
  });

  it('keeps edit, patch, and read detection separate from create diffs', () => {
    const edit = 'In the file `src/a.ts``, replace the string:\n```ts\nold\n```\nwith:\n```ts\nnew\n```';
    expect(isRenderableToolDiff(edit)).toBe(true);
    expect(isRenderableToolDiff(MULTI_FILE_PATCH)).toBe(true);
    expect(isRenderableToolDiff('Read the file `docs/notes.md`.\n')).toBe(false);
    expect(isRenderableToolDiff('View the directory `docs`.\n')).toBe(false);
  });

  it('does not treat an unfinished code fence as a completed create diff', () => {
    const unfinished = 'Create the file `src/new.ts`` with the following content:\n```ts\nnew';

    expect(parseFileCreateContent(unfinished)?.isComplete).toBe(false);
    expect(isRenderableToolDiff(unfinished)).toBe(false);
  });
});
