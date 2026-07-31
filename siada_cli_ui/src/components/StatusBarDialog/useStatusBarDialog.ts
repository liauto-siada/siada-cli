/**
 * Status Bar Dialog Hook
 * Manages status bar dialog state and configuration
 */

import { useState, useCallback } from 'react';
import { configManager } from '../../utils/config.js';

export interface UseStatusBarDialogReturn {
  isOpen: boolean;
  visibleItems: string[];
  openDialog: () => void;
  closeDialog: () => void;
  handleToggle: (key: string) => void;
}

export function useStatusBarDialog(): UseStatusBarDialogReturn {
  const [isOpen, setIsOpen] = useState(false);
  const [visibleItems, setVisibleItems] = useState<string[]>(
    configManager.getStatusbarItems()
  );

  const openDialog = useCallback(() => {
    // Re-read config on open to get latest values
    setVisibleItems(configManager.getStatusbarItems());
    setIsOpen(true);
  }, []);

  const closeDialog = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleToggle = useCallback((key: string) => {
    setVisibleItems(prev => {
      const next = prev.includes(key)
        ? prev.filter(k => k !== key)
        : [...prev, key];
      // Persist immediately
      configManager.setStatusbarItems(next);
      return next;
    });
  }, []);

  return {
    isOpen,
    visibleItems,
    openDialog,
    closeDialog,
    handleToggle,
  };
}