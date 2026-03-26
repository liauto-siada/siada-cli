/**
 * Model Selector Hook
 * Manages model selector dialog state and actions.
 *
 * Mirrors useEditorDialog: isOpen state lives inside IPWW (local), not in App.tsx.
 * open() is called synchronously from handleSubmit — same pattern as EditorDialog —
 * so the keypress guard is always current and there is no stale-closure window.
 */

import { useState, useCallback } from 'react';

export interface UseModelSelectorReturn {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  handleSelect: (modelName: string) => void;
}

export function useModelSelector(
  onSelectModel?: (modelName: string) => void
): UseModelSelectorReturn {
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => {
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleSelect = useCallback(
    (modelName: string) => {
      onSelectModel?.(modelName);
      setIsOpen(false);
    },
    [onSelectModel]
  );

  return { isOpen, open, close, handleSelect };
}
