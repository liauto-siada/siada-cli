/**
 * Content Cleaner
 * Shared cleaning for process-style message content (thinking / tool_use /
 * answer blocks sent by the backend with box-drawing and ANSI decorations).
 * Extracted from MessageList so exports can reuse the exact on-screen rules.
 */

export function extractCleanContent(content: string): string {
  // Remove ANSI escape sequences (colors, formatting, etc.)
  // This regex matches ANSI escape codes like \x1b[39m, \x1b[1m, etc.
  let cleaned = content.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');

  // Also remove alternative ANSI format [39m, [1m, etc.
  cleaned = cleaned.replace(/\[[0-9;]*m/g, '');

  // Remove box-drawing characters (╭, ╮, ╰, ╯, │, ─)
  cleaned = cleaned.replace(/[╭╮╰╯│─]/g, '');

  // Remove arrow and **TYPE** headers
  cleaned = cleaned.replace(/[▶►]\s*\*\*[A-Z\s]+\*\*/g, '');

  // Remove token counter lines - split into lines first to handle each line
  const lines = cleaned.split('\n');
  const filteredLines = lines.filter(line => {
    // Remove lines that are ONLY whitespace and token counts
    // Pattern: any amount of whitespace + "X,XXX / XXX,XXX tokens"
    const tokenPattern = /^\s*[\d,]+\s*\/\s*[\d,]+\s+tokens?\s*$/i;
    if (tokenPattern.test(line)) {
      return false; // Remove this line
    }

    // Remove lines that are only separators
    const separatorPattern = /^[\s─\-]+$/;
    if (separatorPattern.test(line)) {
      return false;
    }

    // Keep all lines including empty ones to preserve newline structure
    return true;
  });

  // Join lines back together
  let result = filteredLines.join('\n');

  // Collapse 3+ consecutive newlines into 2 (one blank line) throughout the content
  // This handles cases where removing markers (like ▶ **ANSWER**) leaves extra blank lines
  result = result.replace(/\n{3,}/g, '\n\n');

  // Strip leading newlines
  result = result.replace(/^\n+/, '');

  // Strip trailing newlines (keep at most 1)
  result = result.replace(/\n{2,}$/, '\n');

  return result;
}
