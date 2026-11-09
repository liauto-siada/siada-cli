/**
 * Markdown Utilities
 * Provides markdown-aware text processing for safe content splitting
 */

export interface MarkdownCodeFence {
  marker: string;
  language: string | null;
}

/** Advance fence state using the same rules as the terminal renderer. */
export function advanceMarkdownFence(
  line: string,
  fence: MarkdownCodeFence | undefined,
): MarkdownCodeFence | undefined {
  const match = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
  if (!match) return fence;
  if (fence) {
    return match[1][0] === fence.marker[0] &&
      match[1].length >= fence.marker.length && match[2].trim() === ''
      ? undefined : fence;
  }
  // Backticks are not allowed in the info string of a backtick fence.
  if (match[1][0] === '`' && match[2].includes('`')) return undefined;
  return { marker: match[1], language: match[2].trim().split(/\s+/, 1)[0] || null };
}

/**
 * Split presentation content near 3000 characters without cutting fenced code.
 * Oversized and unfinished code blocks remain whole; prose stays bounded.
 */
export function splitMarkdownFragments(content: string): string[] {
  const codeBlocks: { start: number; end: number }[] = [];
  let fence: MarkdownCodeFence | undefined;
  let blockStart = 0;
  let position = 0;
  // Scan source lines once so long histories do not repeatedly scan prefixes.
  for (const line of content.split('\n')) {
    const nextFence = advanceMarkdownFence(line.replace(/\r$/, ''), fence);
    if (!fence && nextFence) blockStart = position;
    if (fence && !nextFence) {
      codeBlocks.push({ start: blockStart, end: Math.min(position + line.length + 1, content.length) });
    }
    fence = nextFence;
    position += line.length + 1;
  }
  if (fence) codeBlocks.push({ start: blockStart, end: content.length });

  const fragments: string[] = [];
  let offset = 0;
  let blockIndex = 0;
  while (offset < content.length) {
    let end = Math.min(offset + 3000, content.length);
    if (end < content.length) {
      const newline = content.lastIndexOf('\n', end);
      if (newline > offset + 1500) end = newline + 1;
      // Never split a UTF-16 surrogate pair.
      if (/[\uD800-\uDBFF]/.test(content[end - 1])) end--;
    }
    while (blockIndex < codeBlocks.length && codeBlocks[blockIndex].end <= end) blockIndex++;
    const block = codeBlocks[blockIndex];
    if (block && block.start < end) {
      // Finish prose before the opener, or include the entire oversized block.
      end = block.start > offset ? block.start : block.end;
    }
    fragments.push(content.slice(offset, end));
    offset = end;
  }
  return fragments;
}

/**
 * Find the start position of a code block that encloses the given index
 * Returns -1 if the index is not inside a code block
 * 
 * @param content - The markdown content to search
 * @param index - The index to check
 * @returns The position of the opening ``` or -1 if not in a code block
 */
export function findEnclosingCodeBlockStart(content: string, index: number): number {
  let codeBlockStart = -1;
  let fence: MarkdownCodeFence | undefined;
  let pos = 0;

  // Scan through content looking for code block markers
  const lines = content.substring(0, index).split('\n');
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const nextFence = advanceMarkdownFence(line.replace(/\r$/, ''), fence);
    if (!fence && nextFence) codeBlockStart = pos;
    if (fence && !nextFence) codeBlockStart = -1;
    fence = nextFence;
    
    pos += line.length + 1; // +1 for newline
  }

  // If we're still in a code block at the index position, return its start
  return fence ? codeBlockStart : -1;
}

/**
 * Check if a given index position is inside a code block
 * 
 * @param content - The markdown content
 * @param index - The index to check
 * @returns true if the index is inside a code block
 */
export function isIndexInsideCodeBlock(content: string, index: number): boolean {
  return findEnclosingCodeBlockStart(content, index) !== -1;
}

/**
 * Find the last safe point to split markdown content
 * Prioritizes:
 * 1. Not splitting inside code blocks
 * 2. Splitting at paragraph boundaries (\n\n)
 * 3. Keeping content whole if no safe point is found
 * 
 * @param content - The markdown content to split
 * @returns The index of the last safe split point, or content.length if no split is safe
 */
export function findLastSafeSplitPoint(content: string): number {
  if (!content || content.length === 0) {
    return 0;
  }

  // 1. Check if the end of content is inside a code block
  const enclosingBlockStart = findEnclosingCodeBlockStart(content, content.length);
  if (enclosingBlockStart !== -1) {
    // We're inside a code block - split before it starts
    return enclosingBlockStart;
  }

  // 2. Look for the last paragraph boundary (double newline)
  let searchStartIndex = content.length;
  
  while (searchStartIndex >= 0) {
    const doubleNewlineIndex = content.lastIndexOf('\n\n', searchStartIndex);
    
    if (doubleNewlineIndex === -1) {
      // No more paragraph boundaries found
      break;
    }

    const potentialSplitPoint = doubleNewlineIndex + 2; // After the \n\n
    
    // Make sure this split point is not inside a code block
    if (!isIndexInsideCodeBlock(content, potentialSplitPoint)) {
      return potentialSplitPoint;
    }
    
    // This split point was inside a code block, try earlier
    searchStartIndex = doubleNewlineIndex - 1;
  }

  // 3. No safe split point found - keep content whole
  return content.length;
}

/**
 * Split content into completed and pending parts at a safe point
 * 
 * @param content - The content to split
 * @returns Object with completed and pending parts
 */
export function splitContentSafely(content: string): { completed: string; pending: string } {
  const splitPoint = findLastSafeSplitPoint(content);
  
  if (splitPoint === content.length) {
    // No safe split point - keep everything as pending
    return {
      completed: '',
      pending: content,
    };
  }

  return {
    completed: content.substring(0, splitPoint),
    pending: content.substring(splitPoint),
  };
}

/**
 * Count the number of lines in a string
 * 
 * @param content - The content to count lines in
 * @returns Number of lines
 */
export function countLines(content: string): number {
  if (!content) return 0;
  return content.split('\n').length;
}

/**
 * Check if content should be split based on line count threshold
 * 
 * @param content - The content to check
 * @param threshold - Maximum lines before splitting
 * @returns true if content exceeds threshold and should be split
 */
export function shouldSplitContent(content: string, threshold: number): boolean {
  return countLines(content) > threshold;
}
