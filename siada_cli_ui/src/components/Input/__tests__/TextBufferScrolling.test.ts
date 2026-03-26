/**
 * TextBuffer Scrolling Tests
 * Tests for scrolling and visible line behavior
 */

import { describe, it, expect } from 'vitest';
import {
  textBufferReducer,
  createInitialState,
} from '../TextBufferReducer.js';

describe('TextBuffer Scrolling', () => {
  describe('scroll action', () => {
    it('should scroll down', () => {
      // Create multi-line text
      const text = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');
      const state = createInitialState(text);
      
      const newState = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 5 },
      });
      
      expect(newState.scrollOffset).toBe(5);
    });

    it('should scroll up', () => {
      const text = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');
      let state = createInitialState(text);
      
      // Scroll down first
      state = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 10 },
      });
      
      expect(state.scrollOffset).toBe(10);
      
      // Then scroll up
      const newState = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: -5 },
      });
      
      expect(newState.scrollOffset).toBe(5);
    });

    it('should not scroll below 0', () => {
      const state = createInitialState('Line 1\nLine 2');
      
      const newState = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: -10 },
      });
      
      expect(newState.scrollOffset).toBe(0);
    });

    it('should not scroll beyond total lines', () => {
      const text = 'Line 1\nLine 2\nLine 3';
      const state = createInitialState(text);
      
      const newState = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 100 },
      });
      
      // scrollOffset should be clamped to valid range
      expect(newState.scrollOffset).toBeGreaterThanOrEqual(0);
      expect(newState.scrollOffset).toBeLessThanOrEqual(state.lines.length);
    });
  });

  describe('scroll_to_bottom action', () => {
    it('should scroll to bottom', () => {
      const text = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');
      const state = createInitialState(text);
      
      const newState = textBufferReducer(state, {
        type: 'scroll_to_bottom',
      });
      
      // scrollOffset should be at or near the last line
      expect(newState.scrollOffset).toBeGreaterThan(0);
    });
  });

  describe('scrollOffset persistence', () => {
    it('should maintain scrollOffset after text insert', () => {
      const text = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');
      let state = createInitialState(text);
      
      // Scroll to middle
      state = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 5 },
      });
      
      const scrollOffsetBefore = state.scrollOffset;
      
      // Insert text at beginning
      state = textBufferReducer(state, {
        type: 'set_cursor',
        payload: { cursorRow: 0, cursorCol: 0 },
      });
      
      state = textBufferReducer(state, {
        type: 'insert',
        payload: 'New text',
      });
      
      // scrollOffset should be preserved (in practice may auto-scroll to cursor)
      expect(state.scrollOffset).toBe(scrollOffsetBefore);
    });

    it('should maintain scrollOffset after delete', () => {
      const text = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');
      let state = createInitialState(text);
      
      state = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 10 },
      });
      
      const scrollOffsetBefore = state.scrollOffset;
      
      state = textBufferReducer(state, {
        type: 'backspace',
      });
      
      expect(state.scrollOffset).toBe(scrollOffsetBefore);
    });
  });

  describe('scrollOffset with undo/redo', () => {
    it('should maintain scrollOffset through undo', () => {
      let state = createInitialState('Hello World');
      
      state = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 5 },
      });
      
      state = textBufferReducer(state, {
        type: 'insert',
        payload: ' Test',
      });
      
      const scrollOffsetBefore = state.scrollOffset;
      
      state = textBufferReducer(state, {
        type: 'undo',
      });
      
      // Undo should not change scrollOffset
      expect(state.scrollOffset).toBe(scrollOffsetBefore);
    });
  });

  describe('scrollOffset edge cases', () => {
    it('should handle empty text', () => {
      const state = createInitialState('');
      
      const newState = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 5 },
      });
      
      expect(newState.scrollOffset).toBe(0);
    });

    it('should handle single line', () => {
      const state = createInitialState('Single line');
      
      const newState = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 5 },
      });
      
      // Single-line text: scrollOffset should stay at 0
      expect(newState.scrollOffset).toBe(0);
    });
  });

  describe('clear with scroll', () => {
    it('should reset scrollOffset when clearing', () => {
      const text = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');
      let state = createInitialState(text);
      
      state = textBufferReducer(state, {
        type: 'scroll',
        payload: { delta: 10 },
      });
      
      expect(state.scrollOffset).toBe(10);
      
      // Clearing text should reset scrollOffset
      const newState = textBufferReducer(state, {
        type: 'clear',
      });
      
      expect(newState.scrollOffset).toBe(0);
      expect(newState.lines).toEqual(['']);
    });
  });
});
