/**
 * Editor Settings Dialog
 * Allows users to select their preferred external editor
 */

import React, { useState, useMemo } from 'react';
import { t, useUiLanguage } from '../../i18n/index.js';
import { PickerFrame, PickerRow, PickerScrollHint, pickerHint, usePickerWindow } from '../Picker/Picker.js';
import { useKeypress } from '../../hooks/useKeypress.js';
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
      displayName: t('未设置', 'None'),
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
  const language = useUiLanguage();
  const options = useMemo(getEditorOptions, [language]);
  
  // Find current selection index
  const currentIndex = options.findIndex((opt) => opt.type === currentEditor);
  const [selectedIndex, setSelectedIndex] = useState(
    currentIndex >= 0 ? currentIndex : 0
  );
  const { startIndex: start, endIndex } = usePickerWindow(options.length, selectedIndex, { summary: true });
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
    <PickerFrame title={t('选择编辑器', 'Editor Selection')}
      summary={`${t('当前：', 'Current: ')}${currentEditor && currentEditor !== 'not_set' ? getEditorDisplayName(currentEditor) : t('未设置', 'None')}`}
      hint={pickerHint('vertical')}>
      <PickerScrollHint visible={start > 0} direction="up" />
      {/* Editor options */}
      {options.slice(start, endIndex).map((option, offset) => {
        const index = start + offset;
        const isSelected = index === selectedIndex;
        const disabled = !option.installed;
        
        let displayText = option.displayName;
        if (disabled) {
          displayText += t('（未安装）', ' (Not installed)');
        }

        return (
          <PickerRow key={option.type} active={isSelected} disabled={disabled}
            current={option.type === (currentEditor || 'not_set')}>{displayText}</PickerRow>
        );
      })}

      <PickerScrollHint visible={endIndex < options.length} direction="down" />
    </PickerFrame>
  );
}
