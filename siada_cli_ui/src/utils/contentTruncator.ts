/**
 * Content Truncation Utilities
 * 
 * Key Strategy: Truncate by LINES, not by BYTES
 * - Terminal.app crashes from rendering too many lines
 * - 15KB could be 150 lines or 1500 lines (inconsistent)
 * - Line-based truncation is more predictable
 */

export interface TruncationResult {
  content: string;
  hiddenLines: number;
  truncated: boolean;
}

/**
 * Truncate content by number of lines
 * 
 * @param content - Original content
 * @param maxLines - Maximum lines to keep
 * @param keepPosition - 'end' (default) keeps last N lines, 'start' keeps first N lines, 'both' keeps first 4 + last lines
 * @returns Truncated content and metadata
 * 
 * @example
 * ```ts
 * const { content, hiddenLines } = truncateByLines(longText, 100);
 * // Keeps last 100 lines, returns hiddenLines count
 * 
 * const { content, hiddenLines } = truncateByLines(longText, 100, 'both');
 * // Keeps firsct 4 lines + last (100-4) lines, returns hiddenLines count
 * ```
 */
export function truncateByLines(
  content: string,
  maxLines: number,
  keepPosition: 'start' | 'end' | 'both' = 'end'
): TruncationResult {
  if (!content || maxLines <= 0) {
    return {
      content: '',
      hiddenLines: 0,
      truncated: false,
    };
  }

  const lines = content.split(/\r?\n/);
  
  if (lines.length <= maxLines) {
    return {
      content,
      hiddenLines: 0,
      truncated: false,
    };
  }

  const hiddenLines = lines.length - maxLines;
  let visibleLines: string[];
  const truncationMarker = `... [${hiddenLines} lines hidden] ...`;
  
  if (keepPosition === 'both') {
    // Keep first 4 lines + last (maxLines - 4) lines
    const firstLines = 4;
    const lastLines = Math.max(maxLines - firstLines, 0);
    const firstPart = lines.slice(0, firstLines);
    const lastPart = lastLines > 0 ? lines.slice(-lastLines) : [];
    // Insert marker in the middle
    visibleLines = [...firstPart, truncationMarker, ...lastPart];
  } else if (keepPosition === 'end') {
    // Keep last N lines, insert marker at the beginning
    visibleLines = [truncationMarker, ...lines.slice(-maxLines)];
  } else {
    // Keep first N lines, insert marker at the end
    visibleLines = [...lines.slice(0, maxLines), truncationMarker];
  }

  return {
    content: visibleLines.join('\n'),
    hiddenLines,
    truncated: true,
  };
}

/**
 * Truncate code blocks specifically
 * 
 * Code blocks are expensive to render due to syntax highlighting.
 * This function truncates code while preserving the fence.
 * 
 * @param content - Code block content (may include fence)
 * @param maxLines - Maximum lines
 * @returns Truncated code
 */
export function truncateCodeBlock(
  content: string,
  maxLines: number
): TruncationResult {
  // Detect code fence
  const fenceMatch = content.match(/^```(\w*)\n/);
  const hasFence = !!fenceMatch;
  const language = fenceMatch ? fenceMatch[1] : '';

  let codeContent = content;
  let prefix = '';
  let suffix = '';

  if (hasFence) {
    // Extract fence
    const lines = content.split('\n');
    prefix = lines[0] + '\n';  // ```language
    suffix = lines[lines.length - 1] === '```' ? '\n```' : '';
    codeContent = lines.slice(1, lines[lines.length - 1] === '```' ? -1 : undefined).join('\n');
  }

  // Truncate the code itself
  const result = truncateByLines(codeContent, maxLines - (hasFence ? 2 : 0));

  if (result.truncated && hasFence) {
    return {
      content: `${prefix}${result.content}${suffix}`,
      hiddenLines: result.hiddenLines,
      truncated: true,
    };
  }

  return result;
}

/**
 * Smart truncation that adapts to content type
 * 
 * @param content - Content to truncate
 * @param maxLines - Maximum lines
 * @param contentType - Type hint for optimization
 * @returns Truncated content
 */
export function smartTruncate(
  content: string,
  maxLines: number,
  contentType?: 'code' | 'markdown' | 'plain'
): TruncationResult {
  // Auto-detect content type if not provided
  if (!contentType) {
    if (content.startsWith('```')) {
      contentType = 'code';
    } else if (content.includes('#') || content.includes('**')) {
      contentType = 'markdown';
    } else {
      contentType = 'plain';
    }
  }

  // Use specialized truncation for code blocks
  if (contentType === 'code' && content.startsWith('```')) {
    return truncateCodeBlock(content, maxLines);
  }

  // Default line-based truncation
  return truncateByLines(content, maxLines);
}

/**
 * Truncate JSON content with pretty formatting
 * 
 * This function:
 * 1. Parses JSON and pretty-prints it
 * 2. Truncates long field values (>120 chars)
 * 3. Applies line-based truncation
 * 
 * @param content - JSON string to truncate
 * @param maxLines - Maximum lines to keep
 * @param keepPosition - Where to keep lines ('start', 'end', 'both')
 * @param maxFieldLength - Maximum length for field values (default 120)
 * @returns Truncated content with metadata
 * 
 * @example
 * ```ts
 * const result = truncateByJSONLines('{"key": "very long value..."}', 20);
 * // Returns pretty-printed JSON with truncated fields and lines
 * ```
 */
export function truncateByJSONLines(
  content: string,
  maxLines: number,
  keepPosition: 'start' | 'end' | 'both' = 'end',
  maxFieldLength: number = 120
): TruncationResult {
  if (!content || maxLines <= 0) {
    return {
      content: '',
      hiddenLines: 0,
      truncated: false,
    };
  }

  try {
    // Step 1: Parse JSON
    const parsed = JSON.parse(content);
    
    // Step 2: Truncate long field values
    const truncateObject = (obj: any): any => {
      if (typeof obj === 'string') {
        if (obj.length > maxFieldLength) {
          return obj.substring(0, maxFieldLength) + '...';
        }
        return obj;
      }
      
      if (Array.isArray(obj)) {
        return obj.map(item => truncateObject(item));
      }
      
      if (obj !== null && typeof obj === 'object') {
        const result: any = {};
        for (const [key, value] of Object.entries(obj)) {
          result[key] = truncateObject(value);
        }
        return result;
      }
      
      return obj;
    };
    
    const truncatedObj = truncateObject(parsed);
    
    // Step 3: Pretty print with 2-space indentation
    const prettyJSON = JSON.stringify(truncatedObj, null, 2);
    
    // Step 4: Apply line-based truncation
    return truncateByLines(prettyJSON, maxLines, keepPosition);
    
  } catch (error) {
    // If not valid JSON, fall back to regular truncation
    return truncateByLines(content, maxLines, keepPosition);
  }
}

/**
 * Calculate approximate line count for content
 * 
 * Useful for pre-checking before rendering.
 * 
 * @param content - Content to measure
 * @param maxWidth - Terminal width (default 80)
 * @returns Estimated line count
 */
export function estimateLineCount(
  content: string,
  maxWidth: number = 80
): number {
  const lines = content.split(/\r?\n/);
  let totalLines = 0;

  for (const line of lines) {
    if (line.length === 0) {
      totalLines += 1;
    } else {
      // Estimate wrapped lines
      const wrappedLines = Math.ceil(line.length / maxWidth);
      totalLines += wrappedLines;
    }
  }

  return totalLines;
}
