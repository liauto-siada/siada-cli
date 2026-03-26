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
    
    // Check for slash command (must be at start of first line)
    const firstLineEnd = inputText.indexOf('\n');
    const firstLine = firstLineEnd === -1 ? inputText : inputText.substring(0, firstLineEnd);
    const cursorLine = inputText.substring(0, cursorPosition).split('\n').length - 1;
    
    if (firstLine.startsWith('/') && cursorLine === 0) {
      return CompletionMode.SLASH;
    }
    
    // Check for @ file completion (anywhere in the text)
    const textBefore = inputText.substring(0, cursorPosition);
    const atPos = textBefore.lastIndexOf('@');
    
    if (atPos !== -1) {
      return CompletionMode.AT;
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
