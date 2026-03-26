/**
 * Editor Settings Dialog
 * Allows users to select their preferred external editor
 */

import React, { useState, useEffect } from 'react';
import { useKeypress } from '../../hooks/useKeypress.js';
import { Box, Text, useStdout, useInput } from '@jrichman/ink';
import {
  type EditorType,
  checkHasEditorType,
  getEditorDisplayName,
  EDITOR_DISPLAY_NAMES,
} from '../../utils/editor.js';

export interface EditorOption {
  type: EditorType;
  displayName: string;
  installed: boolean;
}

interface EditorDialogProps {
  currentEditor?: EditorType;
  onSelect: (editor: EditorType) => void;
  onCancel: () => void;
}

/**
 * Get all available editor options with installation status
 */
function getEditorOptions(): EditorOption[] {
  const options: EditorOption[] = [
    {
      type: 'not_set',
      displayName: 'None',
      installed: true,
    },
  ];

  // Check each editor type
  const editorTypes = Object.keys(EDITOR_DISPLAY_NAMES) as Array<
    Exclude<EditorType, 'not_set'>
  >;

  for (const editorType of editorTypes) {
    const installed = checkHasEditorType(editorType);
    options.push({
      type: editorType,
      displayName: EDITOR_DISPLAY_NAMES[editorType],
      installed,
    });
  }

  return options;
}

export function EditorDialog({
  currentEditor,
  onSelect,
  onCancel,
}: EditorDialogProps): React.JSX.Element {
  const options = getEditorOptions();
  
  // Find current selection index
  const currentIndex = options.findIndex((opt) => opt.type === currentEditor);
  const [selectedIndex, setSelectedIndex] = useState(
    currentIndex >= 0 ? currentIndex : 0
  );
  const { stdout } = useStdout();
  const terminalWidth =  stdout?.columns ?? 80;
  // Handle keyboard input
  useKeypress(
    (key) => {
      // Up arrow
      if (key.name === 'up') {
        setSelectedIndex((prev) => {
          // Skip disabled options
          let newIndex = prev - 1;
          while (newIndex >= 0 && !options[newIndex].installed) {
            newIndex--;
          }
          return newIndex >= 0 ? newIndex : prev;
        });
        return;
      }

      // Down arrow
      if (key.name === 'down') {
        setSelectedIndex((prev) => {
          // Skip disabled options
          let newIndex = prev + 1;
          while (newIndex < options.length && !options[newIndex].installed) {
            newIndex++;
          }
          return newIndex < options.length ? newIndex : prev;
        });
        return;
      }

      // Enter to confirm
      if (key.name === 'return') {
        const selected = options[selectedIndex];
        if (selected.installed) {
          onSelect(selected.type);
        }
        return;
      }

      // Escape to cancel
      if (key.name === 'escape') {
        onCancel();
        return;
      }
    },
    { isActive: true }
  );

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="gray "
      paddingX={2}
      paddingY={1}
      width={terminalWidth}
    >
      <Box marginBottom={1}>
        <Text bold color="white">
           Editor Selection
        </Text>
      </Box>

      {/* Editor options */}
      {options.map((option, index) => {
        const isSelected = index === selectedIndex;
        const disabled = !option.installed;
        
        let displayText = option.displayName;
        if (disabled) {
          displayText += ' (Not installed)';
        }

        return (
          <Box key={option.type} marginLeft={1}>
            <Text
              color={disabled ? 'gray' : isSelected ? 'cyan' : 'white'}
              bold={isSelected}
            >
              {isSelected ? '● ' : '○ '}
              {displayText}
            </Text>
          </Box>
        );
      })}

      {/* Current preference */}
      <Box marginTop={1} marginLeft={1}>
        <Text dimColor>
          Current: {currentEditor ? getEditorDisplayName(currentEditor) : 'None'}
        </Text>
      </Box>

      {/* Instructions */}
      <Box marginTop={1} borderStyle="single" borderColor="gray" paddingX={1}>
        <Text >
          ↑↓ Navigate • Enter Select • Esc Cancel • Ctrl+X Open Editor
        </Text>
      </Box>
    </Box>
  );
}
