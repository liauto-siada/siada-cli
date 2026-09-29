import { parsePatch, structuredPatch, type StructuredPatchHunk } from 'diff';

const CONTEXT_LINES = 3;
const AMPERSAND_TOKEN = '<<:AMPERSAND_TOKEN:>>';
const DOLLAR_TOKEN = '<<:DOLLAR_TOKEN:>>';

function escapeForDiff(s: string): string {
  return s.replaceAll('&', AMPERSAND_TOKEN).replaceAll('$', DOLLAR_TOKEN);
}

function unescapeFromDiff(s: string): string {
  return s.replaceAll(AMPERSAND_TOKEN, '&').replaceAll(DOLLAR_TOKEN, '$');
}

export function getSimplePatch(
  filePath: string,
  oldString: string,
  newString: string,
): StructuredPatchHunk[] {
  const result = structuredPatch(
    filePath,
    filePath,
    escapeForDiff(oldString),
    escapeForDiff(newString),
    undefined,
    undefined,
    { context: CONTEXT_LINES },
  );
  if (!result) return [];
  return result.hunks.map(h => ({
    ...h,
    lines: h.lines.map(unescapeFromDiff),
  }));
}

export interface FileEditInfo {
  filePath: string;
  oldString: string;
  newString: string;
  isComplete: boolean;
}

export type ApplyPatchAction = 'create' | 'update' | 'delete' | 'move' | 'failed' | 'unknown';

export interface ApplyPatchFileChange {
  action: ApplyPatchAction;
  path: string;
  moveTo?: string;
  hunks: StructuredPatchHunk[];
  error?: string;
  details?: string;
  diffOmitted?: boolean;
}

export interface ApplyPatchInfo {
  fileCount: number;
  changes: ApplyPatchFileChange[];
  historyPreview: boolean;
}

const APPLY_PATCH_START = '<!-- siada-apply-patch:start -->';
const APPLY_PATCH_END = '<!-- siada-apply-patch:end -->';
const APPLY_PATCH_HISTORY_PREVIEW = '<!-- siada-apply-patch:history-preview -->';
// Earlier releases persisted these implementation details as display text.
// Keep them parseable during resume, but never present them as file content.
const PATCH_DISPLAY_NOTICES = new Set([
  'Deletion requested; original file contents are unavailable in history.',
  'Submitted patch has no displayable line changes.',
  'Submitted patch details are unavailable in history.',
  'Move requested without text changes.',
  'Applied patch details are unavailable in this replay.',
  'Applied without a displayable text diff.',
  'Moved without text changes.',
]);

/**
 * Parse the stable text protocol emitted for native Responses apply_patch.
 *
 * The protocol intentionally remains ordinary text for ACP/log backwards
 * compatibility. Empty sections are valid for file operations with no saved
 * diff. Return null for malformed markers, headings, or diff hunks instead of
 * showing a partially guessed diff.
 */
export function parseApplyPatchContent(content: string): ApplyPatchInfo | null {
  const start = content.indexOf(APPLY_PATCH_START);
  const end = content.indexOf(APPLY_PATCH_END);
  if (start < 0 || end < 0 || end <= start) return null;

  const summary = content.slice(0, start).trim();
  const summaryMatch = summary.match(/^Apply patch: (\d+) files? changed$/m);
  if (!summaryMatch) return null;

  const body = content.slice(start + APPLY_PATCH_START.length, end).trim();
  if (!body) return null;

  const headingPattern = /^### (.+)$/gm;
  const headings = [...body.matchAll(headingPattern)];
  if (headings.length === 0) return null;

  const changes: ApplyPatchFileChange[] = [];
  for (let index = 0; index < headings.length; index++) {
    const heading = headings[index];
    const headingText = heading[1]?.trim() || '';
    const sectionStart = (heading.index ?? 0) + heading[0].length;
    const sectionEnd = index + 1 < headings.length
      ? (headings[index + 1].index ?? body.length)
      : body.length;
    const section = body.slice(sectionStart, sectionEnd).trim();
    const parsedHeading = parseApplyPatchHeading(headingText);
    if (!parsedHeading) return null;

    const diffMatch = section.match(/^```diff\n([\s\S]*?)\n```$/m);
    let hunks: StructuredPatchHunk[] = [];
    if (diffMatch) {
      try {
        hunks = parsePatch(diffMatch[1]).flatMap(patch => patch.hunks || []);
      } catch {
        return null;
      }
    }

    const details = diffMatch || PATCH_DISPLAY_NOTICES.has(section) ? undefined : section || undefined;
    changes.push({
      ...parsedHeading,
      hunks,
      details,
      error: parsedHeading.action === 'failed' ? details : undefined,
      diffOmitted: !!details && /Diff omitted/.test(details),
    });
  }

  return {
    fileCount: Number.parseInt(summaryMatch[1]!, 10),
    changes,
    historyPreview: summary.includes(APPLY_PATCH_HISTORY_PREVIEW),
  };
}

function parseApplyPatchHeading(
  heading: string,
): Pick<ApplyPatchFileChange, 'action' | 'path' | 'moveTo'> | null {
  const moveMatch = heading.match(/^Move `([^`]+)` → `([^`]+)`$/);
  if (moveMatch) {
    return { action: 'move', path: moveMatch[1]!, moveTo: moveMatch[2]! };
  }

  const standardMatch = heading.match(/^(Create|Update|Delete) `([^`]+)`$/);
  if (standardMatch) {
    return {
      action: standardMatch[1]!.toLowerCase() as ApplyPatchAction,
      path: standardMatch[2]!,
    };
  }

  const failedMoveMatch = heading.match(/^Failed Move `([^`]+)` → `([^`]+)`$/);
  if (failedMoveMatch) {
    return { action: 'failed', path: failedMoveMatch[1]!, moveTo: failedMoveMatch[2]! };
  }

  const failedMatch = heading.match(/^Failed (?:Create|Update|Delete|[A-Za-z ]+) `([^`]+)`$/);
  if (failedMatch) {
    return { action: 'failed', path: failedMatch[1]! };
  }

  return null;
}

export function parseFileEditContent(content: string): FileEditInfo | null {
  // Full match: In the file `path``, replace the string:\n```lang\nold\n```\nwith:\n```lang\nnew\n```
  // Note: Python formatter produces double backtick after path (`path``, replace...)
  const fullMatch = content.match(
    /^In the file `([^`]+)`+, replace the string:\n```[^\n]*\n([\s\S]*?)\n```\nwith:\n```[^\n]*\n([\s\S]*?)\n```/,
  );
  if (fullMatch) {
    return {
      filePath: fullMatch[1],
      oldString: fullMatch[2],
      newString: fullMatch[3],
      isComplete: true,
    };
  }
  return null;
}

/** Whether a completed tool-call body renders as a file diff in Message. */
export function isRenderableToolDiff(content: string): boolean {
  const cleanContent = content.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();
  if (parseApplyPatchContent(cleanContent)) return true;

  const edit = parseFileEditContent(cleanContent);
  return edit?.isComplete === true &&
    getSimplePatch(edit.filePath, edit.oldString, edit.newString).length > 0;
}
