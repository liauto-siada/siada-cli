/**
 * usePromptCompletion Hook
 * Provides intelligent prompt suggestions based on context
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { CompletionMode } from '../types/autocomplete.js';
import type { Suggestion, AutoCompleteState } from '../types/autocomplete.js';
import { logger } from '../utils/logger.js';

export interface UsePromptCompletionOptions {
  /** Current input text */
  inputText: string;
  
  /** Cursor position */
  cursorPosition: number;
  
  /** Whether autocomplete is enabled */
  enabled?: boolean;
  
  /** Minimum characters before showing suggestions */
  minChars?: number;
  
  /** Debounce delay in ms */
  debounceMs?: number;
  
  /** Recent messages for context */
  recentMessages?: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
  
  /** Current working directory */
  cwd?: string;
}

export interface UsePromptCompletionReturn extends AutoCompleteState {
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
}

/**
 * Prompt completion templates based on common patterns
 */
const PROMPT_TEMPLATES: Array<{
  trigger: string;
  label: string;
  value: string;
  description: string;
  category: string;
}> = [
  // Code-related prompts
  {
    trigger: 'fix',
    label: 'Fix the bug',
    value: 'Fix the bug in ',
    description: 'Ask to fix a specific bug',
    category: 'Code'
  },
  {
    trigger: 'explain',
    label: 'Explain this code',
    value: 'Explain how this code works: ',
    description: 'Request code explanation',
    category: 'Code'
  },
  {
    trigger: 'refactor',
    label: 'Refactor this',
    value: 'Refactor this code to be more ',
    description: 'Request code refactoring',
    category: 'Code'
  },
  {
    trigger: 'optimize',
    label: 'Optimize performance',
    value: 'Optimize the performance of ',
    description: 'Request performance optimization',
    category: 'Code'
  },
  {
    trigger: 'test',
    label: 'Write tests',
    value: 'Write unit tests for ',
    description: 'Request test writing',
    category: 'Code'
  },
  {
    trigger: 'document',
    label: 'Add documentation',
    value: 'Add documentation for ',
    description: 'Request documentation',
    category: 'Code'
  },
  
  // Review prompts
  {
    trigger: 'review',
    label: 'Review this code',
    value: 'Review this code and suggest improvements: ',
    description: 'Request code review',
    category: 'Review'
  },
  {
    trigger: 'security',
    label: 'Security review',
    value: 'Review this code for security vulnerabilities: ',
    description: 'Request security review',
    category: 'Review'
  },
  
  // Implementation prompts
  {
    trigger: 'implement',
    label: 'Implement feature',
    value: 'Implement a feature that ',
    description: 'Request feature implementation',
    category: 'Implementation'
  },
  {
    trigger: 'create',
    label: 'Create component',
    value: 'Create a component that ',
    description: 'Request component creation',
    category: 'Implementation'
  },
  {
    trigger: 'add',
    label: 'Add functionality',
    value: 'Add functionality to ',
    description: 'Request adding functionality',
    category: 'Implementation'
  },
  
  // Debug prompts
  {
    trigger: 'debug',
    label: 'Debug this issue',
    value: 'Help me debug this issue: ',
    description: 'Request debugging help',
    category: 'Debug'
  },
  {
    trigger: 'error',
    label: 'Fix this error',
    value: 'Help me fix this error: ',
    description: 'Request error fixing',
    category: 'Debug'
  },
  {
    trigger: 'why',
    label: 'Why is this happening',
    value: 'Why is this happening: ',
    description: 'Ask for explanation',
    category: 'Debug'
  },
  
  // Question prompts
  {
    trigger: 'how',
    label: 'How do I',
    value: 'How do I ',
    description: 'Ask how to do something',
    category: 'Question'
  },
  {
    trigger: 'what',
    label: 'What is',
    value: 'What is ',
    description: 'Ask what something is',
    category: 'Question'
  },
  {
    trigger: 'show',
    label: 'Show me',
    value: 'Show me how to ',
    description: 'Request demonstration',
    category: 'Question'
  },
  
  // Conversion prompts
  {
    trigger: 'convert',
    label: 'Convert to',
    value: 'Convert this code to ',
    description: 'Request code conversion',
    category: 'Conversion'
  },
  {
    trigger: 'translate',
    label: 'Translate to',
    value: 'Translate this code to ',
    description: 'Request code translation',
    category: 'Conversion'
  },
  
  // Task prompts
  {
    trigger: 'help',
    label: 'Help me with',
    value: 'Help me with ',
    description: 'Request general help',
    category: 'Task'
  },
  {
    trigger: 'improve',
    label: 'Improve this',
    value: 'Improve this code by ',
    description: 'Request improvements',
    category: 'Task'
  },
];

/**
 * Hook for intelligent prompt completion
 */
export function usePromptCompletion({
  inputText,
  cursorPosition,
  enabled = true,
  minChars = 2,
  debounceMs = 300,
  recentMessages = [],
  cwd = process.cwd(),
}: UsePromptCompletionOptions): UsePromptCompletionReturn {
  const [state, setState] = useState<AutoCompleteState>({
    suggestions: [],
    activeIndex: -1,
    visibleStartIndex: 0,
    isLoading: false,
    showSuggestions: false,
    pattern: '',
    mode: CompletionMode.IDLE,
    isPerfectMatch: false
  });

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Detect plain text input (not @ or /) and trigger prompt suggestions
  useEffect(() => {
    if (!enabled) {
      return;
    }

    // Clear previous timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Get first line
    const firstLineEnd = inputText.indexOf('\n');
    const firstLine = firstLineEnd === -1 ? inputText : inputText.substring(0, firstLineEnd);
    
    // Don't trigger if:
    // 1. Starts with / (slash command)
    // 2. Contains @ (file reference)
    // 3. Too short
    if (
      firstLine.startsWith('/') ||
      inputText.includes('@') ||
      inputText.length < minChars
    ) {
      setState(prev => ({
        ...prev,
        showSuggestions: false,
        mode: CompletionMode.IDLE
      }));
      return;
    }

    // Get text before cursor
    const textBefore = inputText.substring(0, cursorPosition).toLowerCase().trim();
    
    // Don't show if there's already a lot of text (user is typing freely)
    if (textBefore.length > 50) {
      setState(prev => ({
        ...prev,
        showSuggestions: false
      }));
      return;
    }

    logger.debug('[PromptCompletion] Analyzing input', {
      textBefore: textBefore.substring(0, 30),
      length: textBefore.length
    });

    // Debounce the search
    debounceTimerRef.current = setTimeout(() => {
      // Filter templates based on input
      const matchedTemplates = PROMPT_TEMPLATES.filter(template => {
        // Match by trigger word
        if (textBefore.includes(template.trigger)) {
          return true;
        }
        
        // Fuzzy match on label
        const words = textBefore.split(/\s+/);
        return words.some(word => 
          template.label.toLowerCase().includes(word) ||
          template.trigger.includes(word)
        );
      });

      // If no matches, show popular templates
      const suggestions: Suggestion[] = (
        matchedTemplates.length > 0 
          ? matchedTemplates 
          : PROMPT_TEMPLATES.slice(0, 8)
      ).map(template => ({
        label: template.label,
        value: template.value,
        description: template.description,
        type: 'prompt' as const,
        icon: '💡',
        category: template.category,
      }));

      logger.debug('[PromptCompletion] Suggestions generated', {
        count: suggestions.length,
        matched: matchedTemplates.length > 0,
        topSuggestions: suggestions.slice(0, 3).map(s => s.label)
      });

      setState(prev => ({
        ...prev,
        suggestions,
        isLoading: false,
        showSuggestions: suggestions.length > 0,
        activeIndex: suggestions.length > 0 ? 0 : -1,
        pattern: textBefore,
        mode: CompletionMode.PROMPT,
        isPerfectMatch: false
      }));
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [inputText, cursorPosition, enabled, minChars, debounceMs]);

  // Navigate up (previous suggestion)
  const navigateUp = useCallback(() => {
    setState(prev => {
      if (prev.suggestions.length === 0) return prev;
      
      const newIndex = prev.activeIndex <= 0 
        ? prev.suggestions.length - 1 
        : prev.activeIndex - 1;
      
      // Update visible start index for scrolling
      const maxVisible = 8;
      let newVisibleStart = prev.visibleStartIndex;
      
      if (newIndex < newVisibleStart) {
        newVisibleStart = newIndex;
      } else if (newIndex >= newVisibleStart + maxVisible) {
        newVisibleStart = newIndex - maxVisible + 1;
      }
      
      return {
        ...prev,
        activeIndex: newIndex,
        visibleStartIndex: newVisibleStart
      };
    });
  }, []);

  // Navigate down (next suggestion)
  const navigateDown = useCallback(() => {
    setState(prev => {
      if (prev.suggestions.length === 0) return prev;
      
      const newIndex = prev.activeIndex >= prev.suggestions.length - 1 
        ? 0 
        : prev.activeIndex + 1;
      
      // Update visible start index for scrolling
      const maxVisible = 8;
      let newVisibleStart = prev.visibleStartIndex;
      
      if (newIndex < newVisibleStart) {
        newVisibleStart = newIndex;
      } else if (newIndex >= newVisibleStart + maxVisible) {
        newVisibleStart = newIndex - maxVisible + 1;
      }
      
      return {
        ...prev,
        activeIndex: newIndex,
        visibleStartIndex: newVisibleStart
      };
    });
  }, []);

  // Accept suggestion
  const acceptSuggestion = useCallback(() => {
    if (state.activeIndex < 0 || state.activeIndex >= state.suggestions.length) {
      return null;
    }

    const suggestion = state.suggestions[state.activeIndex];
    
    // Replace current text with suggestion
    const completed = suggestion.value;
    
    // Reset suggestions after completion
    setState(prev => ({
      ...prev,
      showSuggestions: false,
      activeIndex: -1
    }));
    
    logger.debug('[PromptCompletion] Suggestion accepted', {
      suggestion: suggestion.label,
      value: suggestion.value
    });
    
    return completed;
  }, [state.activeIndex, state.suggestions]);

  // Reset autocomplete state
  const reset = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    
    setState({
      suggestions: [],
      activeIndex: -1,
      visibleStartIndex: 0,
      isLoading: false,
      showSuggestions: false,
      pattern: '',
      mode: CompletionMode.IDLE,
      isPerfectMatch: false
    });
  }, []);

  // Manually trigger autocomplete
  const trigger = useCallback(() => {
    if (!enabled) {
      return;
    }

    const textBefore = inputText.substring(0, cursorPosition).toLowerCase().trim();
    
    // Show all popular templates
    const suggestions: Suggestion[] = PROMPT_TEMPLATES.slice(0, 10).map(template => ({
      label: template.label,
      value: template.value,
      description: template.description,
      type: 'prompt' as const,
      icon: '💡',
      category: template.category,
    }));

    setState(prev => ({
      ...prev,
      suggestions,
      isLoading: false,
      showSuggestions: suggestions.length > 0,
      activeIndex: suggestions.length > 0 ? 0 : -1,
      pattern: textBefore,
      mode: CompletionMode.PROMPT
    }));
  }, [inputText, cursorPosition, enabled]);

  return {
    ...state,
    navigateUp,
    navigateDown,
    acceptSuggestion,
    reset,
    trigger
  };
}
