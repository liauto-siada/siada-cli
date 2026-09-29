import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { Message as MessageType } from '../src/types/index.js';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    Text: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    Static: ({ items, children }: { items: unknown[]; children: (item: unknown, index: number) => React.ReactNode }) => (
      <section data-area="static">{items.map((item, index) => children(item, index))}</section>
    ),
    useStdout: () => ({ stdout: { rows: 24, columns: 80 } }),
  };
});

vi.mock('../src/themes/index.js', async (importOriginal) => ({
  ...await importOriginal<typeof import('../src/themes/index.js')>(),
  useThemeVersion: () => 0,
}));

import { MessageList } from '../src/components/Chat/MessageList.js';

const patch = `Apply patch: 1 file changed

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
const edit = 'In the file `src/a.ts``, replace the string:\n```ts\nold\n```\nwith:\n```ts\nnew\n```';
const historyPreview = patch.replace(
  '<!-- siada-apply-patch:start -->',
  '<!-- siada-apply-patch:history-preview -->\n<!-- siada-apply-patch:start -->',
);

function toolMessage(content: string): MessageType {
  return {
    id: 'patch',
    type: 'agent',
    content,
    timestamp: '2026-01-01T00:00:00.000Z',
    author: 'Siada',
    metadata: { subtype: 'tool_use', streamEnd: true },
  };
}

function render(content: string, isCollapsed = true): string {
  return renderToStaticMarkup(<MessageList messages={[toolMessage(content)]} isCollapsed={isCollapsed} />);
}

describe('file edit tool diffs', () => {
  it('keeps resumed patches in Static without an extra history-preview notice', () => {
    const output = render(historyPreview);

    expect(output).toContain('data-area="static"');
    expect(output).toContain('● Update src/a.ts (+1 -1)');
    expect(output).not.toContain('Submitted patch');
    expect(output).not.toContain('history preview');
    expect(output).toContain('old');
    expect(output).toContain('new');
    expect(output).not.toContain('ctrl+o to expand');
  });

  it('shows the same uncollapsed diff for completed apply_patch and edit_file', () => {
    const patchOutput = render(patch);
    const editOutput = render(edit);
    for (const output of [patchOutput, editOutput]) {
      expect(output).toContain('data-area="static"');
      expect(output).toContain('● Update src/a.ts (+1 -1)');
      expect(output).toContain('old');
      expect(output).toContain('new');
      expect(output).not.toContain('ctrl+o to expand');
    }
    expect(patchOutput).not.toContain('Apply patch:');
    expect(patchOutput).not.toContain('Patch(1 files)');
    expect(render('Read the file `src/a.ts`')).toContain('Read 1 file');
  });

  it('lists each edited file with its line totals and diff beneath a multi-file summary', () => {
    const multiPatch = patch.replace('1 file changed', '2 files changed').replace(
      '<!-- siada-apply-patch:end -->',
      '### Update `src/b.ts`\n```diff\n--- a/src/b.ts\n+++ b/src/b.ts\n@@ -2 +2 @@\n-before\n+after\n```\n<!-- siada-apply-patch:end -->',
    );
    const output = render(multiPatch);
    expect(output).toContain('● Edited 2 files (+2 -2)');
    expect(output).toContain('├─ Update src/a.ts (+1 -1)');
    expect(output).toContain('└─ Update src/b.ts (+1 -1)');
    expect(output).toContain('before');
    expect(output).toContain('after');
    expect(output).not.toContain('ctrl+o to expand');
  });

  it('shows resumed multi-file patches with the normal edit summary and no preview label', () => {
    const multiPatch = historyPreview.replace('1 file changed', '2 files changed').replace(
      '<!-- siada-apply-patch:end -->',
      '### Update `src/b.ts`\n```diff\n--- a/src/b.ts\n+++ b/src/b.ts\n@@ -2 +2 @@\n-before\n+after\n```\n<!-- siada-apply-patch:end -->',
    );
    const output = render(multiPatch);
    expect(output).toContain('● Edited 2 files (+2 -2)');
    expect(output).toContain('├─ Update src/a.ts (+1 -1)');
    expect(output).toContain('└─ Update src/b.ts (+1 -1)');
    expect(output).not.toContain('Submitted patch');
  });

  it('preserves create and delete labels with accurate addition and deletion counts', () => {
    const multiPatch = patch.replace('1 file changed', '3 files changed').replace(
      '<!-- siada-apply-patch:end -->',
      '### Create `src/b.ts`\n```diff\n--- /dev/null\n+++ b/src/b.ts\n@@ -0,0 +1 @@\n+created\n```\n### Delete `src/c.ts`\n```diff\n--- a/src/c.ts\n+++ /dev/null\n@@ -1 +0,0 @@\n-deleted\n```\n<!-- siada-apply-patch:end -->',
    );
    const output = render(multiPatch);
    expect(output).toContain('● Edited 3 files (+2 -2)');
    expect(output).toContain('├─ Create src/b.ts (+1 -0)');
    expect(output).toContain('└─ Delete src/c.ts (+0 -1)');
    expect(output).toContain('created');
    expect(output).toContain('deleted');
  });

  it('renders a history-only delete as the action alone, including older saved notices', () => {
    const deletion = `Apply patch: 1 file changed
<!-- siada-apply-patch:history-preview -->
<!-- siada-apply-patch:start -->
### Delete \`progress.md\`
<!-- siada-apply-patch:end -->`;
    for (const content of [deletion, deletion.replace('### Delete `progress.md`',
      '### Delete `progress.md`\nDeletion requested; original file contents are unavailable in history.')]) {
      for (const collapsed of [true, false]) {
        const output = render(content, collapsed);
        expect(output).toContain('● Delete progress.md');
        expect(output).not.toContain('Deletion requested');
        expect(output).not.toContain('No text changes to display');
      }
    }
  });

  it('shows paths only for create/update/delete without diff lines or actionable details', () => {
    const pathOnly = `Apply patch: 3 files changed
<!-- siada-apply-patch:history-preview -->
<!-- siada-apply-patch:start -->
### Create \`new.py\`
Submitted patch details are unavailable in history.
### Update \`changed.py\`
Submitted patch has no displayable line changes.
### Delete \`old.py\`
Deletion requested; original file contents are unavailable in history.
<!-- siada-apply-patch:end -->`;
    const output = render(pathOnly, false);
    expect(output).toContain('● Edited 3 files');
    expect(output).toContain('├─ Create new.py');
    expect(output).toContain('├─ Update changed.py');
    expect(output).toContain('└─ Delete old.py');
    expect(output).not.toContain('unavailable');
    expect(output).not.toContain('Submitted patch');
    expect(output).not.toContain('No text changes to display');
  });

  it('keeps context line numbers under the file heading', () => {
    const numberedPatch = patch.replace('@@ -1 +1 @@\n-old\n+new', '@@ -267,2 +267,3 @@\n context\n-old\n+new\n+extra');
    const output = render(numberedPatch);
    expect(output).toContain('● Update src/a.ts (+2 -1)');
    expect(output).toMatch(/267[\s\S]*context/);
    expect(output).toMatch(/268[\s\S]*old/);
    expect(output).toContain('extra');
  });

  it('shows failed operations without claiming their files were edited', () => {
    const failedPatch = `Apply patch: 1 file changed

<!-- siada-apply-patch:start -->
### Failed Update \`src/a.ts\`
Permission denied.
<!-- siada-apply-patch:end -->`;
    const output = render(failedPatch);
    expect(output).toContain('● Failed src/a.ts');
    expect(output).toContain('Permission denied.');
    expect(output).not.toContain('Edited 1 file');
  });

  it('does not invent line totals for an omitted diff', () => {
    const multiPatch = patch.replace('1 file changed', '2 files changed').replace(
      '<!-- siada-apply-patch:end -->',
      '### Update `src/b.ts`\nDiff omitted to keep the history display responsive.\n<!-- siada-apply-patch:end -->',
    );
    expect(render(multiPatch)).toContain('● Edited 2 files (+1 -1 shown)');
    expect(render(multiPatch)).toContain('Diff omitted to keep the history display responsive.');
  });

  it('does not mark a known text-free move as an omitted diff', () => {
    const multiPatch = patch.replace('1 file changed', '2 files changed').replace(
      '<!-- siada-apply-patch:end -->',
      '### Move `src/b.ts` → `src/c.ts`\nMoved without text changes.\n<!-- siada-apply-patch:end -->',
    );
    const output = render(multiPatch);
    expect(output).toContain('● Edited 2 files (+1 -1)');
    expect(output).toContain('└─ Move src/b.ts → src/c.ts');
    expect(output).not.toContain('shown');
  });

  it('keeps incomplete patches visible as raw text until a diff can be rendered', () => {
    expect(render('Apply patch: 1 file changed')).toContain('Apply patch: 1 file changed');
  });

  it('also renders the diff when compact mode is off', () => {
    expect(render(edit, false)).toContain('● Update src/a.ts (+1 -1)');
    const output = render(historyPreview, false);
    expect(output).toContain('● Update src/a.ts (+1 -1)');
    expect(output).not.toContain('Submitted patch');
  });
});
