import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { colors } from '../../utils/colors.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { calculateVisibleRange } from '../../utils/sessionUtils.js';
import { useThemeVersion } from '../../themes/index.js';

export const PICKER_ACTIVE_BACKGROUND = '#8aa8c8';
export const PICKER_ACTIVE_FOREGROUND = '#1f2328';

function singleLine(children: React.ReactNode) {
  return React.Children.map(children, child => typeof child === 'string' ? child.replace(/[\r\n]+/g, ' ') : child);
}

/** Shared chrome for both list pickers and the horizontal effort scale. */
export function PickerHeader({ title, summary }: { title: React.ReactNode; summary?: React.ReactNode }) {
  useThemeVersion();
  useUiLanguage();
  return <Box flexDirection="column">
    <Text bold wrap="truncate-end">{singleLine(title)}</Text>
    {summary != null && <Text color={colors.content.secondary} wrap="truncate-end">{singleLine(summary)}</Text>}
  </Box>;
}

export function PickerFooter({ children }: { children: React.ReactNode }) {
  useThemeVersion();
  return <Box marginTop={1}>
    <Text color={colors.content.secondary} wrap="truncate-end">{children}</Text>
  </Box>;
}

export function pickerHint(direction: 'horizontal' | 'vertical', action: 'confirm' | 'execute' | 'toggle' | 'resume' = 'confirm') {
  const navigate = direction === 'horizontal' ? '←→' : '↑↓';
  const submit = action === 'toggle' ? t('Space/Enter 切换', 'Space/Enter toggle')
    : action === 'execute' ? t('Enter 执行', 'Enter execute')
    : action === 'resume' ? t('Enter 恢复', 'Enter resume') : t('Enter 确定', 'Enter confirm');
  return `${navigate} ${t('选择', 'select')} · ${submit} · ${t('Esc 返回', 'Esc back')}`;
}

export function PickerFrame({ title, summary, description, hint, children }: {
  title: React.ReactNode; summary?: React.ReactNode; description?: React.ReactNode;
  hint: React.ReactNode; children: React.ReactNode;
}) {
  return <Box flexDirection="column" paddingX={1} width="100%">
    <PickerHeader title={title} summary={summary} />
    <Box flexDirection="column">{children}</Box>
    {description != null && <Box marginTop={1}>
      <Text color={colors.content.secondary} wrap="truncate-end">{singleLine(description)}</Text>
    </Box>}
    <PickerFooter>{hint}</PickerFooter>
  </Box>;
}

/** Focus, saved value and checkbox state deliberately use separate indicators. */
export function PickerRow({ active, current = false, disabled = false, checked, children }: {
  active: boolean; current?: boolean; disabled?: boolean; checked?: boolean; children: React.ReactNode;
}) {
  useUiLanguage();
  useThemeVersion();
  const highlighted = active && !disabled;
  return <Box height={1} flexShrink={0}
    backgroundColor={highlighted ? PICKER_ACTIVE_BACKGROUND : undefined}>
    <Box width={2} flexShrink={0}>
      <Text color={highlighted ? PICKER_ACTIVE_FOREGROUND : colors.content.secondary}>{active ? '› ' : '  '}</Text>
    </Box>
    <Box flexGrow={1} flexShrink={1} overflowX="hidden">
      <Text color={highlighted ? PICKER_ACTIVE_FOREGROUND : disabled ? colors.content.tertiary : undefined}
        bold={highlighted} wrap="truncate-end">
        {checked !== undefined ? checked ? '[x] ' : '[ ] ' : ''}
        {singleLine(children)}{current ? t('（当前）', ' (current)') : ''}
      </Text>
    </Box>
  </Box>;
}

export function PickerScrollHint({ visible, direction }: { visible: boolean; direction: 'up' | 'down' }) {
  useThemeVersion();
  useUiLanguage();
  if (!visible) return null;
  return <Text color={colors.content.secondary} wrap="truncate-end">
    {direction === 'up' ? t('▲ 上方还有选项', '▲ More above') : t('▼ 下方还有选项', '▼ More below')}
  </Text>;
}

/** Reserve title, footer, scroll indicators and the terminal's trailing newline. */
export function calculatePickerVisibleCount(rows: number, {
  summary = false, description = false, rowHeight = 1, extraRows = 0,
}: { summary?: boolean; description?: boolean; rowHeight?: number; extraRows?: number } = {}) {
  return Math.max(1, Math.floor((rows - 6 - Number(summary) - (description ? 2 : 0) - extraRows) / rowHeight));
}

export function usePickerWindow(total: number, activeIndex: number, options: {
  rows?: number; summary?: boolean; description?: boolean; rowHeight?: number; extraRows?: number;
} = {}) {
  const { rows } = useTerminalSize();
  const count = calculatePickerVisibleCount(options.rows ?? rows, options);
  return { count, ...calculateVisibleRange(total, activeIndex, count) };
}