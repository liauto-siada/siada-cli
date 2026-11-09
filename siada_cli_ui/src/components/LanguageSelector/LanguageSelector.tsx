import React, { useState } from 'react';
import { PickerFrame, PickerRow, pickerHint } from '../Picker/Picker.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { getUiLanguage, useUiLanguage, t, type UiLanguage } from '../../i18n/index.js';

const options: { language: UiLanguage; label: string }[] = [
  { language: 'en', label: 'English' },
  { language: 'zh-CN', label: '中文' },
];

export function LanguageSelector({ onSelect, onClose }: {
  onSelect: (language: UiLanguage) => void; onClose: () => void;
}) {
  useUiLanguage();
  const [selected, setSelected] = useState(getUiLanguage() === 'en' ? 0 : 1);
  useKeypress(key => {
    if (key.name === 'up' || key.sequence === 'k') setSelected(0);
    else if (key.name === 'down' || key.sequence === 'j') setSelected(1);
    else if (key.name === 'return') onSelect(options[selected].language);
    else if (key.name === 'escape' || key.ctrl && key.name === 'c' || key.sequence === 'q') onClose();
  });
  return <PickerFrame title={t('界面语言', 'Interface language')}
    summary={`${t('当前：', 'Current: ')}${options.find(option => option.language === getUiLanguage())?.label}`}
    hint={pickerHint('vertical')}>
    {options.map((option, index) => <PickerRow key={option.language} active={selected === index}
      current={getUiLanguage() === option.language}>{option.label}</PickerRow>)}
  </PickerFrame>;
}