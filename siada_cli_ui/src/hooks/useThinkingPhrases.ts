/**
 * Hook for cycling through thinking/loading phrases
 */

import { useState, useEffect, useRef } from 'react';
import { 
  THINKING_PHRASES, 
  WITTY_PHRASES, 
  PHRASE_CHANGE_INTERVAL 
} from '../constants/phrases.js';

export interface UseThinkingPhrasesOptions {
  /** Whether phrase cycling is active */
  isActive: boolean;
  /** Custom phrases to use instead of defaults */
  customPhrases?: string[];
}

/**
 * Custom hook to manage cycling through thinking/loading phrases
 * @returns The current phrase to display
 */
export function useThinkingPhrases({
  isActive,
  customPhrases,
}: UseThinkingPhrasesOptions): string {
  // Use ref to store phrase pool to avoid recreating on each render
  const phrasePoolRef = useRef<string[]>(
    customPhrases && customPhrases.length > 0
      ? customPhrases
      : [...THINKING_PHRASES, ...WITTY_PHRASES]
  );

  const [currentPhrase, setCurrentPhrase] = useState(phrasePoolRef.current[0]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Update phrase pool if customPhrases changes
    if (customPhrases && customPhrases.length > 0) {
      phrasePoolRef.current = customPhrases;
    } else {
      phrasePoolRef.current = [...THINKING_PHRASES, ...WITTY_PHRASES];
    }
  }, [customPhrases]);

  useEffect(() => {
    // Clear existing interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!isActive) {
      setCurrentPhrase(phrasePoolRef.current[0]);
      return;
    }

    const selectRandomPhrase = () => {
      const pool = customPhrases && customPhrases.length > 0
        ? customPhrases
        : phrasePoolRef.current;
      const randomIndex = Math.floor(Math.random() * pool.length);
      setCurrentPhrase(pool[randomIndex]);
    };

    // Set initial random phrase
    selectRandomPhrase();

    // Start interval for phrase rotation
    intervalRef.current = setInterval(selectRandomPhrase, PHRASE_CHANGE_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isActive, customPhrases]);

  return currentPhrase;
}
