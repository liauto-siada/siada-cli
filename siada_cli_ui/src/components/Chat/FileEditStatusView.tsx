import React from 'react';
import { Box, Text } from '@jrichman/ink';
import type { FileEditPresentation } from '../../utils/diff.js';
import { colors } from '../../utils/colors.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { ToolHeading } from './ToolHeading.js';
import { wrapToolFieldText } from './ToolPromptView.js';

/** Result-aware file operations share the same heading and tree as other tools. */
export const FileEditStatusView: React.FC<{
  edit: FileEditPresentation;
  collapsed: boolean;
  width: number;
  maxRows?: number;
  showHeading?: boolean;
}> = ({ edit, collapsed, width, maxRows, showHeading = true }) => {
  useUiLanguage();
  const action = edit.action === 'create' ? 'Create' : edit.action === 'undo' ? 'Undo' : 'Update';
  const failed = edit.status === 'failed';
  const reason = failed ? edit.error || t('文件操作失败。', 'File operation failed.')
    : edit.status === 'pending' ? t('等待工具结果…', 'Waiting for tool result...')
    : edit.status === 'unverified' ? edit.details || t('工具结果不可用，尚未验证修改。', 'Tool result unavailable; changes not verified.')
    : edit.details || t('操作已完成，文本内容没有变化。', 'Applied without text changes.');
  const detailRows = failed && edit.details
    ? edit.details.split('\n').flatMap(line => wrapToolFieldText(line, Math.max(width - 6, 2)))
    : [];
  const visibleRows = maxRows === undefined ? detailRows : detailRows.slice(0, Math.max(maxRows - 2, 0));
  return (
    <Box flexDirection="column" marginBottom={showHeading ? 1 : 0}>
      {showHeading && <ToolHeading parts={[`${action} ${edit.path}`]} failed={failed}
        suffix={collapsed ? <Text color={failed ? colors.error : colors.content.secondary}>{` — ${reason}`}</Text> : undefined} />}
      {!collapsed && (
        <Box flexDirection="column" paddingLeft={2}>
          <Text><Text color={colors.content.secondary}>└─ </Text><Text color={failed ? colors.error : colors.content.secondary}>{reason}</Text></Text>
          {visibleRows.map((line, index) => <Text key={index} color={colors.content.secondary}>{line}</Text>)}
          {visibleRows.length < detailRows.length && <Text color={colors.content.secondary}>{t(
            `… 还有 ${detailRows.length - visibleRows.length} 行`, `… ${detailRows.length - visibleRows.length} more lines`)}</Text>}
        </Box>
      )}
    </Box>
  );
};
