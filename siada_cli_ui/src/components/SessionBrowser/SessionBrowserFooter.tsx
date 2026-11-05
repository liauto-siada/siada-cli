/**
 * Session Browser Footer Component
 * Displays keyboard shortcuts help
 */

import React from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { PickerFooter, pickerHint } from '../Picker/Picker.js';
import { SessionBrowserFooterProps } from '../../types/session.js';

export const SessionBrowserFooter: React.FC<SessionBrowserFooterProps> = ({
  isSearchMode,
  hasResults,
  scope,
}) => {
  useUiLanguage();
  if (isSearchMode) {
    return (
      <PickerFooter>{t('Enter 确定 · Esc 返回 · 输入关键词搜索', 'Enter confirm · Esc back · Type to search')}</PickerFooter>
    );
  }

  if (!hasResults) {
    return (
      <PickerFooter>{PANEL_TIPS.sessionEmpty(scope === 'current' ? t('所有项目', 'all projects') : t('仅当前项目', 'current only'))}</PickerFooter>
    );
  }

  const scopeHint = scope === 'current' ? t('所有项目', 'all projects') : t('仅当前项目', 'current only');

  return (
    <PickerFooter>{pickerHint('vertical', 'resume')} · {t(`/ 搜索 · s 排序 · Ctrl+R 重命名 · Ctrl+A ${scopeHint}`,
      `/ search · s sort · Ctrl+R rename · Ctrl+A ${scopeHint}`)}</PickerFooter>
  );
};
