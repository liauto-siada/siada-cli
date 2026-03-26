/**
 * TextBuffer Home/End Tests
 * Tests for Home and End key behavior
 */

import { describe, it, expect } from 'vitest';
import {
  textBufferReducer,
  createInitialState,
} from '../TextBufferReducer.js';

describe('TextBuffer Home/End', () => {
  describe('home action', () => {
    it('should move cursor to start of current line', () => {
      const state = createInitialState('Hello World');
      // Cursor at end of line
      expect(state.cursorCol).toBe(11);
      
      const newState = textBufferReducer(state, {
        type: 'move',
        payload: { dir: 'home' },
      });
      
      // Should move to start of current line
      expect(newState.cursorRow).toBe(0);
      expect(newState.cursorCol).toBe(0);
    });

    it('should move to start of current line in multi-line text', () => {
      const state = createInitialState('Line 1\nLine 2\nLine 3');
      
      // Move to middle of second line
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 1, cursorCol: 4 },
      });
      
      expect(moved.cursorRow).toBe(1);
      expect(moved.cursorCol).toBe(4);
      
      // Press Home
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'home' },
      });
      
      // Should move to start of second line (not first)
      expect(newState.cursorRow).toBe(1);
      expect(newState.cursorCol).toBe(0);
    });

    it('should stay on same line when already at start', () => {
      const state = createInitialState('Line 1\nLine 2');
      
      // Move to start of second line
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 1, cursorCol: 0 },
      });
      
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'home' },
      });
      
      // Should stay at start of second line
      expect(newState.cursorRow).toBe(1);
      expect(newState.cursorCol).toBe(0);
    });
  });

  describe('end action', () => {
    it('should move cursor to end of current line', () => {
      const state = createInitialState('Hello World');
      
      // Move to start
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 0, cursorCol: 0 },
      });
      
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'end' },
      });
      
      // Should move to end of current line
      expect(newState.cursorRow).toBe(0);
      expect(newState.cursorCol).toBe(11); // length of "Hello World"
    });

    it('should move to end of current line in multi-line text', () => {
      const state = createInitialState('Line 1\nLine 2\nLine 3');
      
      // Move to start of second line
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 1, cursorCol: 0 },
      });
      
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'end' },
      });
      
      // Should move to end of second line (not third)
      expect(newState.cursorRow).toBe(1);
      expect(newState.cursorCol).toBe(6); // length of "Line 2"
    });

    it('should stay on same line when already at end', () => {
      const state = createInitialState('Line 1\nLine 2');
      
      // Move to end of first line
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 0, cursorCol: 6 },
      });
      
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'end' },
      });
      
      // Should stay at end of first line
      expect(newState.cursorRow).toBe(0);
      expect(newState.cursorCol).toBe(6);
    });
  });

  describe('home/end with Chinese text', () => {
    it('should handle Chinese characters correctly with home', () => {
      const state = createInitialState('你好世界');
      
      expect(state.cursorCol).toBe(4); // 4 chars
      
      const newState = textBufferReducer(state, {
        type: 'move',
        payload: { dir: 'home' },
      });
      
      expect(newState.cursorCol).toBe(0);
    });

    it('should handle Chinese characters correctly with end', () => {
      const state = createInitialState('你好世界');
      
      // Move to start
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 0, cursorCol: 0 },
      });
      
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'end' },
      });
      
      expect(newState.cursorCol).toBe(4); // 4 chars
    });
  });

  describe('docStart/docEnd - document-level navigation', () => {
    it('should move to document start from anywhere', () => {
      const state = createInitialState('Line 1\nLine 2\nLine 3');
      
      // Move to middle of third line
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 2, cursorCol: 3 },
      });
      
      expect(moved.cursorRow).toBe(2);
      expect(moved.cursorCol).toBe(3);
      
      // Move to document start
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'docStart' },
      });
      
      // Should be at row 0, col 0
      expect(newState.cursorRow).toBe(0);
      expect(newState.cursorCol).toBe(0);
    });

    it('should move to document end from anywhere', () => {
      const state = createInitialState('Line 1\nLine 2\nLine 3');
      
      // Move to start of first line
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 0, cursorCol: 0 },
      });
      
      // Move to document end
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'docEnd' },
      });
      
      // Should be at last row, last col
      expect(newState.cursorRow).toBe(2);
      expect(newState.cursorCol).toBe(6); // length of "Line 3"
    });

    it('should handle docStart in single line', () => {
      const state = createInitialState('Hello World');
      
      const newState = textBufferReducer(state, {
        type: 'move',
        payload: { dir: 'docStart' },
      });
      
      expect(newState.cursorRow).toBe(0);
      expect(newState.cursorCol).toBe(0);
    });

    it('should handle docEnd in single line', () => {
      const state = createInitialState('Hello World');
      
      // Move to start
      let moved = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 0, cursorCol: 0 },
      });
      
      const newState = textBufferReducer(moved, {
        type: 'move',
        payload: { dir: 'docEnd' },
      });
      
      expect(newState.cursorRow).toBe(0);
      expect(newState.cursorCol).toBe(11);
    });

    it('should handle docStart/docEnd with empty lines', () => {
      const state = createInitialState('Line 1\n\nLine 3');
      
      // docStart
      let atStart = textBufferReducer(state, {
        type: 'move',
        payload: { dir: 'docStart' },
      });
      
      expect(atStart.cursorRow).toBe(0);
      expect(atStart.cursorCol).toBe(0);
      
      // docEnd
      let atEnd = textBufferReducer(atStart, {
        type: 'move',
        payload: { dir: 'docEnd' },
      });
      
      expect(atEnd.cursorRow).toBe(2);
      expect(atEnd.cursorCol).toBe(6);
    });
  });
});
