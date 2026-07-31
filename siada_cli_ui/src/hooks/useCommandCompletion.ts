/**
 * useCommandCompletion Hook
 * Unified completion orchestrator that coordinates between @ and / completions
 */

import { useMemo } from 'react';
import { useAtCompletion } from './useAtCompletion.js';
import { useSlashCompletion } from './useSlashCompletion.js';
import { usePromptCompletion } from './usePromptCompletion.js';
import { CompletionMode } from '../types/autocomplete.js';
import type { AutoCompleteState } from '../types/autocomplete.js';

export interface UseCommandCompletionOptions {
  /** Current input text */
  inputText: string;
  
  /** Cursor position */
  cursorPosition: number;
  
  /** Current working directory for @ completion */
  cwd: string;
  
  /** Whether autocomplete is enabled */
  enabled?: boolean;
  
  /** MCP resources for @ completion */
  mcpResources?: Array<{
    uri: string;
    name: string;
    description?: string;
    mimeType?: string;
  }>;
  
  /** Debounce delay in ms */
  debounceMs?: number;
  
  /** Loading delay before showing spinner (ms) */
  loadingDelayMs?: number;
  
  /** Recent messages for prompt completion context */
  recentMessages?: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
  
  /** Enable prompt suggestions */
  enablePromptSuggestions?: boolean;
}

export interface UseCommandCompletionReturn extends AutoCompleteState {
  /** Navigate to previous suggestion */
  navigateUp: () => void;
  
  /** Navigate to next suggestion */
  navigateDown: () => void;
  
  /** Accept current suggestion and return completed text */
  acceptSuggestion: () => string | null;
  
  /** Reset autocomplete state */
  reset: () => void;
  
  /** Manually trigger autocomplete */
  trigger: () => void;
  
  /** Current completion mode */
  mode: CompletionMode;
}

/**
 * Unified command completion hook
 * Automatically detects and switches between @, /, and prompt completion modes
 */
export function useCommandCompletion({
  inputText,
  cursorPosition,
  cwd,
  enabled = true,
  mcpResources = [],
  debounceMs = 150,
  loadingDelayMs = 200,
  recentMessages = [],
  enablePromptSuggestions = false,
}: UseCommandCompletionOptions): UseCommandCompletionReturn {
  // Detect completion mode based on input
  const detectedMode = useMemo(() => {
    if (!enabled) return CompletionMode.IDLE;

    const firstLineEnd = inputText.indexOf('\n');
    const firstLine = firstLineEnd === -1 ? inputText : inputText.substring(0, firstLineEnd);
    const cursorLine = inputText.substring(0, cursorPosition).split('\n').length - 1;

    // Priority 1: @ file completion — only when the cursor is currently inside
    // an independent @ token (i.e. @ is at the start of a token: preceded by
    // whitespace or at the beginning of the line, and there's no whitespace
    // between @ and the cursor). This allows "/cmd @xxx" to still trigger
    // file completion even when the line starts with '/'.
    const textBefore = inputText.substring(0, cursorPosition);
    const atPos = textBefore.lastIndexOf('@');
    if (atPos !== -1) {
      const charBeforeAt = atPos === 0 ? '' : textBefore[atPos - 1];
      const isAtTokenStart = atPos === 0 || /\s/.test(charBeforeAt ?? '');
      // Ensure no whitespace between @ and cursor (cursor is within the @ token)
      const afterAt = textBefore.substring(atPos + 1);
      const cursorInAtToken = !/\s/.test(afterAt);
      if (isAtTokenStart && cursorInAtToken) {
        return CompletionMode.AT;
      }
    }

    // Priority 2: slash command (must be at start of first line, cursor on line 0,
    // and command name must only contain [a-zA-Z0-9:_-] to exclude file paths)
    if (firstLine.startsWith('/') && cursorLine === 0) {
      const slashInput = firstLine.substring(1);
      const commandName = slashInput.split(' ')[0];
      if (/^[a-zA-Z0-9:_-]*$/.test(commandName)) {
        return CompletionMode.SLASH;
      }
    }
    
    // Check for prompt suggestions (plain text, no / or @)
    if (enablePromptSuggestions && 
        !firstLine.startsWith('/') && 
        !inputText.includes('@') &&
        inputText.trim().length >= 2) {
      return CompletionMode.PROMPT;
    }
    
    return CompletionMode.IDLE;
  }, [inputText, cursorPosition, enabled, enablePromptSuggestions]);

  // Initialize all completion hooks
  const atCompletion = useAtCompletion({
    inputText,
    cursorPosition,
    cwd,
    enabled: enabled && detectedMode === CompletionMode.AT,
    mcpResources,
    debounceMs,
    loadingDelayMs,
  });

  const slashCompletion = useSlashCompletion({
    inputText,
    cursorPosition,
    enabled: enabled && detectedMode === CompletionMode.SLASH,
    debounceMs,
  });

  const promptCompletion = usePromptCompletion({
    inputText,
    cursorPosition,
    enabled: enabled && detectedMode === CompletionMode.PROMPT,
    debounceMs,
    recentMessages,
    cwd,
  });

  // Return the active completion based on detected mode
  if (detectedMode === CompletionMode.AT) {
    return {
      ...atCompletion,
      mode: CompletionMode.AT
    };
  } else if (detectedMode === CompletionMode.SLASH) {
    return {
      ...slashCompletion,
      mode: CompletionMode.SLASH
    };
  } else if (detectedMode === CompletionMode.PROMPT) {
    return {
      ...promptCompletion,
      mode: CompletionMode.PROMPT
    };
  } else {
    // IDLE mode - return empty state
    return {
      suggestions: [],
      activeIndex: -1,
      visibleStartIndex: 0,
      isLoading: false,
      showSuggestions: false,
      pattern: '',
      mode: CompletionMode.IDLE,
      isPerfectMatch: false,
      navigateUp: () => {},
      navigateDown: () => {},
      acceptSuggestion: () => null,
      reset: () => {},
      trigger: () => {},
    };
  }
}
