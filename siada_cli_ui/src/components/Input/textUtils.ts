/**
 * Text utility functions for Unicode handling and text manipulation
 */

/**
 * Convert a string to an array of code points (proper Unicode handling)
 */
export function toCodePoints(str: string): string[] {
  return Array.from(str);
}

/**
 * Get the length of a string in code points
 */
export function cpLen(str: string): number {
  return toCodePoints(str).length;
}

/**
 * Slice a string by code point indices
 */
export function cpSlice(str: string, start: number, end?: number): string {
  const codePoints = toCodePoints(str);
  return codePoints.slice(start, end).join('');
}

/**
 * Check if a character is a word character (strict - no combining marks)
 */
export function isWordCharStrict(char: string): boolean {
  return /[\w\p{L}\p{N}]/u.test(char);
}

/**
 * Alias for backward compatibility
 */
export function isWordChar(char: string): boolean {
  return isWordCharStrict(char);
}

/**
 * Check if a character is whitespace
 */
export function isWhitespace(char: string): boolean {
  return /\s/.test(char);
}

/**
 * Check if a character is a combining mark (diacritics, etc.)
 */
export function isCombiningMark(char: string): boolean {
  return /\p{M}/u.test(char);
}

/**
 * Check if a character should be considered part of a word (including combining marks)
 */
export function isWordCharWithCombining(char: string): boolean {
  return isWordCharStrict(char) || isCombiningMark(char);
}

/**
 * Get the script of a character (for proper word boundary detection)
 * Supports international text
 */
export function getCharScript(char: string): string {
  if (/[\p{Script=Latin}]/u.test(char)) return 'latin';
  if (/[\p{Script=Han}]/u.test(char)) return 'han'; // Chinese
  if (/[\p{Script=Arabic}]/u.test(char)) return 'arabic';
  if (/[\p{Script=Hiragana}]/u.test(char)) return 'hiragana';
  if (/[\p{Script=Katakana}]/u.test(char)) return 'katakana';
  if (/[\p{Script=Cyrillic}]/u.test(char)) return 'cyrillic';
  return 'other';
}

/**
 * Check if two characters are from different scripts (indicating word boundary)
 * Essential for CJK text handling
 */
export function isDifferentScript(char1: string, char2: string): boolean {
  if (!isWordCharStrict(char1) || !isWordCharStrict(char2)) return false;
  return getCharScript(char1) !== getCharScript(char2);
}

/**
 * Find next word start within a line, starting from col
 * Script boundary detection for word navigation
 */
export function findNextWordStartInLine(line: string, col: number): number | null {
  const chars = toCodePoints(line);
  let i = col;

  if (i >= chars.length) return null;

  const currentChar = chars[i];

  // Skip current word/sequence based on character type
  if (isWordCharStrict(currentChar)) {
    while (i < chars.length && isWordCharWithCombining(chars[i])) {
      // Check for script boundary - if next character is from different script, stop here
      if (
        i + 1 < chars.length &&
        isWordCharStrict(chars[i + 1]) &&
        isDifferentScript(chars[i], chars[i + 1])
      ) {
        i++; // Include current character
        break; // Stop at script boundary
      }
      i++;
    }
  } else if (!isWhitespace(currentChar)) {
    while (
      i < chars.length &&
      !isWordCharStrict(chars[i]) &&
      !isWhitespace(chars[i])
    ) {
      i++;
    }
  }

  // Skip whitespace
  while (i < chars.length && isWhitespace(chars[i])) {
    i++;
  }

  return i < chars.length ? i : null;
}

/**
 * Find previous word start within a line
 * Script boundary detection for word navigation
 */
export function findPrevWordStartInLine(line: string, col: number): number | null {
  const chars = toCodePoints(line);
  let i = col;

  if (i <= 0) return null;

  i--;

  // Skip whitespace moving backwards
  while (i >= 0 && isWhitespace(chars[i])) {
    i--;
  }

  if (i < 0) return null;

  if (isWordCharStrict(chars[i])) {
    // We're in a word, move to its beginning
    while (i >= 0 && isWordCharStrict(chars[i])) {
      // Check for script boundary - if previous character is from different script, stop here
      if (
        i - 1 >= 0 &&
        isWordCharStrict(chars[i - 1]) &&
        isDifferentScript(chars[i], chars[i - 1])
      ) {
        return i; // Return current position at script boundary
      }
      i--;
    }
    return i + 1;
  } else {
    // We're in punctuation, move to its beginning
    while (i >= 0 && !isWordCharStrict(chars[i]) && !isWhitespace(chars[i])) {
      i--;
    }
    return i + 1;
  }
}

/**
 * Find word end within a line
 */
export function findWordEndInLine(line: string, col: number): number | null {
  const chars = toCodePoints(line);
  let i = col;

  // If we're already at the end of a word, advance to next word
  const atEndOfWordChar =
    i < chars.length &&
    isWordCharWithCombining(chars[i]) &&
    (i + 1 >= chars.length ||
      !isWordCharWithCombining(chars[i + 1]) ||
      (isWordCharStrict(chars[i]) &&
        i + 1 < chars.length &&
        isWordCharStrict(chars[i + 1]) &&
        isDifferentScript(chars[i], chars[i + 1])));

  const atEndOfPunctuation =
    i < chars.length &&
    !isWordCharWithCombining(chars[i]) &&
    !isWhitespace(chars[i]) &&
    (i + 1 >= chars.length ||
      isWhitespace(chars[i + 1]) ||
      isWordCharWithCombining(chars[i + 1]));

  if (atEndOfWordChar || atEndOfPunctuation) {
    i++;
    while (i < chars.length && isWhitespace(chars[i])) {
      i++;
    }
  }

  // If we're not on a word character, find the next word
  if (i < chars.length && !isWordCharWithCombining(chars[i])) {
    while (i < chars.length && isWhitespace(chars[i])) {
      i++;
    }
  }

  // Move to end of current word
  let foundWord = false;
  let lastBaseCharPos = -1;

  if (i < chars.length && isWordCharWithCombining(chars[i])) {
    while (i < chars.length && isWordCharWithCombining(chars[i])) {
      foundWord = true;

      if (isWordCharStrict(chars[i])) {
        lastBaseCharPos = i;
      }

      // Check for script boundary
      if (
        i + 1 < chars.length &&
        isWordCharStrict(chars[i + 1]) &&
        isDifferentScript(chars[i], chars[i + 1])
      ) {
        i++;
        if (isWordCharStrict(chars[i - 1])) {
          lastBaseCharPos = i - 1;
        }
        break;
      }

      i++;
    }
  } else if (i < chars.length && !isWhitespace(chars[i])) {
    while (
      i < chars.length &&
      !isWordCharStrict(chars[i]) &&
      !isWhitespace(chars[i])
    ) {
      foundWord = true;
      lastBaseCharPos = i;
      i++;
    }
  }

  if (foundWord && lastBaseCharPos >= col) {
    return lastBaseCharPos;
  }

  return null;
}

/**
 * Find next word across lines (for multi-line text)
 */
export function findNextWordAcrossLines(
  lines: string[],
  cursorRow: number,
  cursorCol: number,
  searchForWordStart: boolean = true,
): { row: number; col: number } | null {
  // First try current line
  const currentLine = lines[cursorRow] || '';
  const colInCurrentLine = searchForWordStart
    ? findNextWordStartInLine(currentLine, cursorCol)
    : findWordEndInLine(currentLine, cursorCol);

  if (colInCurrentLine !== null) {
    return { row: cursorRow, col: colInCurrentLine };
  }

  // Search subsequent lines
  for (let row = cursorRow + 1; row < lines.length; row++) {
    const line = lines[row] || '';
    const chars = toCodePoints(line);

    if (chars.length === 0) continue;

    // Find first non-whitespace
    let firstNonWhitespace = 0;
    while (
      firstNonWhitespace < chars.length &&
      isWhitespace(chars[firstNonWhitespace])
    ) {
      firstNonWhitespace++;
    }

    if (firstNonWhitespace < chars.length) {
      if (searchForWordStart) {
        return { row, col: firstNonWhitespace };
      } else {
        const endCol = findWordEndInLine(line, firstNonWhitespace);
        if (endCol !== null) {
          return { row, col: endCol };
        }
      }
    }
  }

  return null;
}

/**
 * Find previous word across lines (for multi-line text)
 */
export function findPrevWordAcrossLines(
  lines: string[],
  cursorRow: number,
  cursorCol: number,
): { row: number; col: number } | null {
  // First try current line
  const currentLine = lines[cursorRow] || '';
  const colInCurrentLine = findPrevWordStartInLine(currentLine, cursorCol);

  if (colInCurrentLine !== null) {
    return { row: cursorRow, col: colInCurrentLine };
  }

  // Search previous lines
  for (let row = cursorRow - 1; row >= 0; row--) {
    const line = lines[row] || '';
    const chars = toCodePoints(line);

    if (chars.length === 0) continue;

    // Find last word start
    let lastWordStart = chars.length;
    while (lastWordStart > 0 && isWhitespace(chars[lastWordStart - 1])) {
      lastWordStart--;
    }

    if (lastWordStart > 0) {
      const wordStart = findPrevWordStartInLine(line, lastWordStart);
      if (wordStart !== null) {
        return { row, col: wordStart };
      }
    }
  }

  return null;
}

/**
 * Legacy function for backward compatibility
 * Use findNextWordStartInLine for line-based operations
 */
export function findNextWordStart(text: string, pos: number): number {
  const line = text;
  const result = findNextWordStartInLine(line, pos);
  return result !== null ? result : text.length;
}

/**
 * Legacy function for backward compatibility
 * Use findPrevWordStartInLine for line-based operations
 */
export function findPrevWordStart(text: string, pos: number): number {
  const line = text;
  const result = findPrevWordStartInLine(line, pos);
  return result !== null ? result : 0;
}

/**
 * Strip unsafe characters from text
 */
export function stripUnsafeCharacters(text: string): string {
  // Remove control characters except newline and tab
  return text.replace(/[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]/g, '');
}

/**
 * Calculate visual width of a character (considering wide characters)
 * Enhanced implementation for accurate width calculation
 */
export function getCharWidth(char: string): number {
  const code = char.codePointAt(0);
  if (!code) return 0;

  // Control characters have zero width
  if (code < 0x20 || (code >= 0x7f && code < 0xa0)) {
    return 0;
  }

  // Combining marks have zero width
  if (isCombiningMark(char)) {
    return 0;
  }

  // CJK characters and full-width forms are 2 cells wide
  if (
    (code >= 0x1100 && code <= 0x115f) || // Hangul Jamo
    (code >= 0x2e80 && code <= 0x9fff) || // CJK
    (code >= 0xac00 && code <= 0xd7a3) || // Hangul Syllables
    (code >= 0xf900 && code <= 0xfaff) || // CJK Compatibility
    (code >= 0xff00 && code <= 0xff60) || // Full-width forms
    (code >= 0xffe0 && code <= 0xffe6) || // Full-width symbols
    (code >= 0x20000 && code <= 0x2fffd) || // CJK Extension B-E
    (code >= 0x30000 && code <= 0x3fffd) // CJK Extension F-G
  ) {
    return 2;
  }

  // Emojis are typically 2 cells wide
  if (
    (code >= 0x1f000 && code <= 0x1f9ff) || // Emoticons, Pictographs
    (code >= 0x1fa00 && code <= 0x1faff) // Symbols and Pictographs Extended-A
  ) {
    return 2;
  }

  return 1;
}

/**
 * Calculate the visual width of a string
 * Uses cached calculation for performance
 */
const widthCache = new Map<string, number>();

export function getStringWidth(str: string): number {
  // Check cache first
  if (widthCache.has(str)) {
    return widthCache.get(str)!;
  }

  let width = 0;
  for (const char of toCodePoints(str)) {
    width += getCharWidth(char);
  }

  // Cache the result
  widthCache.set(str, width);
  
  // Limit cache size
  if (widthCache.size > 1000) {
    const firstKey = widthCache.keys().next().value;
    widthCache.delete(firstKey);
  }

  return width;
}

/**
 * Clear the width cache (useful for testing or memory management)
 */
export function clearWidthCache(): void {
  widthCache.clear();
}

/**
 * Cached version of string width calculation using string-width library
 * Accurate visual width calculation including CJK and emoji
 * This is the primary function used by calculateLayout
 */
import stringWidth from 'string-width';

// Simple LRU cache implementation
class SimpleLRUCache<K, V> {
  private cache = new Map<K, V>();
  private maxSize: number;

  constructor(maxSize: number) {
    this.maxSize = maxSize;
  }

  get(key: K): V | undefined {
    const value = this.cache.get(key);
    if (value !== undefined) {
      // Move to end (most recently used)
      this.cache.delete(key);
      this.cache.set(key, value);
    }
    return value;
  }

  set(key: K, value: V): void {
    // Remove if exists to re-add at end
    if (this.cache.has(key)) {
      this.cache.delete(key);
    }
    this.cache.set(key, value);
    
    // Remove oldest if over limit
    if (this.cache.size > this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
  }

  clear(): void {
    this.cache.clear();
  }
}

const LRU_BUFFER_PERF_CACHE_LIMIT = 20000;
const stringWidthCache = new SimpleLRUCache<string, number>(LRU_BUFFER_PERF_CACHE_LIMIT);

/**
 * Cached version of stringWidth function for better performance
 * Used in calculateLayout
 */
export const getCachedStringWidth = (str: string): number => {
  // ASCII printable chars (32-126) have width 1.
  // This is a very frequent path, so we use a fast numeric check.
  if (str.length === 1) {
    const code = str.charCodeAt(0);
    if (code >= 0x20 && code <= 0x7e) {
      return 1;
    }
  }

  const cached = stringWidthCache.get(str);
  if (cached !== undefined) {
    return cached;
  }

  let width: number;
  try {
    width = stringWidth(str);
  } catch {
    // Fallback for characters that cause string-width to crash
    width = toCodePoints(str).length;
  }

  stringWidthCache.set(str, width);

  return width;
};

/**
 * Clear the string width cache
 */
export const clearStringWidthCache = (): void => {
  stringWidthCache.clear();
};
