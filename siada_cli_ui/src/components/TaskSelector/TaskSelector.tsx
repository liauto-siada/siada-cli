import React, { useState } from 'react';
import { Text } from '@jrichman/ink';
import { t, useUiLanguage } from '../../i18n/index.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { PickerFrame, PickerRow, PickerScrollHint, pickerHint, usePickerWindow } from '../Picker/Picker.js';

export interface TaskItem {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  category: string;
  status: string;
  needs_confirmation: boolean;
  suggested_actions: string[];
  confidence: number;
}

export interface TaskSelectorProps {
  availableRows?: number;
  tasks: TaskItem[];
  onSelect: (task: TaskItem) => void;
  onExit: () => void;
}

const PRIORITY_LABEL: Record<string, string> = { high: '!!!', medium: '!', low: '' };

export const TaskSelector: React.FC<TaskSelectorProps> = ({ tasks, onSelect, onExit, availableRows }) => {
  useUiLanguage();
  const [activeIndex, setActiveIndex] = useState(0);
  const { startIndex, endIndex } = usePickerWindow(tasks.length, activeIndex, {
    rows: availableRows, summary: true, description: true,
  });
  useKeypress(key => {
    if (key.name === 'up' || key.sequence === 'k') setActiveIndex(i => Math.max(0, i - 1));
    else if (key.name === 'down' || key.sequence === 'j') setActiveIndex(i => Math.min(tasks.length - 1, i + 1));
    else if (key.name === 'return' && tasks[activeIndex]) onSelect(tasks[activeIndex]);
    else if (key.name === 'escape' || key.ctrl && key.name === 'c' || /^(q|Q)$/.test(key.sequence)) onExit();
  });
  return <PickerFrame title={t('待处理任务', 'Pending Tasks')}
    summary={t(`已发现 ${tasks.length} 个任务`, `${tasks.length} tasks discovered`)}
    description={tasks.length ? tasks[activeIndex]?.description.replace(/\s+/g, ' ')
      : t('启动主动任务服务以发现任务', 'Run the proactive daemon to discover tasks.')}
    hint={pickerHint('vertical', 'execute')}>
    {tasks.length === 0 && <Text wrap="truncate-end">{t('暂无待处理任务', 'No Tasks Found')}</Text>}
    <PickerScrollHint visible={startIndex > 0} direction="up" />
    {tasks.slice(startIndex, endIndex).map((task, offset) => <PickerRow key={task.id} active={startIndex + offset === activeIndex}>
      {`${PRIORITY_LABEL[task.priority] || ''} ${task.category.slice(0, 5)} ${task.confidence.toFixed(2)}  ${task.title}`.trim()}
      {task.needs_confirmation ? t(' [待确认]', ' [confirm]') : ''}
    </PickerRow>)}
    <PickerScrollHint visible={endIndex < tasks.length} direction="down" />
  </PickerFrame>;
};