/**
 * useSlashCompletion Hook
 * Provides / slash command autocomplete with fuzzy search
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Fzf } from 'fzf';
import { slashCommandService } from '../services/slashCommandService.js';
import { checkpointService } from '../services/checkpointService.js';
import { CompletionMode } from '../types/autocomplete.js';
import type { Suggestion, AutoCompleteState, CommandDefinition } from '../types/autocomplete.js';
import { logger } from '../utils/logger.js';

export interface UseSlashCompletionOptions {
  /** Current input text */
  inputText: string;
  
  /** Cursor position */
  cursorPosition: number;
  
  /** Whether autocomplete is enabled */
  enabled?: boolean;
  
  /** Debounce delay in ms */
  debounceMs?: number;
}

export interface UseSlashCompletionReturn extends AutoCompleteState {
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
 * Hook for slash command completion with fuzzy search
 */
export function useSlashCompletion({
  inputText,
  cursorPosition,
  enabled = true,
  debounceMs = 50,
}: UseSlashCompletionOptions): UseSlashCompletionReturn {
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

  const commandsRef = useRef<CommandDefinition[]>([]);
  const fzfRef = useRef<Fzf<CommandDefinition[]> | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Initialize commands and fzf
  useEffect(() => {
    const initCommands = async () => {
      const commands = await slashCommandService.getCommands();
      commandsRef.current = commands;
      
      // Create fzf instance
      fzfRef.current = new Fzf(commands, {
        selector: (cmd) => cmd.name,
        casing: 'case-insensitive',
      });
      
      logger.debug('[SlashCompletion] Commands initialized', {
        count: commands.length,
        commands: commands.map(c => c.name)
      });
    };
    
    initCommands();
  }, []);

  // Detect / at start of first line and trigger autocomplete
  useEffect(() => {
    if (!enabled || !fzfRef.current) {
      return;
    }

    // Clear previous timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Get first line only (slash commands must be at line start)
    const firstLineEnd = inputText.indexOf('\n');
    const firstLine = firstLineEnd === -1 ? inputText : inputText.substring(0, firstLineEnd);
    
    // Check if starts with /
    if (!firstLine.startsWith('/')) {
      setState(prev => ({
        ...prev,
        showSuggestions: false,
        mode: CompletionMode.IDLE
      }));
      return;
    }

    // Check if cursor is on first line
    const cursorLine = inputText.substring(0, cursorPosition).split('\n').length - 1;
    if (cursorLine !== 0) {
      setState(prev => ({
        ...prev,
        showSuggestions: false
      }));
      return;
    }

    // Extract pattern (from / to cursor or space)
    const textBeforeCursor = firstLine.substring(0, Math.min(cursorPosition, firstLine.length));
    const pattern = textBeforeCursor; // e.g., "/hel", "/rule-", "/status"
    
    logger.debug('[SlashCompletion] Pattern detected', {
      pattern,
      firstLine,
      cursorPosition
    });

    // Check if there's text after cursor without space (editing in middle)
    const textAfterCursor = firstLine.substring(Math.min(cursorPosition, firstLine.length));
    if (textAfterCursor.length > 0 && !textAfterCursor.startsWith(' ')) {
      setState(prev => ({
        ...prev,
        showSuggestions: false
      }));
      return;
    }

    // Debounce the search
    debounceTimerRef.current = setTimeout(() => {
      // Check if we're completing command arguments (checkpoint files)
      const spaceIndex = pattern.indexOf(' ');
      if (spaceIndex > 0) {
        // We have a space, check if it's a checkpoint command
        const commandName = pattern.substring(1, spaceIndex); // e.g., "compare", "undo", "restore"
        const checkpointCommands = ['compare', 'undo', 'restore'];
        
        if (checkpointCommands.includes(commandName)) {
          // Get the argument query (text after space)
          const argQuery = pattern.substring(spaceIndex + 1);
          
          logger.debug('[SlashCompletion] Checkpoint argument completion', {
            command: commandName,
            argQuery
          });
          
          // Get checkpoints from service
          const checkpoints = checkpointService.searchCheckpoints(argQuery);
          
          // Convert to suggestions
          const suggestions: Suggestion[] = checkpoints.map(cp => ({
            label: cp.file_name,
            value: cp.file_name,
            description: `${cp.tool} - ${cp.timestamp}`,
            type: 'file' as const,
            icon: '📦',
            positions: [],
            score: 0,
          }));
          
          logger.debug('[SlashCompletion] Checkpoint suggestions', {
            count: suggestions.length,
            topResults: suggestions.slice(0, 3).map(s => s.label)
          });
          
          setState(prev => ({
            ...prev,
            suggestions,
            isLoading: false,
            showSuggestions: suggestions.length > 0,
            activeIndex: suggestions.length > 0 ? 0 : -1,
            pattern,
            mode: CompletionMode.SLASH,
            isPerfectMatch: false
          }));
          
          return;
        }
      }
      
      // Normal command completion
      const query = pattern.substring(1); // Remove leading /
      
      logger.debug('[SlashCompletion] Searching', { query });
      
      // Use fzf for fuzzy search
      const results = fzfRef.current!.find(query);
      
      // Convert to suggestions
      const suggestions: Suggestion[] = results.map(result => ({
        label: result.item.name,
        value: result.item.name,
        description: result.item.description,
        type: 'command' as const,
        icon: '',
        positions: Array.from(result.positions),
        score: result.score,
        commandKind: result.item.kind,
      }));

      // Check for perfect match
      const perfectMatch = suggestions.some(s => 
        s.label.toLowerCase() === query.toLowerCase()
      );

      logger.debug('[SlashCompletion] Search completed', {
        query,
        resultCount: suggestions.length,
        perfectMatch,
        topResults: suggestions.slice(0, 3).map(s => s.label)
      });

      setState(prev => ({
        ...prev,
        suggestions,
        isLoading: false,
        showSuggestions: suggestions.length > 0,
        activeIndex: suggestions.length > 0 ? 0 : -1,
        pattern,
        mode: CompletionMode.SLASH,
        isPerfectMatch: perfectMatch
      }));
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [inputText, cursorPosition, enabled, debounceMs]);

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
    
    // Get first line
    const firstLineEnd = inputText.indexOf('\n');
    const firstLine = firstLineEnd === -1 ? inputText : inputText.substring(0, firstLineEnd);
    const restOfText = firstLineEnd === -1 ? '' : inputText.substring(firstLineEnd);
    
    // Check if we're completing a checkpoint argument
    const spaceIndex = state.pattern.indexOf(' ');
    let completed: string;
    
    if (spaceIndex > 0 && suggestion.type === 'file') {
      // Completing checkpoint argument - replace the argument part
      const commandPart = state.pattern.substring(0, spaceIndex + 1); // e.g., "/compare "
      completed = `${commandPart}${suggestion.value}${restOfText}`;
    } else {
      // Completing command name - add space after command
      completed = `/${suggestion.value} ${restOfText}`;
    }
    
    // Reset suggestions after completion
    setState(prev => ({
      ...prev,
      showSuggestions: false,
      activeIndex: -1
    }));
    
    logger.debug('[SlashCompletion] Suggestion accepted', {
      suggestion: suggestion.label,
      suggestionType: suggestion.type,
      completed: completed.substring(0, 50)
    });
    
    return completed;
  }, [state.activeIndex, state.suggestions, state.pattern, inputText]);

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
    if (!enabled || !fzfRef.current) {
      return;
    }

    const firstLineEnd = inputText.indexOf('\n');
    const firstLine = firstLineEnd === -1 ? inputText : inputText.substring(0, firstLineEnd);
    
    if (firstLine.startsWith('/')) {
      const pattern = firstLine.substring(0, Math.min(cursorPosition, firstLine.length));
      const query = pattern.substring(1);
      
      const results = fzfRef.current.find(query);
      const suggestions: Suggestion[] = results.map(result => ({
        label: result.item.name,
        value: result.item.name,
        description: result.item.description,
        type: 'command' as const,
        icon: '/',
        positions: Array.from(result.positions),
        score: result.score,
        commandKind: result.item.kind,
      }));

      setState(prev => ({
        ...prev,
        suggestions,
        isLoading: false,
        showSuggestions: suggestions.length > 0,
        activeIndex: suggestions.length > 0 ? 0 : -1,
        pattern,
        mode: CompletionMode.SLASH
      }));
    }
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
