/**
 * useAtCompletion Hook
 * Provides @ file path autocomplete functionality with MCP resource support
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { FileSearchService } from '../services/fileSearch.js';
import { CompletionMode } from '../types/autocomplete.js';
import type { Suggestion, AutoCompleteState } from '../types/autocomplete.js';
import { logger } from '../utils/logger.js';

export interface UseAtCompletionOptions {
  /** Current input text */
  inputText: string;
  
  /** Cursor position */
  cursorPosition: number;
  
  /** Current working directory */
  cwd: string;
  
  /** Whether autocomplete is enabled */
  enabled?: boolean;
  
  /** Debounce delay in ms */
  debounceMs?: number;
  
  /** Loading delay before showing spinner (ms) */
  loadingDelayMs?: number;
  
  /** MCP resources (if available) */
  mcpResources?: Array<{
    uri: string;
    name: string;
    mimeType?: string;
    description?: string;
  }>;
}

export interface UseAtCompletionResult extends AutoCompleteState {
  /** Navigate to previous suggestion */
  navigateUp: () => void;
  
  /** Navigate to next suggestion */
  navigateDown: () => void;
  
  /** Accept current suggestion */
  acceptSuggestion: () => string | null;
  
  /** Reset autocomplete state */
  reset: () => void;
  
  /** Manually trigger autocomplete */
  trigger: () => void;
}

// Cache for file search results with TTL
interface CacheEntry {
  suggestions: Suggestion[];
  timestamp: number;
}

const searchCache = new Map<string, CacheEntry>();
const CACHE_TTL_MS = 30000; // 30 seconds

export function useAtCompletion({
  inputText,
  cursorPosition,
  cwd,
  enabled = true,
  debounceMs = 500,  // Increased to 500ms to avoid blocking with sync I/O
  loadingDelayMs = 200,
  mcpResources = []
}: UseAtCompletionOptions): UseAtCompletionResult {
  const [state, setState] = useState<AutoCompleteState>({
    suggestions: [],
    activeIndex: -1,
    isLoading: false,
    showSuggestions: false,
    pattern: '',
    mode: CompletionMode.IDLE,
    visibleStartIndex: 0,
    isPerfectMatch: false
  });

  const fileSearchRef = useRef<FileSearchService | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const loadingDelayTimerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Stabilize mcpResources to prevent infinite loops
  // Use JSON.stringify to create a stable key for comparison
  const mcpResourcesKey = useMemo(
    () => JSON.stringify(mcpResources?.map(r => r.uri) || []),
    [mcpResources]
  );

  // Initialize file search service
  useEffect(() => {
    fileSearchRef.current = new FileSearchService(cwd, {
      maxResults: 20,
      maxDepth: 10,  // Increased to 10 for deeper monorepo structures
      respectGitIgnore: true
    });
  }, [cwd]);

  // Helper function to get MCP resource suggestions
  // Note: We inline this in useEffect to avoid dependency issues
  const getMcpResourceSuggestions = (searchPattern: string, resources: typeof mcpResources): Suggestion[] => {
    if (!resources || resources.length === 0) {
      return [];
    }

    const query = searchPattern.replace('@', '').toLowerCase();
    
    return resources
      .filter(resource => {
        const name = resource.name.toLowerCase();
        const uri = resource.uri.toLowerCase();
        return query === '' || name.includes(query) || uri.includes(query);
      })
      .map(resource => ({
        label: resource.name,
        value: resource.uri,
        description: resource.description || resource.mimeType || 'MCP Resource',
        type: 'resource' as const,
        icon: ''
      }))
      .slice(0, 10); // Limit MCP resources to 10
  };

  // Detect @ symbol and trigger autocomplete
  useEffect(() => {
    // Only log when enabled to avoid unnecessary overhead
    if (!enabled || !fileSearchRef.current) {
      return;
    }

    logger.debug('[@Completion] useEffect triggered', {
      component: 'useAtCompletion',
      inputText: inputText.substring(0, 50),
      cursorPosition,
      hasFileSearch: !!fileSearchRef.current
    });

    // Clear previous timers
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (loadingDelayTimerRef.current) {
      clearTimeout(loadingDelayTimerRef.current);
    }
    // Abort previous search
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const textBefore = inputText.substring(0, cursorPosition);
    const atPos = textBefore.lastIndexOf('@');

    logger.debug('[@Completion] Checking @ position', {
      component: 'useAtCompletion',
      textBefore: textBefore.substring(Math.max(0, textBefore.length - 30)),
      atPos,
      cursorPosition
    });

    // No @ symbol found
    if (atPos === -1) {
      logger.debug('[@Completion] No @ symbol found', {
        component: 'useAtCompletion'
      });
      setState(prev => ({
        ...prev,
        showSuggestions: false,
        mode: CompletionMode.IDLE
      }));
      return;
    }

    const pattern = textBefore.substring(atPos);
    const textAfter = inputText.substring(cursorPosition);
    
    logger.debug('[@Completion] Pattern extracted', {
      component: 'useAtCompletion',
      pattern,
      atPos,
      textAfter: textAfter.substring(0, 20)
    });
    
    // If pattern contains space after @, stop searching
    // e.g., "@file.txt " - user has completed the file selection
    if (pattern.includes(' ')) {
      setState(prev => ({
        ...prev,
        showSuggestions: false,
        mode: CompletionMode.IDLE
      }));
      return;
    }
    
    // Check if cursor is in the middle of an @ command
    const spaceAfter = textAfter.indexOf(' ');
    const atAfter = textAfter.indexOf('@');
    
    // If there's text after cursor without space, we're in the middle
    if (textAfter.length > 0 && spaceAfter !== 0 && (spaceAfter > 0 || atAfter < 0)) {
      // User is editing in the middle, don't show suggestions
      setState(prev => ({
        ...prev,
        showSuggestions: false
      }));
      return;
    }

    // Check cache first
    const cacheKey = `${cwd}:${pattern}`;
    const cached = searchCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      // Merge with MCP resources
      const mcpSuggestions = getMcpResourceSuggestions(pattern, mcpResources);
      const allSuggestions = [...mcpSuggestions, ...cached.suggestions];
      
      setState(prev => ({
        ...prev,
        suggestions: allSuggestions,
        isLoading: false,
        showSuggestions: allSuggestions.length > 0,
        activeIndex: allSuggestions.length > 0 ? 0 : -1,
        pattern,
        mode: CompletionMode.AT
      }));
      return;
    }

    // Debounce the search
    debounceTimerRef.current = setTimeout(async () => {
      logger.debug('[@Completion] Starting file search', {
        component: 'useAtCompletion',
        pattern,
        cwd
      });

      // Start loading indicator after delay to avoid flicker
      loadingDelayTimerRef.current = setTimeout(() => {
        setState(prev => ({
          ...prev,
          isLoading: true
        }));
      }, loadingDelayMs);

      setState(prev => ({
        ...prev,
        pattern,
        mode: CompletionMode.AT
      }));

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const fileSuggestions = await fileSearchRef.current!.search(pattern);
        
        logger.debug('[@Completion] File search completed', {
          component: 'useAtCompletion',
          pattern,
          resultCount: fileSuggestions.length,
          firstFew: fileSuggestions.slice(0, 3).map(s => s.label)
        });
        
        // Don't update if aborted
        if (controller.signal.aborted) {
          return;
        }

        // Merge file suggestions with MCP resources
        const mcpSuggestions = getMcpResourceSuggestions(pattern, mcpResources);
        const allSuggestions = [...mcpSuggestions, ...fileSuggestions];

        // Cache file results
        searchCache.set(cacheKey, {
          suggestions: fileSuggestions,
          timestamp: Date.now()
        });

        // Clear loading delay timer
        if (loadingDelayTimerRef.current) {
          clearTimeout(loadingDelayTimerRef.current);
        }

        setState(prev => ({
          ...prev,
          suggestions: allSuggestions,
          isLoading: false,
          showSuggestions: allSuggestions.length > 0,
          activeIndex: allSuggestions.length > 0 ? 0 : -1
        }));
      } catch (error) {
        // Clear loading delay timer
        if (loadingDelayTimerRef.current) {
          clearTimeout(loadingDelayTimerRef.current);
        }
        
        // Error is silently handled by resetting state
        setState(prev => ({
          ...prev,
          isLoading: false,
          showSuggestions: false,
          suggestions: []
        }));
      }
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (loadingDelayTimerRef.current) {
        clearTimeout(loadingDelayTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputText, cursorPosition, cwd, enabled, debounceMs, loadingDelayMs, mcpResourcesKey]);

  // Navigate up (previous suggestion)
  const navigateUp = useCallback(() => {
    setState(prev => {
      if (prev.suggestions.length === 0) return prev;
      
      const newIndex = prev.activeIndex <= 0
        ? prev.suggestions.length - 1
        : prev.activeIndex - 1;
      
      // Adjust visible window for scrolling
      const MAX_VISIBLE = 8;
      let newVisibleStart = prev.visibleStartIndex;
      if (newIndex < newVisibleStart) {
        newVisibleStart = newIndex;
      } else if (newIndex >= newVisibleStart + MAX_VISIBLE) {
        newVisibleStart = Math.max(0, newIndex - MAX_VISIBLE + 1);
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
      
      // Adjust visible window for scrolling
      const MAX_VISIBLE = 8;
      let newVisibleStart = prev.visibleStartIndex;
      if (newIndex < newVisibleStart) {
        newVisibleStart = 0;
      } else if (newIndex >= newVisibleStart + MAX_VISIBLE) {
        newVisibleStart = Math.min(
          prev.suggestions.length - MAX_VISIBLE,
          newIndex - MAX_VISIBLE + 1
        );
      }
      
      return {
        ...prev,
        activeIndex: newIndex,
        visibleStartIndex: newVisibleStart
      };
    });
  }, []);

  // Accept current suggestion
  const acceptSuggestion = useCallback((): string | null => {
    if (state.activeIndex < 0 || state.activeIndex >= state.suggestions.length) {
      return null;
    }

    const suggestion = state.suggestions[state.activeIndex];
    
    // Find @ position
    const textBefore = inputText.substring(0, cursorPosition);
    const atPos = textBefore.lastIndexOf('@');
    
    if (atPos === -1) {
      return null;
    }

    // Replace from @ to cursor with completed value
    const before = inputText.substring(0, atPos);
    const after = inputText.substring(cursorPosition);
    
    // Add space after completion for better UX
    const completed = `${before}@${suggestion.value} ${after}`;
    
    // Reset suggestions after completion
    setState(prev => ({
      ...prev,
      showSuggestions: false,
      activeIndex: -1
    }));
    
    return completed;
  }, [state.activeIndex, state.suggestions, inputText, cursorPosition]);

  // Reset autocomplete state
  const reset = useCallback(() => {
    // Clear timers
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (loadingDelayTimerRef.current) {
      clearTimeout(loadingDelayTimerRef.current);
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    setState({
      suggestions: [],
      activeIndex: -1,
      isLoading: false,
      showSuggestions: false,
      pattern: '',
      mode: CompletionMode.IDLE,
      visibleStartIndex: 0,
      isPerfectMatch: false
    });
  }, []);

  // Manually trigger autocomplete
  const trigger = useCallback(() => {
    if (!enabled || !fileSearchRef.current) {
      return;
    }

    const textBefore = inputText.substring(0, cursorPosition);
    const atPos = textBefore.lastIndexOf('@');
    
    if (atPos !== -1) {
      const pattern = textBefore.substring(atPos);
      
      setState(prev => ({ ...prev, isLoading: true, pattern }));
      
      fileSearchRef.current.search(pattern).then(fileSuggestions => {
        const mcpSuggestions = getMcpResourceSuggestions(pattern, mcpResources);
        const allSuggestions = [...mcpSuggestions, ...fileSuggestions];
        
        setState(prev => ({
          ...prev,
          suggestions: allSuggestions,
          isLoading: false,
          showSuggestions: allSuggestions.length > 0,
          activeIndex: allSuggestions.length > 0 ? 0 : -1,
          mode: CompletionMode.AT
        }));
      });
    }
  }, [inputText, cursorPosition, enabled, mcpResources]);

  return {
    ...state,
    navigateUp,
    navigateDown,
    acceptSuggestion,
    reset,
    trigger
  };
}
