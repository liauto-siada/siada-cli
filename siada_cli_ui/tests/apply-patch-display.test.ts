import { describe, expect, it } from 'vitest';
import { parseApplyPatchContent } from '../src/utils/diff.js';
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
