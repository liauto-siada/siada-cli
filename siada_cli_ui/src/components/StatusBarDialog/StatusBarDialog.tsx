/**
 * Status Bar Dialog
 * Allows users to toggle visibility of individual status bar items
 */

import React, { useState, useContext, useMemo } from 'react';
import { createHash } from 'crypto';
import stringWidth from 'string-width';
import { PANEL_TIPS } from '../../constants/tips.js';
import { BottomPaneContext } from '../../contexts/BottomPaneContext.js';
import { Box, Text } from '@jrichman/ink';
import { bilingual, t, useUiLanguage } from '../../i18n/index.js';
import { PickerFrame, PickerRow, PickerScrollHint, pickerHint, usePickerWindow } from '../Picker/Picker.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { colors } from '../../utils/colors.js';
import { useThemeVersion } from '../../themes/index.js';

// Full 12-item definition: key → label preview
const STATUSBAR_ITEM_LABELS: Record<string, string> = bilingual({
  model: '模型：example-model',
  balance: '剩余额度：25.34%',
  input_cost: '输入：¥0.0012(12,345)',
  output_cost: '输出：¥0.0034(6,789)',
  cache_write_cost: '缓存写入：¥0.0001(100)',
  cache_read_cost: '缓存读取：¥0.0023(1,234)',
  total_cost: '总费用：¥0.0046(19,234)',
  hit_rate: '缓存命中：45.2%',
  git_branch: '⎇ main',
  workspace: '~/projects/foo',
  cost_time: '12.3s',
  token_usage: '68,284 / 600,000 tokens',
}, {
  model: 'Model: example-model', balance: 'Balance: 25.34%',
  input_cost: 'in:¥0.0012(12,345)', output_cost: 'out:¥0.0034(6,789)',
  cache_write_cost: 'cw:¥0.0001(100)', cache_read_cost: 'cr:¥0.0023(1,234)',
  total_cost: 'cost:¥0.0046(19,234)', hit_rate: 'hit:45.2%',
  git_branch: '⎇ main', workspace: '~/projects/foo', cost_time: '12.3s',
  token_usage: '68,284 / 600,000 tokens',
});

// Description for each status bar item, shown below the list and follows the current selection
const STATUSBAR_ITEM_DESCRIPTIONS: Record<string, string> = bilingual({
  model: '当前使用的模型名称',
  balance: '账户剩余额度的百分比',
  input_cost: '未命中缓存的输入费用和 token 数',
  output_cost: '模型输出的费用和 token 数',
  cache_write_cost: '首次将上下文写入缓存的费用和 token 数',
  cache_read_cost: '复用缓存上下文的费用和 token 数',
  total_cost: '本轮累计费用和 token 数',
  hit_rate: '缓存命中率 = 缓存读取 token /（输入 + 缓存读取）token；越高表示复用越多',
  git_branch: '当前工作目录的 Git 分支',
  workspace: '当前工作目录的路径',
  cost_time: '本轮耗时（从开始到最近一次模型响应）',
  token_usage: '当前上下文使用的 token 数 / 模型上下文上限',
}, {
  model: 'Name of the model currently in use',
  balance: 'Account balance, as a percentage of remaining quota',
  input_cost: 'Cost and token count for input not served from cache',
  output_cost: 'Cost and token count for model output',
  cache_write_cost: 'Cost and token count for writing context into the cache (first-time context)',
  cache_read_cost: 'Cost and token count for context served from cache (reused context)',
  total_cost: 'Total accumulated cost and token count for this turn',
  hit_rate: 'Cache hit rate = cache-read tokens / (input + cache-read) tokens; higher means more context reuse',
  git_branch: 'Git branch of the current working directory',
  workspace: 'Path of the current working directory',
  cost_time: 'Elapsed time for this turn (from turn start to the latest model response)',
  token_usage: 'Tokens used in the current context / the model\'s context window limit',
});

const STATUSBAR_KEYS = Object.keys(STATUSBAR_ITEM_LABELS);

interface StatusBarDialogProps {
  visibleItems: string[];
  onToggle: (key: string) => void;
  onClose: () => void;
}

export function StatusBarDialog({
  visibleItems,
  onToggle,
  onClose,
}: StatusBarDialogProps): React.JSX.Element {
  useUiLanguage();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const { startIndex: start, endIndex } = usePickerWindow(STATUSBAR_KEYS.length, selectedIndex, { description: true });

  useKeypress(
    (key) => {
      // Up arrow
      if (key.name === 'up') {
        setSelectedIndex((prev) => Math.max(0, prev - 1));
        return;
      }

      // Down arrow
      if (key.name === 'down') {
        setSelectedIndex((prev) => Math.min(STATUSBAR_KEYS.length - 1, prev + 1));
        return;
      }

      // Space or Enter to toggle
      if (key.name === 'space' || key.name === 'return') {
        onToggle(STATUSBAR_KEYS[selectedIndex]);
        return;
      }

      // Escape to close
      if (key.name === 'escape') {
        onClose();
        return;
      }
    },
    { isActive: true }
  );

  return (
    <PickerFrame title={t('状态栏显示项', 'Status Bar Items')}
      description={STATUSBAR_ITEM_DESCRIPTIONS[STATUSBAR_KEYS[selectedIndex]]}
      hint={pickerHint('vertical', 'toggle')}>
      <PickerScrollHint visible={start > 0} direction="up" />
      {STATUSBAR_KEYS.slice(start, endIndex).map((key, offset) => {
        const index = start + offset;
        const isSelected = index === selectedIndex;
        const isVisible = visibleItems.includes(key);
        const label = STATUSBAR_ITEM_LABELS[key];

        return (
          <PickerRow key={key} active={isSelected} checked={isVisible}>{label}</PickerRow>
        );
      })}

      <PickerScrollHint visible={endIndex < STATUSBAR_KEYS.length} direction="down" />
    </PickerFrame>
  );
}

export interface StatusDialogProps {
  model?: string;
  agent?: string;
  sessionId?: string | null;
  workingDir?: string;
  onClose: () => void;
}

export function StatusDialog({
  model,
  agent,
  sessionId,
  workingDir,
  onClose,
}: StatusDialogProps): React.JSX.Element {
  const pane = useContext(BottomPaneContext);
  useUiLanguage();
  useThemeVersion();

  const projectHash = useMemo(() => {
    if (!workingDir) return '-';
    return createHash('sha256').update(workingDir).digest('hex');
  }, [workingDir]);

  const items = [
    { key: 'model', label: t('模型', 'Model'), value: model || '-' },
    { key: 'agent', label: t('智能体', 'Agent'), value: agent || '-' },
    { key: 'session_id', label: t('会话 ID', 'Session id'), value: sessionId || '-' },
    { key: 'workspace', label: t('工作目录', 'Workspace'), value: workingDir || '-' },
    { key: 'project_hash', label: t('项目哈希', 'Project Hash'), value: projectHash },
  ];
  const labelWidth = Math.max(...items.map(item => stringWidth(item.label))) + 2;

  useKeypress(
    (key) => {
      if (
        key.name === 'escape' ||
        key.name === 'return' ||
        key.sequence === 'q' ||
        key.sequence === 'Q'
      ) {
        onClose();
        return;
      }
    },
    { isActive: true }
  );

  return (
    <Box
      flexDirection="column"
      paddingX={1}
      height={pane?.rows}
      backgroundColor={colors.content.surface}
      width="100%"
    >
      <Box height={2} flexShrink={0}>
        <Text bold>
          {t('当前会话状态', 'Current Status')}
        </Text>
      </Box>

      <Box flexDirection="column" flexGrow={pane ? 1 : 0} marginBottom={1}>
        {items.map((item) => (
          <Box key={item.key} height={1} flexShrink={0}>
            <Box width={labelWidth} flexShrink={0}>
              <Text color={colors.content.secondary}>{item.label}</Text>
            </Box>
            <Box flexGrow={1} flexShrink={1} overflowX="hidden">
              <Text wrap="truncate-end">{item.value}</Text>
            </Box>
          </Box>
        ))}
      </Box>

      <Box height={1} flexShrink={0}>
        <Text color={colors.content.tertiary} wrap="truncate-end">
          {PANEL_TIPS.status}
        </Text>
      </Box>
    </Box>
  );
}