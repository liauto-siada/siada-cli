import { describe, expect, it } from 'vitest';
import { isRenderableToolDiff, parseApplyPatchContent } from '../src/utils/diff.js';

const historyPreview = `Apply patch: 3 files changed

<!-- siada-apply-patch:history-preview -->
<!-- siada-apply-patch:start -->

### Update \`src/a.py\`
\`\`\`diff
--- a/src/a.py
+++ b/src/a.py
@@ -1 +1 @@
-old
+new
\`\`\`

### Create \`new.py\`
\`\`\`diff
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+new
\`\`\`

### Delete \`old.py\`
Deletion requested; original file contents are unavailable in history.
<!-- siada-apply-patch:end -->`;

describe('resumed apply_patch history preview', () => {
  it('renders the saved requested patch as a multi-file diff, with an explicit preview label', () => {
    const result = parseApplyPatchContent(historyPreview);
    expect(result).toMatchObject({
      fileCount: 3,
      historyPreview: true,
      changes: [
        { action: 'update', path: 'src/a.py' },
        { action: 'create', path: 'new.py' },
        { action: 'delete', path: 'old.py' },
      ],
    });
    expect(result?.changes[0]?.hunks[0]?.lines).toContain('-old');
    expect(result?.changes[1]?.hunks[0]?.lines).toContain('+new');
    expect(result?.changes[2]?.hunks).toHaveLength(0);
    expect(result?.changes[2]?.details).toBeUndefined();
    expect(isRenderableToolDiff(historyPreview)).toBe(true);
  });

  it('does not label a live applied-file diff as a requested history preview', () => {
    expect(parseApplyPatchContent(historyPreview.replace('<!-- siada-apply-patch:history-preview -->', ''))?.historyPreview).toBe(false);
  });

  it('accepts path-only create/update/delete sections and hides legacy history notices', () => {
    const pathOnly = `Apply patch: 3 files changed
<!-- siada-apply-patch:history-preview -->
<!-- siada-apply-patch:start -->
### Create \`new.py\`
### Update \`src/a.py\`
### Delete \`old.py\`
<!-- siada-apply-patch:end -->`;
    expect(parseApplyPatchContent(pathOnly)?.changes).toMatchObject([
      { action: 'create', path: 'new.py', hunks: [] },
      { action: 'update', path: 'src/a.py', hunks: [] },
      { action: 'delete', path: 'old.py', hunks: [] },
    ]);
    for (const change of parseApplyPatchContent(pathOnly)?.changes ?? []) {
      expect(change.details).toBeUndefined();
    }
    expect(isRenderableToolDiff(pathOnly)).toBe(true);

    const legacy = pathOnly.replace('### Create `new.py`',
      '### Create `new.py`\nSubmitted patch details are unavailable in history.')
      .replace('### Update `src/a.py`', '### Update `src/a.py`\nSubmitted patch has no displayable line changes.')
      .replace('### Delete `old.py`', '### Delete `old.py`\nDeletion requested; original file contents are unavailable in history.');
    for (const change of parseApplyPatchContent(legacy)?.changes ?? []) {
      expect(change.details).toBeUndefined();
    }
  });
});
