import { structuredPatch, type StructuredPatchHunk } from 'diff';

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
