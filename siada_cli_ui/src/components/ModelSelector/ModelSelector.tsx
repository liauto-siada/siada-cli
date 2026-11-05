/**
 * Model Selector Component
 * Displays a list of available models and allows the user to switch
 */

import React, { useState, useCallback } from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Text } from '@jrichman/ink';
import { PickerFrame, PickerRow, PickerScrollHint, pickerHint, calculatePickerVisibleCount } from '../Picker/Picker.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { useClearScreenOnMount } from '../../hooks/useClearScreenOnMount.js';
import { calculateVisibleRange } from '../../utils/sessionUtils.js';

export interface ModelSelectorProps {
  embedded?: boolean;
  availableRows?: number;
  models: string[];
  currentModel: string;
  modelNotes?: Record<string, string>;
  onSelect: (modelName: string) => void;
  onExit: () => void;
}

/** Share the picker chrome budget; each model occupies exactly one row. */
export function calculateVisibleModelCount(terminalRows: number): number {
  return calculatePickerVisibleCount(terminalRows, { summary: true });
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  currentModel,
  modelNotes,
  onSelect,
  onExit,
  embedded = false,
  availableRows,
}) => {
  // Start selection on the current model if present, otherwise 0
  useUiLanguage();
  const initialIndex = Math.max(0, models.indexOf(currentModel));
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const { rows: terminalRows } = useTerminalSize();
  // Fullscreen view: clear the screen on mount and paint the first frame
  // from row 1 instead of mid-screen (where it would scroll its top off).
  const cleared = useClearScreenOnMount(!embedded);

  const moveSelection = useCallback((delta: number) => {
    setActiveIndex(prev => {
      const next = prev + delta;
      if (next < 0) return 0;
      if (next >= models.length) return models.length - 1;
      return next;
    });
  }, [models.length]);

  useKeypress((key) => {
    if (key.name === 'up' || key.sequence === 'k') {
      moveSelection(-1);
    } else if (key.name === 'down' || key.sequence === 'j') {
      moveSelection(1);
    } else if (key.name === 'return') {
      const selected = models[activeIndex];
      if (selected) {
        onSelect(selected);
      }
    } else if (
      key.name === 'escape' ||
      (key.ctrl && key.name === 'c') ||
      key.sequence === 'q' ||
      key.sequence === 'Q'
    ) {
      onExit();
    }
  });

  if (models.length === 0) {
    return (
      <PickerFrame title={t('切换模型', 'Switch Model')} hint={PANEL_TIPS.close}>
        <Text>{t('暂无可用模型', 'No Models Available')}</Text>
      </PickerFrame>
    );
  }

  // Wait for the mount clear so the first real frame paints from row 1.
  if (!cleared) return null;

  // Height-limited window centered on the active item (same approach as
  // SessionBrowser): the terminal only shows the bottom of a frame taller
  // than itself, so an unwindowed list hides the active item.
  const visibleCount = calculateVisibleModelCount(availableRows ?? terminalRows);
  const { startIndex, endIndex } = calculateVisibleRange(
    models.length,
    activeIndex,
    visibleCount
  );
  const visibleModels = models.slice(startIndex, endIndex);

  return (
    <PickerFrame title={t('切换模型', 'Switch Model')}
      summary={`${t('当前：', 'Current: ')}${currentModel} · ${t(`${models.length} 个可用模型`, `${models.length} models available`)}`}
      hint={pickerHint('vertical')}>
        <PickerScrollHint visible={startIndex > 0} direction="up" />
        {visibleModels.map((model, idx) => {
          const index = startIndex + idx;
          const isActive = index === activeIndex;
          const isCurrent = model === currentModel;

          const note = modelNotes?.[model] ? `(${modelNotes[model]})` : '';

          return (
            <PickerRow key={`${model}-${index}`} active={isActive} current={isCurrent}>
              {model}{note ? `  ${note}` : ''}
            </PickerRow>
          );
        })}
        <PickerScrollHint visible={endIndex < models.length} direction="down" />
    </PickerFrame>
  );
};
