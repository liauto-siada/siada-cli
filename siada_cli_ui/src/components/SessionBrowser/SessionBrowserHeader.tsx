/**
 * Session Browser Header Component
 * Displays title and summary information
 */

import React from 'react';
import { t, useUiLanguage } from '../../i18n/index.js';
import { PickerHeader } from '../Picker/Picker.js';
import { SessionBrowserHeaderProps } from '../../types/session.js';

export const SessionBrowserHeader: React.FC<SessionBrowserHeaderProps> = ({
  totalCount,
  filteredCount,
  currentPage,
  totalPages,
  sortOrder,
  sortReverse,
  scope,
  projectName,
}) => {
  useUiLanguage();
  const sortLabel = {
    date: t('时间', 'Date'),
    messages: t('消息数', 'Messages'),
    name: t('名称', 'Name'),
  }[sortOrder];

  const sortIcon = sortReverse ? '↓' : '↑';
  
  const scopeLabel = scope === 'all' 
    ? t('所有项目', 'All Projects')
    : projectName 
      ? t(`当前项目：${projectName}`, `Current Project: ${projectName}`)
      : t('当前项目', 'Current Project');

  return (
    <PickerHeader title={t(`继续历史会话（${scopeLabel}）`, `Resume Session (${scopeLabel})`)}
      summary={t(`显示 ${filteredCount}/${totalCount} 个会话 · 第 ${currentPage}/${totalPages} 页 · 排序：${sortLabel} ${sortIcon}`,
        `Showing ${filteredCount} of ${totalCount} sessions · Page ${currentPage}/${totalPages} · Sort: ${sortLabel} ${sortIcon}`)} />
  );
};
