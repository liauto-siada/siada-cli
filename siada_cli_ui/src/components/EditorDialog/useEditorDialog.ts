/**
 * Editor Dialog Hook
 * Manages editor dialog state and actions
 */

import { useState, useCallback } from 'react';
import type { EditorType } from '../../utils/editor.js';
import { configManager } from '../../utils/config.js';

export interface UseEditorDialogReturn {
  isOpen: boolean;
  currentEditor: EditorType | undefined;
  openDialog: () => void;
  closeDialog: () => void;
  handleSelect: (editor: EditorType) => { success: boolean; message: string };
}

/**
 * Hook for managing editor dialog
 */
export function useEditorDialog(): UseEditorDialogReturn {
  const [isOpen, setIsOpen] = useState(false);
  const [currentEditor, setCurrentEditor] = useState<EditorType | undefined>(
    configManager.getPreferredEditor()
  );

  const openDialog = useCallback(() => {
    setIsOpen(true);
  }, []);

  const closeDialog = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleSelect = useCallback(
    (editor: EditorType): { success: boolean; message: string } => {
      try {
        // Save to config
        configManager.setPreferredEditor(editor);
        setCurrentEditor(editor);
        setIsOpen(false);

        const editorName =
          editor === 'not_set'
            ? 'None'
            : editor === 'vim'
            ? 'Vim'
            : editor === 'vscode'
            ? 'VS Code'
            : editor;

        return {
          success: true,
          message: `Editor preference set to "${editorName}"`,
        };
      } catch (error) {
        return {
          success: false,
          message: `Failed to set editor preference: ${error}`,
        };
      }
    },
    []
  );

  return {
    isOpen,
    currentEditor,
    openDialog,
    closeDialog,
    handleSelect,
  };
}
