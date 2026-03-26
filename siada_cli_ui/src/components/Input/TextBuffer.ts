/**
 * TextBuffer - Advanced text buffer with multi-line support, viewport management, and history
 */

import { useState, useCallback, useRef, useMemo, useReducer, useEffect } from 'react';
import {
  toCodePoints,
  cpLen,
  cpSlice,
  findNextWordStart,
  findPrevWordStart,
  stripUnsafeCharacters,
  getStringWidth,
  getCharWidth,
  getCachedStringWidth,
} from './textUtils.js';

/**
 * Direction for cursor movement
 */
export type Direction =
  | 'left'
  | 'right'
  | 'up'
  | 'down'
  | 'wordLeft'
  | 'wordRight'
  | 'home'
  | 'end';

/**
 * Viewport configuration
 */
export interface Viewport {
  height: number;
  width: number;
}

/**
 * Cursor position (logical position in text)
 */
export interface CursorPosition {
  row: number;
  col: number;
}

/**
 * Text buffer state
 */
export interface TextBufferState {
  text: string;
  cursorPos: number; // Offset in the text
  scrollOffset: number; // For viewport scrolling
}

/**
 * History entry for undo/redo
 */
interface HistoryEntry {
  text: string;
  cursorPos: number;
}

/**
 * Transformation interface - for future extensibility
 * Currently returns empty transformations (no-op)
 */
export interface Transformation {
  logStart: number;        // Start position in logical text
  logEnd: number;          // End position in logical text
  logicalText: string;     // Original text (e.g. full path)
  collapsedText: string;   // Collapsed display text (e.g. "[Image ...]")
  type: 'image' | 'paste'; // Segment type
  id?: string;             // Paste placeholder ID
}

/**
 * Visual layout - maps logical lines to visual lines considering wrapping
 */
export interface VisualLayout {
  visualLines: string[]; // All visual lines after wrapping
  logicalToVisualMap: Array<Array<[number, number]>>; // For each logical line: [[visualLineIndex, startColInLogical], ...]
  visualToLogicalMap: Array<[number, number]>; // For each visual line: [logicalLineIndex, startColInLogical]
  transformedToLogicalMaps: number[][]; // For each logical line: mapping from transformed position to logical position
}

/**
 * Calculate transformations for a line
 * Currently returns empty array (no transformations)
 * Future: Add image path detection, paste placeholder detection, etc.
 */
export function calculateTransformationsForLine(line: string): Transformation[] {
  // Future: Add image path detection, paste placeholder detection, etc.
  return [];
}

/**
 * Apply transformations to a line
 * Currently a no-op that returns the original line with 1:1 mapping
 */
function applyTransformationsToLine(
  logLine: string,
  transforms: Transformation[],
  logicalCursor: [number, number],
  currentLogicalRow: number,
): { transformedLine: string; transformedToLogMap: number[] } {
  // If no transformations, return original line with 1:1 mapping
  if (transforms.length === 0) {
    const transformedLine = logLine;
    const transformedToLogMap: number[] = [];
    
    // Create 1:1 mapping: transformedToLogMap[i] = i
    // This means position i in transformed text maps to position i in logical text
    for (let i = 0; i <= cpLen(logLine); i++) {
      transformedToLogMap.push(i);
    }
    
    return { transformedLine, transformedToLogMap };
  }
  
  // Future: Implement actual transformation logic here
  // For now, just return original with 1:1 mapping
  const transformedLine = logLine;
  const transformedToLogMap: number[] = [];
  for (let i = 0; i <= cpLen(logLine); i++) {
    transformedToLogMap.push(i);
  }
  
  return { transformedLine, transformedToLogMap };
}

/**
 * Calculate visual layout with word-wrapping
 */
export function calculateLayout(
  logicalLines: string[],
  viewportWidth: number,
  logicalCursor: [number, number] = [0, 0],
): VisualLayout {
  const visualLines: string[] = [];
  const logicalToVisualMap: Array<Array<[number, number]>> = [];
  const visualToLogicalMap: Array<[number, number]> = [];
  const transformedToLogicalMaps: number[][] = [];

  logicalLines.forEach((logLine, logIndex) => {
    logicalToVisualMap[logIndex] = [];

    // Calculate transformations for this line
    const transforms = calculateTransformationsForLine(logLine);
    
    // Apply transformations
    const { transformedLine, transformedToLogMap } = applyTransformationsToLine(
      logLine,
      transforms,
      logicalCursor,
      logIndex,
    );
    
    // Store the transformation mapping
    transformedToLogicalMaps[logIndex] = transformedToLogMap;

    if (transformedLine.length === 0) {
      // Handle empty logical line
      logicalToVisualMap[logIndex].push([visualLines.length, 0]);
      visualToLogicalMap.push([logIndex, 0]);
      visualLines.push('');
      return;
    }

    // Non-empty logical line - process the transformed line
    let currentPosInLogLine = 0; // Tracks position within the transformed line (code point index)
    const codePointsInLogLine = toCodePoints(transformedLine);

    while (currentPosInLogLine < codePointsInLogLine.length) {
      let currentChunk = '';
      let currentChunkVisualWidth = 0;
      let numCodePointsInChunk = 0;
      let lastWordBreakPoint = -1; // Index in codePointsInLogLine for word break
      let numCodePointsAtLastWordBreak = 0;

      // Iterate through code points to build the current visual line (chunk)
      for (let i = currentPosInLogLine; i < codePointsInLogLine.length; i++) {
        const char = codePointsInLogLine[i];
        const charVisualWidth = getCachedStringWidth(char);

        if (currentChunkVisualWidth + charVisualWidth > viewportWidth) {
          // Character would exceed viewport width
          if (
            lastWordBreakPoint !== -1 &&
            numCodePointsAtLastWordBreak > 0 &&
            currentPosInLogLine + numCodePointsAtLastWordBreak < i
          ) {
            // We have a valid word break point to use, and it's not the start of the current segment
            currentChunk = codePointsInLogLine
              .slice(
                currentPosInLogLine,
                currentPosInLogLine + numCodePointsAtLastWordBreak,
              )
              .join('');
            numCodePointsInChunk = numCodePointsAtLastWordBreak;
          } else {
            // No word break, or word break is at the start of this potential chunk, or word break leads to empty chunk.
            // Hard break: take characters up to viewportWidth, or just the current char if it alone is too wide.
            if (
              numCodePointsInChunk === 0 &&
              charVisualWidth > viewportWidth
            ) {
              // Single character is wider than viewport, take it anyway
              currentChunk = char;
              numCodePointsInChunk = 1;
            }
          }
          break; // Break from inner loop to finalize this chunk
        }

        currentChunk += char;
        currentChunkVisualWidth += charVisualWidth;
        numCodePointsInChunk++;

        // Check for word break opportunity (space)
        if (char === ' ') {
          lastWordBreakPoint = i; // Store code point index of the space
          // Store the state *before* adding the space, if we decide to break here.
          numCodePointsAtLastWordBreak = numCodePointsInChunk - 1; // Chars *before* the space
        }
      }

      if (
        numCodePointsInChunk === 0 &&
        currentPosInLogLine < codePointsInLogLine.length
      ) {
        const firstChar = codePointsInLogLine[currentPosInLogLine];
        currentChunk = firstChar;
        numCodePointsInChunk = 1;
      }

      // logicalStartCol is mapped via transformedToLogMap
      const logicalStartCol = transformedToLogMap[currentPosInLogLine] ?? 0;
      logicalToVisualMap[logIndex].push([visualLines.length, logicalStartCol]);
      visualToLogicalMap.push([logIndex, logicalStartCol]);
      visualLines.push(currentChunk);

      const logicalStartOfThisChunk = currentPosInLogLine;
      currentPosInLogLine += numCodePointsInChunk;

      if (
        logicalStartOfThisChunk + numCodePointsInChunk <
          codePointsInLogLine.length &&
        currentPosInLogLine < codePointsInLogLine.length &&
        codePointsInLogLine[currentPosInLogLine] === ' '
      ) {
        currentPosInLogLine++;
      }
    }
  });

  // If the entire logical text was empty, ensure there's one empty visual line.
  if (
    logicalLines.length === 0 ||
    (logicalLines.length === 1 && logicalLines[0] === '')
  ) {
    if (visualLines.length === 0) {
      visualLines.push('');
      if (!logicalToVisualMap[0]) logicalToVisualMap[0] = [];
      logicalToVisualMap[0].push([0, 0]);
      visualToLogicalMap.push([0, 0]);
    }
  }

  return {
    visualLines,
    logicalToVisualMap,
    visualToLogicalMap,
    transformedToLogicalMaps,
  };
}

/**
 * Convert logical cursor position to visual cursor position
 */
export function logicalToVisualCursor(
  layout: VisualLayout,
  logicalCursor: [number, number],
): [number, number] {
  const { logicalToVisualMap, visualLines, transformedToLogicalMaps } = layout;
  const [logicalRow, logicalCol] = logicalCursor;

  const segmentsForLogicalLine = logicalToVisualMap[logicalRow];

  if (!segmentsForLogicalLine || segmentsForLogicalLine.length === 0) {
    // This can happen for an empty document.
    return [0, 0];
  }

  // Get transformation mapping for this line
  const transformedToLogMap = transformedToLogicalMaps[logicalRow] || [];
  
  // Find transformed column from logical column
  // transformedToLogMap[i] = logical position that transformed position i maps to
  // We need to find the transformed position where transformedToLogMap[i] >= logicalCol
  let transformedCol = logicalCol;
  if (transformedToLogMap.length > 0) {
    // Find the first transformed position that maps to or past the logical column
    transformedCol = transformedToLogMap.findIndex(logPos => logPos >= logicalCol);
    if (transformedCol === -1) {
      // If not found, cursor is at the end
      transformedCol = transformedToLogMap.length - 1;
    }
  }

  // Find the segment where the transformed column fits.
  // The segments are sorted by startColInLogical (which now refers to transformed positions).
  let targetSegmentIndex = segmentsForLogicalLine.findIndex(
    ([, startColInTransformed], index) => {
      const nextStartColInTransformed =
        index + 1 < segmentsForLogicalLine.length
          ? segmentsForLogicalLine[index + 1][1]
          : Infinity;
      return (
        transformedCol >= startColInTransformed && transformedCol < nextStartColInTransformed
      );
    },
  );

  // If not found, it means the cursor is at the end of the logical line.
  if (targetSegmentIndex === -1) {
    if (transformedCol === 0) {
      targetSegmentIndex = 0;
    } else {
      targetSegmentIndex = segmentsForLogicalLine.length - 1;
    }
  }

  const [visualRow, startColInTransformed] =
    segmentsForLogicalLine[targetSegmentIndex];

  // Calculate visual column offset within this segment
  const visualCol = transformedCol - startColInTransformed;
  const clampedVisualCol = Math.min(
    Math.max(visualCol, 0),
    cpLen(visualLines[visualRow] ?? ''),
  );
  
  return [visualRow, clampedVisualCol];
}

/**
 * TextBuffer hook for managing text input
 */
export interface TextBuffer {
  // State
  text: string;
  cursorPos: number;
  lines: string[];
  cursorPosition: CursorPosition;
  scrollOffset: number;
  visibleLines: string[];
  
  // Visual layout (with wrapping)
  visualLayout: VisualLayout;
  visualCursor: [number, number];
  visualLines: string[];
  visibleVisualLines: string[];
  
  // Actions
  setText: (text: string) => void;
  insert: (text: string) => void;
  delete: (count: number) => void;
  backspace: (count?: number) => void;
  moveCursor: (direction: Direction) => void;
  setCursorPos: (pos: number) => void;
  clear: () => void;
  killLineRight: () => void;
  killLineLeft: () => void;
  deleteWordBackward: () => void;
  
  // History
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  
  // Viewport
  scroll: (delta: number) => void;
  scrollToBottom: () => void;
}

/**
 * Convert flat cursor position to (row, col)
 */
function offsetToCursorPosition(text: string, offset: number): CursorPosition {
  const lines = text.split('\n');
  let pos = 0;
  
  for (let row = 0; row < lines.length; row++) {
    const lineLength = lines[row].length;
    if (pos + lineLength >= offset) {
      return { row, col: offset - pos };
    }
    pos += lineLength + 1; // +1 for newline
  }
  
  // If offset is beyond text, place at end
  const lastRow = lines.length - 1;
  return { row: lastRow, col: lines[lastRow].length };
}

/**
 * Convert (row, col) to flat cursor position
 */
function cursorPositionToOffset(lines: string[], row: number, col: number): number {
  let offset = 0;
  for (let i = 0; i < row && i < lines.length; i++) {
    offset += lines[i].length + 1; // +1 for newline
  }
  return offset + col;
}

/**
 * Create a text buffer hook
 */
export function useTextBuffer(viewport: Viewport): TextBuffer {
  const [state, setState] = useState<TextBufferState>({
    text: '',
    cursorPos: 0,
    scrollOffset: 0,
  });

  // History stacks for undo/redo
  const undoStack = useRef<HistoryEntry[]>([]);
  const redoStack = useRef<HistoryEntry[]>([]);

  // Save current state to history
  const saveToHistory = useCallback(() => {
    undoStack.current.push({
      text: state.text,
      cursorPos: state.cursorPos,
    });
    
    // Limit history size
    if (undoStack.current.length > 100) {
      undoStack.current.shift();
    }
    
    // Clear redo stack on new action
    redoStack.current = [];
  }, [state]);

  // Derived values
  const lines = state.text.split('\n');
  const cursorPosition = offsetToCursorPosition(state.text, state.cursorPos);
  
  // Calculate visual layout with wrapping
  const visualLayout = useMemo(
    () => calculateLayout(lines, viewport.width),
    [lines, viewport.width]
  );
  
  // Convert logical cursor to visual cursor
  const visualCursor = useMemo(
    () => logicalToVisualCursor(visualLayout, [cursorPosition.row, cursorPosition.col]),
    [visualLayout, cursorPosition]
  );
  
  // Calculate visible lines based on viewport and scroll offset
  const startLine = Math.max(0, Math.min(state.scrollOffset, lines.length - 1));
  const endLine = Math.min(lines.length, startLine + viewport.height);
  const visibleLines = lines.slice(startLine, endLine);
  
  // Calculate visible visual lines based on viewport
  const visualLines = visualLayout.visualLines;
  const startVisualLine = Math.max(0, Math.min(state.scrollOffset, visualLines.length - 1));
  const endVisualLine = Math.min(visualLines.length, startVisualLine + viewport.height);
  const visibleVisualLines = visualLines.slice(startVisualLine, endVisualLine);

  // Set text directly
  const setText = useCallback((newText: string) => {
    saveToHistory();
    const cleaned = stripUnsafeCharacters(newText);
    setState((prev) => ({
      ...prev,
      text: cleaned,
      cursorPos: Math.min(prev.cursorPos, cleaned.length),
    }));
  }, [saveToHistory]);

  // Insert text at cursor position
  const insert = useCallback((insertText: string) => {
    saveToHistory();
    const cleaned = stripUnsafeCharacters(insertText);
    const before = state.text.slice(0, state.cursorPos);
    const after = state.text.slice(state.cursorPos);
    const newText = before + cleaned + after;
    
    setState((prev) => ({
      ...prev,
      text: newText,
      // cursorPos is byte offset, so add byte length, not code point length
      cursorPos: prev.cursorPos + cleaned.length,
    }));
  }, [state.text, state.cursorPos, saveToHistory]);

  // Delete characters after cursor
  const deleteChars = useCallback((count: number = 1) => {
    if (state.cursorPos >= state.text.length) return;
    
    saveToHistory();
    // cursorPos is byte offset, so use string slice directly
    const before = state.text.slice(0, state.cursorPos);
    // Delete 'count' characters (not bytes) starting from cursor position
    const codePoints = toCodePoints(state.text.slice(state.cursorPos));
    const afterCodePoints = codePoints.slice(count);
    const after = afterCodePoints.join('');
    const newText = before + after;
    
    setState((prev) => ({
      ...prev,
      text: newText,
    }));
  }, [state.text, state.cursorPos, saveToHistory]);

  // Backspace - delete characters before cursor
  const backspace = useCallback((count: number = 1) => {
    if (state.cursorPos === 0) return;
    
    saveToHistory();
    // cursorPos is byte offset, so use string slice directly
    const after = state.text.slice(state.cursorPos);
    // Delete 'count' characters (not bytes) before cursor position
    const beforeCodePoints = toCodePoints(state.text.slice(0, state.cursorPos));
    const deleteCount = Math.min(count, beforeCodePoints.length);
    const remainingBeforeCodePoints = beforeCodePoints.slice(0, -deleteCount);
    const before = remainingBeforeCodePoints.join('');
    const newText = before + after;
    const newCursorPos = before.length; // byte offset after deletion
    
    setState((prev) => ({
      ...prev,
      text: newText,
      cursorPos: newCursorPos,
    }));
  }, [state.text, state.cursorPos, saveToHistory]);

  // Move cursor in specified direction
  const moveCursor = useCallback((direction: Direction) => {
    const pos = cursorPosition;
    let newPos = state.cursorPos;

    switch (direction) {
      case 'left':
        // Move one character (code point) to the left
        if (state.cursorPos > 0) {
          const beforeText = state.text.slice(0, state.cursorPos);
          const beforeCodePoints = toCodePoints(beforeText);
          if (beforeCodePoints.length > 0) {
            // Remove last character and get new byte offset
            const newBeforeCodePoints = beforeCodePoints.slice(0, -1);
            newPos = newBeforeCodePoints.join('').length;
          }
        }
        break;

      case 'right':
        // Move one character (code point) to the right
        if (state.cursorPos < state.text.length) {
          const afterText = state.text.slice(state.cursorPos);
          const afterCodePoints = toCodePoints(afterText);
          if (afterCodePoints.length > 0) {
            // Add one character and get new byte offset
            const firstChar = afterCodePoints[0];
            newPos = state.cursorPos + firstChar.length;
          }
        }
        break;

      case 'up': {
        // Move cursor up by visual line
        const visualLayout = calculateLayout(lines, viewport.width, [
          cursorPosition.row,
          cursorPosition.col,
        ]);
        const [visualRow, visualCol] = logicalToVisualCursor(visualLayout, [
          cursorPosition.row,
          cursorPosition.col,
        ]);

        if (visualRow > 0) {
          const newVisualRow = visualRow - 1;
          const [logicalRowForVisual, logicalStartCol] =
            visualLayout.visualToLogicalMap[newVisualRow] ?? [0, 0];

          // Target logical col = visual line start col in logical row + current visual col
          const targetLogicalCol = logicalStartCol + visualCol;
          const clampedLogicalCol = Math.min(
            targetLogicalCol,
            cpLen(lines[logicalRowForVisual] ?? ''),
          );

          newPos = cursorPositionToOffset(
            lines,
            logicalRowForVisual,
            clampedLogicalCol,
          );
        }
        break;
      }

      case 'down': {
        // Move cursor down by visual line
        const visualLayout = calculateLayout(lines, viewport.width, [
          cursorPosition.row,
          cursorPosition.col,
        ]);
        const [visualRow, visualCol] = logicalToVisualCursor(visualLayout, [
          cursorPosition.row,
          cursorPosition.col,
        ]);

        const lastVisualRow = visualLayout.visualLines.length - 1;
        if (visualRow < lastVisualRow) {
          const newVisualRow = visualRow + 1;
          const [logicalRowForVisual, logicalStartCol] =
            visualLayout.visualToLogicalMap[newVisualRow] ?? [lastVisualRow, 0];

          const targetLogicalCol = logicalStartCol + visualCol;
          const clampedLogicalCol = Math.min(
            targetLogicalCol,
            cpLen(lines[logicalRowForVisual] ?? ''),
          );

          newPos = cursorPositionToOffset(
            lines,
            logicalRowForVisual,
            clampedLogicalCol,
          );
        }
        break;
      }

      case 'wordLeft':
        newPos = findPrevWordStart(state.text, state.cursorPos);
        break;

      case 'wordRight':
        newPos = findNextWordStart(state.text, state.cursorPos);
        break;

      case 'home':
        newPos = cursorPositionToOffset(lines, pos.row, 0);
        break;

      case 'end':
        newPos = cursorPositionToOffset(lines, pos.row, lines[pos.row].length);
        break;
    }

    setState((prev) => ({ ...prev, cursorPos: newPos }));
  }, [state.text, state.cursorPos, cursorPosition, lines]);

  // Set cursor position directly
  const setCursorPos = useCallback((pos: number) => {
    setState((prev) => ({
      ...prev,
      cursorPos: Math.max(0, Math.min(pos, prev.text.length)),
    }));
  }, []);

  // Clear all text
  const clear = useCallback(() => {
    saveToHistory();
    setState({ text: '', cursorPos: 0, scrollOffset: 0 });
  }, [saveToHistory]);

  // Kill line right (Ctrl+K)
  const killLineRight = useCallback(() => {
    saveToHistory();
    const pos = cursorPosition;
    const lineStart = cursorPositionToOffset(lines, pos.row, 0);
    const lineEnd = lineStart + lines[pos.row].length;
    
    if (state.cursorPos === lineEnd && pos.row < lines.length - 1) {
      // At end of line, delete the newline
      deleteChars(1);
    } else {
      // Delete from cursor to end of line
      const before = state.text.slice(0, state.cursorPos);
      const after = state.text.slice(lineEnd);
      setState((prev) => ({ ...prev, text: before + after }));
    }
  }, [state.text, state.cursorPos, cursorPosition, lines, saveToHistory, deleteChars]);

  // Kill line left (Ctrl+U)
  const killLineLeft = useCallback(() => {
    saveToHistory();
    const pos = cursorPosition;
    const lineStart = cursorPositionToOffset(lines, pos.row, 0);
    
    const before = state.text.slice(0, lineStart);
    const after = state.text.slice(state.cursorPos);
    
    setState((prev) => ({
      ...prev,
      text: before + after,
      cursorPos: lineStart,
    }));
  }, [state.text, state.cursorPos, cursorPosition, lines, saveToHistory]);

  // Delete word backward (Ctrl+W or Cmd+Backspace)
  const deleteWordBackward = useCallback(() => {
    if (state.cursorPos === 0) return;
    
    saveToHistory();
    const wordStart = findPrevWordStart(state.text, state.cursorPos);
    const before = state.text.slice(0, wordStart);
    const after = state.text.slice(state.cursorPos);
    
    setState((prev) => ({
      ...prev,
      text: before + after,
      cursorPos: wordStart,
    }));
  }, [state.text, state.cursorPos, saveToHistory]);

  // Undo
  const undo = useCallback(() => {
    const entry = undoStack.current.pop();
    if (entry) {
      redoStack.current.push({
        text: state.text,
        cursorPos: state.cursorPos,
      });
      setState((prev) => ({
        ...prev,
        text: entry.text,
        cursorPos: entry.cursorPos,
      }));
    }
  }, [state.text, state.cursorPos]);

  // Redo
  const redo = useCallback(() => {
    const entry = redoStack.current.pop();
    if (entry) {
      undoStack.current.push({
        text: state.text,
        cursorPos: state.cursorPos,
      });
      setState((prev) => ({
        ...prev,
        text: entry.text,
        cursorPos: entry.cursorPos,
      }));
    }
  }, [state.text, state.cursorPos]);

  // Scroll viewport
  const scroll = useCallback((delta: number) => {
    setState((prev) => ({
      ...prev,
      scrollOffset: Math.max(0, Math.min(prev.scrollOffset + delta, lines.length - viewport.height)),
    }));
  }, [lines.length, viewport.height]);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    setState((prev) => ({
      ...prev,
      scrollOffset: Math.max(0, lines.length - viewport.height),
    }));
  }, [lines.length, viewport.height]);

  return {
    // State
    text: state.text,
    cursorPos: state.cursorPos,
    lines,
    cursorPosition,
    scrollOffset: state.scrollOffset,
    visibleLines,
    
    // Visual layout (with wrapping)
    visualLayout,
    visualCursor,
    visualLines,
    visibleVisualLines,
    
    // Actions
    setText,
    insert,
    delete: deleteChars,
    backspace,
    moveCursor,
    setCursorPos,
    clear,
    killLineRight,
    killLineLeft,
    deleteWordBackward,
    
    // History
    undo,
    redo,
    canUndo: undoStack.current.length > 0,
    canRedo: redoStack.current.length > 0,
    
    // Viewport
    scroll,
    scrollToBottom,
  };
}

/**
 * Enhanced TextBuffer hook with reducer pattern
 * This is the new version that uses the reducer for complex state management
 */
import {
  textBufferReducer,
  createInitialState,
  type TextBufferState as ReducerState,
  type TextBufferAction,
  type TextBufferOptions,
  type Direction as ReducerDirection,
} from './TextBufferReducer.js';

/**
 * Enhanced TextBuffer interface
 */
export interface EnhancedTextBuffer {
  // State
  text: string;
  lines: string[];
  cursorRow: number;
  cursorCol: number;
  cursorPosition: CursorPosition;
  scrollOffset: number;
  
  // Visual layout (with wrapping)
  visualLayout: VisualLayout;
  visualCursor: [number, number];
  visualLines: string[];
  visualToLogicalMap: Array<[number, number]>; // For each visual line: [logicalLineIndex, startColInLogical]
  logicalToVisualMap: Array<Array<[number, number]>>; // For each logical line: [[visualLineIndex, startColInLogical], ...]
  
  // Visible lines (for viewport scrolling)
  visibleLines: string[]; // Logical lines that are visible
  visibleVisualLines: string[]; // Visual lines that are visible (with wrapping)
  visibleStartRow: number; // First visible logical row
  visibleEndRow: number; // Last visible logical row
  
  // Actions
  setText: (text: string) => void;
  insert: (text: string) => void;
  backspace: (count?: number) => void;
  deleteChars: (count?: number) => void;
  deleteWordLeft: () => void;
  deleteWordRight: () => void;
  killLineRight: () => void;
  killLineLeft: () => void;
  moveCursor: (direction: ReducerDirection) => void;
  setCursor: (row: number, col: number) => void;
  clear: () => void;
  
  // History
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  
  // Viewport
  scroll: (delta: number) => void;
  scrollToBottom: () => void;
  scrollToCursor: () => void; // Auto-scroll to keep cursor visible
  
  // Direct dispatch for advanced operations
  dispatch: (action: TextBufferAction) => void;
}

/**
 * Enhanced TextBuffer hook using reducer pattern
 */
export function useEnhancedTextBuffer(
  viewport: Viewport,
  options: TextBufferOptions = {},
  initialText: string = '',
): EnhancedTextBuffer {
  const [state, dispatch] = useReducer(
    (s: ReducerState, a: TextBufferAction) => textBufferReducer(s, a, options),
    createInitialState(initialText),
  );

  // Optimization: use hash cache to reduce O(n) array comparison to O(1)
  const layoutCacheRef = useRef<{
    linesHash: string;  // Hash of lines array for fast comparison
    width: number;
    layout: VisualLayout;
  } | null>(null);

  // Compute a fast hash of lines for change detection
  // Pure function; no memoization needed
  const calculateLinesHash = (lines: string[]): string => {
    // Uses line count + total chars + first/last line as hash
    if (lines.length === 0) return '0:0::';
    if (lines.length === 1) return `1:${lines[0].length}:${lines[0]}:`;
    return `${lines.length}:${lines.join('').length}:${lines[0]}:${lines[lines.length - 1]}`;
  };

  // Calculate visual layout with wrapping (with optimized hash-based cache)
  const visualLayout = useMemo(() => {
    const cache = layoutCacheRef.current;
    const currentHash = calculateLinesHash(state.lines);
    
    // O(1) hash comparison instead of O(n) array diff
    if (cache && 
        cache.width === viewport.width && 
        cache.linesHash === currentHash) {
      return cache.layout;
    }
    
    const newLayout = calculateLayout(state.lines, viewport.width);
    
    // Update cache (hash only, not full array)
    layoutCacheRef.current = {
      linesHash: currentHash,
      width: viewport.width,
      layout: newLayout,
    };
    
    return newLayout;
  }, [state, viewport.width]);

  // Convert logical cursor to visual cursor
  const visualCursor = useMemo(
    () => logicalToVisualCursor(visualLayout, [state.cursorRow, state.cursorCol]),
    [visualLayout, state.cursorRow, state.cursorCol],
  );

  // Derived text from lines
  const text = useMemo(() => state.lines.join('\n'), [state.lines]);

  // Cursor position interface
  const cursorPosition: CursorPosition = {
    row: state.cursorRow,
    col: state.cursorCol,
  };

  // Calculate visible logical lines based on scrollOffset
  const visibleLogical = useMemo(() => {
    const totalLines = state.lines.length;
    const startRow = Math.max(0, Math.min(state.scrollOffset, totalLines - viewport.height));
    const endRow = Math.min(totalLines, startRow + viewport.height);
    const lines = state.lines.slice(startRow, endRow);
    
    return {
      lines,
      startRow,
      endRow,
    };
  }, [state.lines, state.scrollOffset, viewport.height]);

  // Calculate visible visual lines (considering wrapping)
  const visibleVisual = useMemo(() => {
    const { visualLines } = visualLayout;
    const totalVisualLines = visualLines.length;
    
    // Use visual cursor position to determine scroll offset
    const visualScrollOffset = Math.max(0, Math.min(
      state.scrollOffset,
      Math.max(0, totalVisualLines - viewport.height)
    ));
    
    const startLine = visualScrollOffset;
    const endLine = Math.min(totalVisualLines, startLine + viewport.height);
    const lines = visualLines.slice(startLine, endLine);
    
    return {
      lines,
      startLine,
      endLine,
    };
  }, [visualLayout, state.scrollOffset, viewport.height]);

  // Action wrappers
  const setText = useCallback((newText: string) => {
    dispatch({ type: 'set_text', payload: newText });
  }, []);

  const insert = useCallback((insertText: string) => {
    dispatch({ type: 'insert', payload: insertText });
  }, []);

  const backspace = useCallback((count?: number) => {
    dispatch({ type: 'backspace', count });
  }, []);

  const deleteChars = useCallback((count?: number) => {
    dispatch({ type: 'delete', count });
  }, []);

  const deleteWordLeft = useCallback(() => {
    dispatch({ type: 'delete_word_left' });
  }, []);

  const deleteWordRight = useCallback(() => {
    dispatch({ type: 'delete_word_right' });
  }, []);

  const killLineRight = useCallback(() => {
    dispatch({ type: 'kill_line_right' });
  }, []);

  const killLineLeft = useCallback(() => {
    dispatch({ type: 'kill_line_left' });
  }, []);

  const moveCursor = useCallback((direction: ReducerDirection) => {
    dispatch({ type: 'move', payload: { dir: direction } });
  }, []);

  const setCursor = useCallback((row: number, col: number) => {
    dispatch({ type: 'set_cursor', payload: { cursorRow: row, cursorCol: col } });
  }, []);

  const clear = useCallback(() => {
    dispatch({ type: 'clear' });
  }, []);

  const undo = useCallback(() => {
    dispatch({ type: 'undo' });
  }, []);

  const redo = useCallback(() => {
    dispatch({ type: 'redo' });
  }, []);

  const scroll = useCallback((delta: number) => {
    dispatch({ type: 'scroll', payload: { delta } });
  }, []);

  const scrollToBottom = useCallback(() => {
    dispatch({ type: 'scroll_to_bottom' });
  }, []);

  // Auto-scroll to keep cursor visible
  const scrollToCursor = useCallback(() => {
    const [visualRow, visualCol] = visualCursor;
    const currentScrollOffset = state.scrollOffset;
    const viewportHeight = viewport.height;
    
    // If cursor is above viewport, scroll up
    if (visualRow < currentScrollOffset) {
      dispatch({ type: 'scroll', payload: { delta: visualRow - currentScrollOffset } });
    }
    // If cursor is below viewport, scroll down
    else if (visualRow >= currentScrollOffset + viewportHeight) {
      dispatch({ type: 'scroll', payload: { delta: visualRow - currentScrollOffset - viewportHeight + 1 } });
    }
  }, [visualCursor, state.scrollOffset, viewport.height]);

  // Auto-scroll after cursor movements or text changes
  useEffect(() => {
    scrollToCursor();
  }, [scrollToCursor]);

  return {
    // State
    text,
    lines: state.lines,
    cursorRow: state.cursorRow,
    cursorCol: state.cursorCol,
    cursorPosition,
    scrollOffset: state.scrollOffset,
    
    // Visual layout
    visualLayout,
    visualCursor,
    visualLines: visualLayout.visualLines,
    visualToLogicalMap: visualLayout.visualToLogicalMap,
    logicalToVisualMap: visualLayout.logicalToVisualMap,
    
    // Visible lines (for rendering)
    visibleLines: visibleLogical.lines,
    visibleVisualLines: visibleVisual.lines,
    visibleStartRow: visibleLogical.startRow,
    visibleEndRow: visibleLogical.endRow,
    
    // Actions
    setText,
    insert,
    backspace,
    deleteChars,
    deleteWordLeft,
    deleteWordRight,
    killLineRight,
    killLineLeft,
    moveCursor,
    setCursor,
    clear,
    
    // History
    undo,
    redo,
    canUndo: state.undoStack.length > 0,
    canRedo: state.redoStack.length > 0,
    
    // Viewport
    scroll,
    scrollToBottom,
    scrollToCursor,
    
    // Direct dispatch
    dispatch,
  };
}
