/**
 * TextBufferReducer Tests
 */

import { describe, it, expect } from 'vitest';
import {
  textBufferReducer,
  createInitialState,
  type TextBufferState,
} from '../TextBufferReducer.js';

describe('TextBufferReducer', () => {
  describe('createInitialState', () => {
    it('should create initial state with empty text', () => {
      const state = createInitialState();
      expect(state.lines).toEqual(['']);
      expect(state.cursorRow).toBe(0);
      expect(state.cursorCol).toBe(0);
      expect(state.undoStack).toEqual([]);
      expect(state.redoStack).toEqual([]);
    });

    it('should create initial state with provided text', () => {
      const state = createInitialState('Hello\nWorld');
      expect(state.lines).toEqual(['Hello', 'World']);
      expect(state.cursorRow).toBe(1);
      expect(state.cursorCol).toBe(5); // After "World"
    });
  });

  describe('insert action', () => {
    it('should insert text at cursor position', () => {
      const state = createInitialState('Hello');
      const newState = textBufferReducer(state, {
        type: 'insert',
        payload: ' World',
      });
      
      expect(newState.lines).toEqual(['Hello World']);
      expect(newState.cursorCol).toBe(11); // After "Hello World"
    });

    it('should insert multi-line text', () => {
      const state = createInitialState('Hello');
      const newState = textBufferReducer(state, {
        type: 'insert',
        payload: '\nWorld',
      });
      
      expect(newState.lines).toEqual(['Hello', 'World']);
      expect(newState.cursorRow).toBe(1);
      expect(newState.cursorCol).toBe(5);
    });
  });

  describe('backspace action', () => {
    it('should delete character before cursor', () => {
      const state = createInitialState('Hello');
      const newState = textBufferReducer(state, { type: 'backspace' });
      
      expect(newState.lines).toEqual(['Hell']);
      expect(newState.cursorCol).toBe(4);
    });
  });

  describe('undo/redo', () => {
    it('should undo insert', () => {
      let state = createInitialState('Hello');
      state = textBufferReducer(state, { type: 'insert', payload: ' World' });
      
      expect(state.lines).toEqual(['Hello World']);
      expect(state.undoStack.length).toBeGreaterThan(0);
      
      const undoneState = textBufferReducer(state, { type: 'undo' });
      expect(undoneState.lines).toEqual(['Hello']);
    });

    it('should redo after undo', () => {
      let state = createInitialState('Hello');
      state = textBufferReducer(state, { type: 'insert', payload: ' World' });
      state = textBufferReducer(state, { type: 'undo' });
      
      expect(state.lines).toEqual(['Hello']);
      expect(state.redoStack.length).toBeGreaterThan(0);
      
      const redoneState = textBufferReducer(state, { type: 'redo' });
      expect(redoneState.lines).toEqual(['Hello World']);
    });
  });

  describe('Chinese/CJK text support', () => {
    it('should handle Chinese text insertion', () => {
      const state = createInitialState('');
      const newState = textBufferReducer(state, {
        type: 'insert',
        payload: '你好世界',
      });
      
      expect(newState.lines).toEqual(['你好世界']);
      expect(newState.cursorCol).toBe(4); // 4 characters
    });

    it('should handle mixed language text', () => {
      const state = createInitialState('');
      const newState = textBufferReducer(state, {
        type: 'insert',
        payload: 'Hello 世界 World',
      });
      
      expect(newState.lines).toEqual(['Hello 世界 World']);
    });
  });
});
