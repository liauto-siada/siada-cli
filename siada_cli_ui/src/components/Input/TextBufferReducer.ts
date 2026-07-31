/**
 * TextBuffer Reducer - State management for text buffer
 */

import {
  toCodePoints,
  cpLen,
  cpSlice,
  stripUnsafeCharacters,
  findNextWordStartInLine,
  findPrevWordStartInLine,
  findWordEndInLine,
  findNextWordAcrossLines,
  findPrevWordAcrossLines,
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
  | 'home'         // Move to line start
  | 'end'          // Move to line end
  | 'docStart'     // Move to document start
  | 'docEnd';      // Move to document end

/**
 * History entry for undo/redo
 */
export interface HistoryEntry {
  lines: string[];
  cursorRow: number;
  cursorCol: number;
}

/**
 * Text buffer state
 */
export interface TextBufferState {
  lines: string[];
  cursorRow: number;
  cursorCol: number;
  preferredCol: number | null; // For vertical movement
  undoStack: HistoryEntry[];
  redoStack: HistoryEntry[];
  scrollOffset: number; // For viewport scrolling
}

/**
 * Text buffer actions
 */
export type TextBufferAction =
  | { type: 'set_text'; payload: string; pushToUndo?: boolean }
  | { type: 'insert'; payload: string }
  | { type: 'backspace'; count?: number }
  | { type: 'delete'; count?: number }
  | { type: 'delete_word_left' }
  | { type: 'delete_word_right' }
  | { type: 'kill_line_right' }
  | { type: 'kill_line_left' }
  | { type: 'move'; payload: { dir: Direction } }
  | { type: 'set_cursor'; payload: { cursorRow: number; cursorCol: number; preferredCol?: number | null } }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'create_undo_snapshot' }
  | { type: 'clear' }
  | { type: 'scroll'; payload: { delta: number } }
  | { type: 'scroll_to_bottom' };

/**
 * Options for reducer
 */
export interface TextBufferOptions {
  /** Single line mode - prevents line breaks */
  singleLine?: boolean;
  
  /** 
   * @deprecated This parameter no longer limits input lines.
   * Use Viewport.height to control visible lines instead.
   * 
   * Previously used to limit the maximum number of lines in the buffer.
   * Now unlimited lines are allowed - only viewport height controls visibility.
   */
  maxLines?: number;
  
  /** Optional filter function to process input text */
  inputFilter?: (text: string) => string;
}

/**
 * History limit
 */
const HISTORY_LIMIT = 100;

/**
 * Push current state to undo stack
 */
function pushUndo(state: TextBufferState): TextBufferState {
  const snapshot: HistoryEntry = {
    lines: [...state.lines],
    cursorRow: state.cursorRow,
    cursorCol: state.cursorCol,
  };
  
  const newStack = [...state.undoStack, snapshot];
  if (newStack.length > HISTORY_LIMIT) {
    newStack.shift();
  }
  
  return { ...state, undoStack: newStack, redoStack: [] };
}

/**
 * Helper: Get current line
 */
function currentLine(state: TextBufferState, row: number): string {
  return state.lines[row] || '';
}

/**
 * Helper: Get current line length
 */
function currentLineLen(state: TextBufferState, row: number): number {
  return cpLen(currentLine(state, row));
}

/**
 * Helper: Clamp value between min and max
 */
function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/**
 * Replace range in text buffer (internal helper)
 */
function replaceRangeInternal(
  state: TextBufferState,
  startRow: number,
  startCol: number,
  endRow: number,
  endCol: number,
  text: string,
): TextBufferState {
  if (
    startRow > endRow ||
    (startRow === endRow && startCol > endCol) ||
    startRow < 0 ||
    startCol < 0 ||
    endRow >= state.lines.length ||
    (endRow < state.lines.length && endCol > currentLineLen(state, endRow))
  ) {
    return state; // Invalid range
  }

  const newLines = [...state.lines];

  const sCol = clamp(startCol, 0, currentLineLen(state, startRow));
  const eCol = clamp(endCol, 0, currentLineLen(state, endRow));

  const prefix = cpSlice(currentLine(state, startRow), 0, sCol);
  const suffix = cpSlice(currentLine(state, endRow), eCol);

  const normalizedReplacement = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const replacementParts = normalizedReplacement.split('\n');

  const firstLine = prefix + replacementParts[0];

  if (replacementParts.length === 1) {
    newLines.splice(startRow, endRow - startRow + 1, firstLine + suffix);
  } else {
    const lastLine = replacementParts[replacementParts.length - 1] + suffix;
    const middleLines = replacementParts.slice(1, -1);
    newLines.splice(startRow, endRow - startRow + 1, firstLine, ...middleLines, lastLine);
  }

  const finalCursorRow = startRow + replacementParts.length - 1;
  const finalCursorCol =
    (replacementParts.length > 1 ? 0 : sCol) +
    cpLen(replacementParts[replacementParts.length - 1]);

  return {
    ...state,
    lines: newLines,
    cursorRow: Math.min(Math.max(finalCursorRow, 0), newLines.length - 1),
    cursorCol: Math.max(0, Math.min(finalCursorCol, cpLen(newLines[finalCursorRow] || ''))),
    preferredCol: null,
  };
}

/**
 * Text buffer reducer
 */
export function textBufferReducer(
  state: TextBufferState,
  action: TextBufferAction,
  options: TextBufferOptions = {},
): TextBufferState {
  switch (action.type) {
    case 'set_text': {
      let nextState = state;
      if (action.pushToUndo !== false) {
        nextState = pushUndo(state);
      }
      
      const newContentLines = action.payload.replace(/\r\n?/g, '\n').split('\n');
      const lines = newContentLines.length === 0 ? [''] : newContentLines;
      const lastLineIndex = lines.length - 1;
      
      return {
        ...nextState,
        lines,
        cursorRow: lastLineIndex,
        cursorCol: cpLen(lines[lastLineIndex] || ''),
        preferredCol: null,
      };
    }

    case 'insert': {
      const nextState = pushUndo(state);
      const newLines = [...nextState.lines];
      let newCursorRow = nextState.cursorRow;
      let newCursorCol = nextState.cursorCol;

      let payload = action.payload;
      if (options.singleLine) {
        payload = payload.replace(/[\r\n]/g, '');
      }
      if (options.inputFilter) {
        payload = options.inputFilter(payload);
      }

      if (payload.length === 0) {
        return state;
      }

      const str = stripUnsafeCharacters(payload.replace(/\r\n/g, '\n').replace(/\r/g, '\n'));
      const parts = str.split('\n');
      const lineContent = currentLine(nextState, newCursorRow);
      const before = cpSlice(lineContent, 0, newCursorCol);
      const after = cpSlice(lineContent, newCursorCol);

      if (parts.length > 1) {
        // Multi-line insert
        newLines[newCursorRow] = before + parts[0];
        const remainingParts = parts.slice(1);
        const lastPartOriginal = remainingParts.pop() ?? '';
        newLines.splice(newCursorRow + 1, 0, ...remainingParts);
        newLines.splice(newCursorRow + parts.length - 1, 0, lastPartOriginal + after);
        newCursorRow = newCursorRow + parts.length - 1;
        newCursorCol = cpLen(lastPartOriginal);
      } else {
        // Single line insert
        newLines[newCursorRow] = before + parts[0] + after;
        newCursorCol = cpLen(before) + cpLen(parts[0]);
      }

      // Note: maxLines option is deprecated and no longer enforced
      // The viewport height controls how many lines are visible, not total input
      // if (options.maxLines && newLines.length > options.maxLines) {
      //   return state; // Reject insert
      // }

      return {
        ...nextState,
        lines: newLines,
        cursorRow: newCursorRow,
        cursorCol: newCursorCol,
        preferredCol: null,
      };
    }

    case 'backspace': {
      const count = action.count ?? 1;
      const nextState = pushUndo(state);
      const newLines = [...nextState.lines];
      let newCursorRow = nextState.cursorRow;
      let newCursorCol = nextState.cursorCol;

      for (let i = 0; i < count; i++) {
        if (newCursorCol === 0 && newCursorRow === 0) break;

        if (newCursorCol > 0) {
          const lineContent = newLines[newCursorRow] || '';
          newLines[newCursorRow] =
            cpSlice(lineContent, 0, newCursorCol - 1) + cpSlice(lineContent, newCursorCol);
          newCursorCol--;
        } else if (newCursorRow > 0) {
          const prevLineContent = newLines[newCursorRow - 1] || '';
          const currentLineContentVal = newLines[newCursorRow] || '';
          const newCol = cpLen(prevLineContent);
          newLines[newCursorRow - 1] = prevLineContent + currentLineContentVal;
          newLines.splice(newCursorRow, 1);
          newCursorRow--;
          newCursorCol = newCol;
        }
      }

      return {
        ...nextState,
        lines: newLines,
        cursorRow: newCursorRow,
        cursorCol: newCursorCol,
        preferredCol: null,
      };
    }

    case 'delete': {
      const count = action.count ?? 1;
      const { cursorRow, cursorCol, lines } = state;
      const lineContent = currentLine(state, cursorRow);
      
      if (cursorCol < currentLineLen(state, cursorRow)) {
        const nextState = pushUndo(state);
        const newLines = [...nextState.lines];
        const endCol = Math.min(cursorCol + count, cpLen(lineContent));
        newLines[cursorRow] = cpSlice(lineContent, 0, cursorCol) + cpSlice(lineContent, endCol);
        
        return {
          ...nextState,
          lines: newLines,
          preferredCol: null,
        };
      } else if (cursorRow < lines.length - 1) {
        // At end of line, join with next line
        const nextState = pushUndo(state);
        const nextLineContent = currentLine(state, cursorRow + 1);
        const newLines = [...nextState.lines];
        newLines[cursorRow] = lineContent + nextLineContent;
        newLines.splice(cursorRow + 1, 1);
        
        return {
          ...nextState,
          lines: newLines,
          preferredCol: null,
        };
      }
      
      return state;
    }

    case 'delete_word_left': {
      const { cursorRow, cursorCol } = state;
      if (cursorCol === 0 && cursorRow === 0) return state;

      const nextState = pushUndo(state);
      const newLines = [...nextState.lines];
      let newCursorRow = cursorRow;
      let newCursorCol = cursorCol;

      if (newCursorCol > 0) {
        const lineContent = currentLine(state, newCursorRow);
        const prevWordStart = findPrevWordStartInLine(lineContent, newCursorCol);
        const start = prevWordStart === null ? 0 : prevWordStart;
        newLines[newCursorRow] =
          cpSlice(lineContent, 0, start) + cpSlice(lineContent, newCursorCol);
        newCursorCol = start;
      } else {
        // Act as backspace at start of line
        const prevLineContent = currentLine(state, cursorRow - 1);
        const currentLineContentVal = currentLine(state, cursorRow);
        const newCol = cpLen(prevLineContent);
        newLines[cursorRow - 1] = prevLineContent + currentLineContentVal;
        newLines.splice(cursorRow, 1);
        newCursorRow--;
        newCursorCol = newCol;
      }

      return {
        ...nextState,
        lines: newLines,
        cursorRow: newCursorRow,
        cursorCol: newCursorCol,
        preferredCol: null,
      };
    }

    case 'delete_word_right': {
      const { cursorRow, cursorCol, lines } = state;
      const lineContent = currentLine(state, cursorRow);
      const lineLen = cpLen(lineContent);

      if (cursorCol >= lineLen && cursorRow === lines.length - 1) {
        return state;
      }

      const nextState = pushUndo(state);
      const newLines = [...nextState.lines];

      if (cursorCol >= lineLen) {
        // Join with next line
        const nextLineContent = currentLine(state, cursorRow + 1);
        newLines[cursorRow] = lineContent + nextLineContent;
        newLines.splice(cursorRow + 1, 1);
      } else {
        const nextWordStart = findNextWordStartInLine(lineContent, cursorCol);
        const end = nextWordStart === null ? lineLen : nextWordStart;
        newLines[cursorRow] = cpSlice(lineContent, 0, cursorCol) + cpSlice(lineContent, end);
      }

      return {
        ...nextState,
        lines: newLines,
        preferredCol: null,
      };
    }

    case 'kill_line_right': {
      const { cursorRow, cursorCol, lines } = state;
      const lineContent = currentLine(state, cursorRow);
      
      if (cursorCol < currentLineLen(state, cursorRow)) {
        const nextState = pushUndo(state);
        const newLines = [...nextState.lines];
        newLines[cursorRow] = cpSlice(lineContent, 0, cursorCol);
        return {
          ...nextState,
          lines: newLines,
        };
      } else if (cursorRow < lines.length - 1) {
        // Join with next line
        const nextState = pushUndo(state);
        const nextLineContent = currentLine(state, cursorRow + 1);
        const newLines = [...nextState.lines];
        newLines[cursorRow] = lineContent + nextLineContent;
        newLines.splice(cursorRow + 1, 1);
        return {
          ...nextState,
          lines: newLines,
          preferredCol: null,
        };
      }
      
      return state;
    }

    case 'kill_line_left': {
      const { cursorRow, cursorCol } = state;
      if (cursorCol > 0) {
        const nextState = pushUndo(state);
        const lineContent = currentLine(state, cursorRow);
        const newLines = [...nextState.lines];
        newLines[cursorRow] = cpSlice(lineContent, cursorCol);
        return {
          ...nextState,
          lines: newLines,
          cursorCol: 0,
          preferredCol: null,
        };
      } else if (cursorRow > 0) {
        // At col 0 with a previous line: delete the newline (merge with previous line)
        const nextState = pushUndo(state);
        const newLines = [...nextState.lines];
        const prevLineContent = newLines[cursorRow - 1] || '';
        const currentLineContent = newLines[cursorRow] || '';
        const newCol = cpLen(prevLineContent);
        newLines[cursorRow - 1] = prevLineContent + currentLineContent;
        newLines.splice(cursorRow, 1);
        return {
          ...nextState,
          lines: newLines,
          cursorRow: cursorRow - 1,
          cursorCol: newCol,
          preferredCol: null,
        };
      }
      return state;
    }

    case 'move': {
      const { dir } = action.payload;
      const { cursorRow, cursorCol, lines, preferredCol } = state;

      let newCursorRow = cursorRow;
      let newCursorCol = cursorCol;
      let newPreferredCol = preferredCol;

      switch (dir) {
        case 'left':
          newPreferredCol = null;
          if (newCursorCol > 0) {
            newCursorCol--;
          } else if (newCursorRow > 0) {
            newCursorRow--;
            newCursorCol = currentLineLen(state, newCursorRow);
          }
          break;

        case 'right':
          newPreferredCol = null;
          if (newCursorCol < currentLineLen(state, cursorRow)) {
            newCursorCol++;
          } else if (newCursorRow < lines.length - 1) {
            newCursorRow++;
            newCursorCol = 0;
          }
          break;

        case 'up':
          if (newCursorRow > 0) {
            if (newPreferredCol === null) newPreferredCol = newCursorCol;
            newCursorRow--;
            newCursorCol = clamp(newPreferredCol, 0, currentLineLen(state, newCursorRow));
          }
          break;

        case 'down':
          if (newCursorRow < lines.length - 1) {
            if (newPreferredCol === null) newPreferredCol = newCursorCol;
            newCursorRow++;
            newCursorCol = clamp(newPreferredCol, 0, currentLineLen(state, newCursorRow));
          }
          break;

        case 'wordLeft': {
          const result = findPrevWordAcrossLines(lines, cursorRow, cursorCol);
          if (result) {
            newCursorRow = result.row;
            newCursorCol = result.col;
            newPreferredCol = null;
          } else if (cursorRow > 0 || cursorCol > 0) {
            // Fallback: move to start
            newCursorRow = 0;
            newCursorCol = 0;
            newPreferredCol = null;
          }
          break;
        }

        case 'wordRight': {
          const result = findNextWordAcrossLines(lines, cursorRow, cursorCol, true);
          if (result) {
            newCursorRow = result.row;
            newCursorCol = result.col;
            newPreferredCol = null;
          } else if (cursorRow < lines.length - 1 || cursorCol < currentLineLen(state, cursorRow)) {
            // Fallback: move to end
            newCursorRow = lines.length - 1;
            newCursorCol = currentLineLen(state, newCursorRow);
            newPreferredCol = null;
          }
          break;
        }

        case 'home':
          newCursorCol = 0;
          newPreferredCol = null;
          break;

        case 'end':
          newCursorCol = currentLineLen(state, cursorRow);
          newPreferredCol = null;
          break;

        case 'docStart':
          // Move to document start
          newCursorRow = 0;
          newCursorCol = 0;
          newPreferredCol = null;
          break;

        case 'docEnd':
          // Move to document end
          newCursorRow = lines.length - 1;
          newCursorCol = currentLineLen(state, lines.length - 1);
          newPreferredCol = null;
          break;
      }

      return {
        ...state,
        cursorRow: newCursorRow,
        cursorCol: newCursorCol,
        preferredCol: newPreferredCol,
      };
    }

    case 'set_cursor': {
      return {
        ...state,
        cursorRow: action.payload.cursorRow,
        cursorCol: action.payload.cursorCol,
        preferredCol: action.payload.preferredCol ?? null,
      };
    }

    case 'undo': {
      const stateToRestore = state.undoStack[state.undoStack.length - 1];
      if (!stateToRestore) return state;

      const currentSnapshot: HistoryEntry = {
        lines: [...state.lines],
        cursorRow: state.cursorRow,
        cursorCol: state.cursorCol,
      };
      
      return {
        ...state,
        ...stateToRestore,
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, currentSnapshot],
      };
    }

    case 'redo': {
      const stateToRestore = state.redoStack[state.redoStack.length - 1];
      if (!stateToRestore) return state;

      const currentSnapshot: HistoryEntry = {
        lines: [...state.lines],
        cursorRow: state.cursorRow,
        cursorCol: state.cursorCol,
      };
      
      return {
        ...state,
        ...stateToRestore,
        redoStack: state.redoStack.slice(0, -1),
        undoStack: [...state.undoStack, currentSnapshot],
      };
    }

    case 'create_undo_snapshot': {
      return pushUndo(state);
    }

    case 'clear': {
      const nextState = pushUndo(state);
      return {
        ...nextState,
        lines: [''],
        cursorRow: 0,
        cursorCol: 0,
        preferredCol: null,
        scrollOffset: 0, // Reset scroll offset when clearing
      };
    }

    case 'scroll': {
      const maxScroll = Math.max(0, state.lines.length - 1);
      return {
        ...state,
        scrollOffset: clamp(state.scrollOffset + action.payload.delta, 0, maxScroll),
      };
    }

    case 'scroll_to_bottom': {
      return {
        ...state,
        scrollOffset: Math.max(0, state.lines.length - 1),
      };
    }

    default:
      return state;
  }
}

/**
 * Create initial text buffer state
 */
export function createInitialState(initialText: string = ''): TextBufferState {
  const lines = initialText.length === 0 ? [''] : initialText.replace(/\r\n?/g, '\n').split('\n');
  
  return {
    lines,
    cursorRow: lines.length - 1,
    cursorCol: cpLen(lines[lines.length - 1] || ''),
    preferredCol: null,
    undoStack: [],
    redoStack: [],
    scrollOffset: 0,
  };
}
