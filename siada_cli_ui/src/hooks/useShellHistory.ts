/**
 * Shell History Hook
 * Manages shell command history with persistent storage
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { ShellHistoryEntry, ShellHistoryOptions } from '../types/shell.js';
import { logger } from '../utils/logger.js';

/**
 * Default history options
 */
const DEFAULT_OPTIONS: ShellHistoryOptions = {
  maxEntries: 100,
  autoSave: true,
};

/**
 * Get default history file path
 */
function getDefaultHistoryPath(): string {
  const siadaDir = path.join(os.homedir(), '.siada');
  
  // Ensure directory exists
  if (!fs.existsSync(siadaDir)) {
    fs.mkdirSync(siadaDir, { recursive: true });
  }
  
  return path.join(siadaDir, 'shell_history');
}

/**
 * Load history from file
 */
function loadHistory(filePath: string): ShellHistoryEntry[] {
  try {
    if (!fs.existsSync(filePath)) {
      return [];
    }
    
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n').filter(line => line.trim());
    
    return lines.map(line => {
      try {
        return JSON.parse(line) as ShellHistoryEntry;
      } catch {
        // Legacy format: plain command text
        return {
          command: line,
          timestamp: Date.now(),
          cwd: process.cwd(),
        };
      }
    });
  } catch (error) {
    logger.error('Failed to load shell history', {
      component: 'useShellHistory',
      operation: 'load',
      error,
    });
    return [];
  }
}

/**
 * Save history to file
 */
function saveHistory(filePath: string, entries: ShellHistoryEntry[]): void {
  try {
    const lines = entries.map(entry => JSON.stringify(entry));
    fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf8');
    
    logger.debug('Shell history saved', {
      component: 'useShellHistory',
      operation: 'save',
      count: entries.length,
    });
  } catch (error) {
    logger.error('Failed to save shell history', {
      component: 'useShellHistory',
      operation: 'save',
      error,
    });
  }
}

/**
 * Shell History Hook
 */
export function useShellHistory(options: ShellHistoryOptions = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const historyFile = opts.historyFile || getDefaultHistoryPath();
  
  const [history, setHistory] = useState<ShellHistoryEntry[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const saveTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

  // Load history on mount
  useEffect(() => {
    const entries = loadHistory(historyFile);
    setHistory(entries);
    setCurrentIndex(-1);
    
    logger.info('Shell history loaded', {
      component: 'useShellHistory',
      operation: 'init',
      count: entries.length,
    });
  }, [historyFile]);

  // Save history with debounce
  const scheduleSave = useCallback(() => {
    if (!opts.autoSave) return;
    
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    
    saveTimeoutRef.current = setTimeout(() => {
      saveHistory(historyFile, history);
    }, 500); // 500ms debounce
  }, [historyFile, history, opts.autoSave]);

  /**
   * Add command to history
   */
  const addCommand = useCallback((
    command: string,
    cwd: string,
    exitCode?: number
  ) => {
    // Don't add empty commands or duplicates of the last command
    if (!command.trim()) return;
    
    const lastEntry = history[history.length - 1];
    if (lastEntry && lastEntry.command === command.trim()) {
      return;
    }

    const entry: ShellHistoryEntry = {
      command: command.trim(),
      timestamp: Date.now(),
      cwd,
      exitCode,
    };

    setHistory(prev => {
      const newHistory = [...prev, entry];
      
      // Trim to max entries
      if (newHistory.length > opts.maxEntries!) {
        return newHistory.slice(newHistory.length - opts.maxEntries!);
      }
      
      return newHistory;
    });

    setCurrentIndex(-1);
    scheduleSave();

    logger.debug('Command added to history', {
      component: 'useShellHistory',
      operation: 'add',
      command: command.substring(0, 50),
    });
  }, [history, opts.maxEntries, scheduleSave]);

  /**
   * Navigate history (UP arrow)
   */
  const navigateUp = useCallback((): string | null => {
    if (history.length === 0) return null;
    
    const newIndex = currentIndex < history.length - 1 
      ? currentIndex + 1 
      : currentIndex;
    
    setCurrentIndex(newIndex);
    
    const entry = history[history.length - 1 - newIndex];
    return entry ? entry.command : null;
  }, [history, currentIndex]);

  /**
   * Navigate history (DOWN arrow)
   */
  const navigateDown = useCallback((): string | null => {
    if (currentIndex <= 0) {
      setCurrentIndex(-1);
      return ''; // Return empty string to clear input
    }
    
    const newIndex = currentIndex - 1;
    setCurrentIndex(newIndex);
    
    const entry = history[history.length - 1 - newIndex];
    return entry ? entry.command : '';
  }, [history, currentIndex]);

  /**
   * Search history by text
   */
  const searchHistory = useCallback((query: string): ShellHistoryEntry[] => {
    if (!query.trim()) return history;
    
    const lowerQuery = query.toLowerCase();
    return history.filter(entry => 
      entry.command.toLowerCase().includes(lowerQuery)
    ).reverse(); // Most recent first
  }, [history]);

  /**
   * Clear all history
   */
  const clearHistory = useCallback(() => {
    setHistory([]);
    setCurrentIndex(-1);
    
    try {
      if (fs.existsSync(historyFile)) {
        fs.unlinkSync(historyFile);
      }
      logger.info('Shell history cleared', {
        component: 'useShellHistory',
        operation: 'clear',
      });
    } catch (error) {
      logger.error('Failed to clear shell history', {
        component: 'useShellHistory',
        operation: 'clear',
        error,
      });
    }
  }, [historyFile]);

  /**
   * Get last N commands
   */
  const getRecent = useCallback((count: number = 10): ShellHistoryEntry[] => {
    return history.slice(-count).reverse();
  }, [history]);

  /**
   * Manually save history
   */
  const save = useCallback(() => {
    saveHistory(historyFile, history);
  }, [historyFile, history]);

  /**
   * Reset navigation index
   */
  const resetIndex = useCallback(() => {
    setCurrentIndex(-1);
  }, []);

  return {
    history,
    currentIndex,
    addCommand,
    navigateUp,
    navigateDown,
    searchHistory,
    clearHistory,
    getRecent,
    save,
    resetIndex,
  };
}
