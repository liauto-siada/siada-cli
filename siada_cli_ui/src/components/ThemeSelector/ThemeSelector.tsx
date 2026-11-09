import React, { useState } from 'react';
import { t, useUiLanguage } from '../../i18n/index.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { PickerFrame, PickerRow, pickerHint } from '../Picker/Picker.js';

export interface ThemeSelectorProps {
  embedded?: boolean;
  themes: string[];
  current: string;
  onSelect: (theme: string) => void;
  onExit: () => void;
}

const THEME_NOTES: Record<string, string> = {
  dark: 'GitHub Dark', light: 'GitHub Light',
};

export const ThemeSelector: React.FC<ThemeSelectorProps> = ({ themes, current, onSelect, onExit }) => {
  useUiLanguage();
  const [activeIndex, setActiveIndex] = useState(Math.max(0, themes.indexOf(current)));
  useKeypress(key => {
    if (key.name === 'up' || key.sequence === 'k') setActiveIndex(i => Math.max(0, i - 1));
    else if (key.name === 'down' || key.sequence === 'j') setActiveIndex(i => Math.min(themes.length - 1, i + 1));
    else if (key.name === 'return' && themes[activeIndex]) onSelect(themes[activeIndex]);
    else if (key.name === 'escape' || key.ctrl && key.name === 'c' || /^(q|Q)$/.test(key.sequence)) onExit();
  });
  return <PickerFrame title={t('切换主题', 'Switch Theme')}
    summary={`${t('当前：', 'Current: ')}${current}`} hint={pickerHint('vertical')}>
    {themes.map((name, i) => <PickerRow key={name} active={i === activeIndex} current={name === current}>
      {name}{THEME_NOTES[name] ? `  ${THEME_NOTES[name]}` : ''}
    </PickerRow>)}
  </PickerFrame>;
};